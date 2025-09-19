import discord
from discord.ext import commands
from discord import app_commands
from .channel_config import get_guild_settings, save_all_settings, get_all_settings, is_owner_or_has_admin_role, PERKS
import asyncio
import time

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        else:
            print(f"An unhandled error occurred in AdminCog: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)

    @app_commands.command(name="synccreators", description="[Admin] Give the Creator role to all members at or above level 25.")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_creators(self, interaction: discord.Interaction):
        # This command is unchanged but kept for functionality.
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild_settings = get_guild_settings(interaction.guild.id)
        creator_role_ids = guild_settings.get("CREATOR_ROLE_IDS", [])
        if not creator_role_ids:
            await interaction.followup.send("❌ No Creator roles configured. Use `/config addcreatorrole` first.", ephemeral=True)
            return
        
        all_users_data = await self.bot.db.get_all_users_in_guild(interaction.guild.id)
        eligible_users = [user for user in all_users_data if user['level'] >= 25]
        updated_count = 0
        
        for user_data in eligible_users:
            member = interaction.guild.get_member(user_data['user_id'])
            if member:
                # Logic to add roles without removing existing ones
                current_role_ids = {role.id for role in member.roles}
                roles_to_add = []
                for role_id in creator_role_ids:
                    if role_id not in current_role_ids:
                        role = interaction.guild.get_role(role_id)
                        if role:
                            roles_to_add.append(role)
                if roles_to_add:
                    try:
                        await member.add_roles(*roles_to_add, reason="Syncing Creator roles")
                        updated_count += 1
                    except discord.Forbidden:
                        print(f"Failed to add creator role to {member.display_name} - Missing Permissions")
        
        await interaction.followup.send(f"✅ Sync complete! Checked **{len(eligible_users)}** eligible members and updated **{updated_count}**.", ephemeral=True)

    # --- NEW: Command to sync all rank roles for existing members ---
    @app_commands.command(name="syncranks", description="[Admin] Give rank roles to all members who meet level requirements.")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_ranks(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        guild_settings = get_guild_settings(interaction.guild.id)
        
        # Role mapping: Level requirement, Role ID, Perk Key
        rank_roles_map = {
            100: (guild_settings.get("SUPREME_ROLE_ID"), "supreme"),
            75: (guild_settings.get("MASTER_ROLE_ID"), "master"),
            50: (guild_settings.get("ELITE_ROLE_ID"), "elite")
        }

        if not any(role_id for role_id, _ in rank_roles_map.values()):
            await interaction.followup.send("❌ No rank roles configured. Use `/config setrankrole` to set them up.", ephemeral=True)
            return

        all_users_data = await self.bot.db.get_all_users_in_guild(interaction.guild.id)
        
        counts = {"elite": 0, "master": 0, "supreme": 0}
        
        await interaction.followup.send(f"Scanning **{len(all_users_data)}** members to sync rank roles. This may take a moment...", ephemeral=True)

        for user_data in all_users_data:
            member = interaction.guild.get_member(user_data['user_id'])
            if not member or member.bot:
                continue

            user_level = user_data['level']
            
            # Check from highest to lowest level requirement
            for level_req, (role_id, perk_key) in sorted(rank_roles_map.items(), reverse=True):
                if user_level >= level_req and role_id:
                    role = interaction.guild.get_role(role_id)
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason=f"Retroactive promotion to Level {level_req}")
                            counts[perk_key] += 1
                            
                            # Send the user a detailed DM about their new perks
                            perk_info = PERKS[perk_key]
                            embed = discord.Embed(
                                title="🎉 You've Been Promoted!",
                                description=f"As a valued member of **{interaction.guild.name}**, your high level has earned you the **{role.name}** rank!",
                                color=discord.Color.brand_green()
                            )
                            embed.add_field(name="💰 Economy Boost", value=f"You now earn **{perk_info['multiplier']:.1f}x** Coins & XP!", inline=False)
                            embed.add_field(name="🎁 Daily Bonus", value=f"You get an extra **{perk_info['daily_bonus']:,}** coins from `/daily`.", inline=False)
                            if perk_info['shop_discount'] > 0:
                                embed.add_field(name="🛍️ Shop Discount", value=f"You get a **{perk_info['shop_discount']:.0%}** discount on all items!", inline=False)
                            if perk_key == "supreme":
                                embed.add_field(name="🚀 Supreme Perk", value="You can now use `/bumpitem` once per week!", inline=False)
                            
                            await member.send(embed=embed)
                            
                        except (discord.Forbidden, discord.HTTPException):
                            print(f"Could not assign rank role or DM {member.name}")
                        
                        # Once the highest role is assigned, we don't need to check for lower ones
                        break 
        
        summary_embed = discord.Embed(
            title="✅ Rank Role Sync Complete",
            color=discord.Color.green()
        )
        summary_desc = "Assigned roles to members who already met the level requirements.\n\n"
        summary_desc += f"**Supreme Roles:** {counts['supreme']} assigned\n"
        summary_desc += f"**Master Roles:** {counts['master']} assigned\n"
        summary_desc += f"**Elite Roles:** {counts['elite']} assigned"
        summary_embed.description = summary_desc
        
        await interaction.followup.send(embed=summary_embed, ephemeral=True)


    # (Your other admin commands remain unchanged)
    @app_commands.command(name="removecoins", description="[Admin] Remove coins from a user.")
    @app_commands.check(is_owner_or_has_admin_role)
    async def removecoins(self, interaction: discord.Interaction, user: discord.User, amount: int):
        await interaction.response.defer()
        if amount <= 0:
            await interaction.followup.send("Please provide a positive number of coins to remove.", ephemeral=True)
            return
        player = await self.bot.db.get_user_data(user.id, interaction.guild.id)
        new_balance = max(0, player['balance'] - amount)
        await self.bot.db.update_user_data(user.id, interaction.guild.id, {"balance": new_balance})
        await interaction.followup.send(f"✅ Removed **{amount:,}** coins from {user.mention}. Their new balance is **{new_balance:,}**.")

    adminrole_group = app_commands.Group(name="adminrole", description="Manage which roles have admin access.")

    @adminrole_group.command(name="add", description="[Admin] Grant a role admin command access.")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_admin_role(self, interaction: discord.Interaction, role: discord.Role):
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in all_settings: all_settings[guild_id_str] = {}
        admin_roles = all_settings[guild_id_str].get("ADMIN_ROLES", [])
        if role.id in admin_roles:
            await interaction.response.send_message(f"❌ {role.mention} is already an admin role.", ephemeral=True)
            return
        admin_roles.append(role.id)
        all_settings[guild_id_str]["ADMIN_ROLES"] = admin_roles
        save_all_settings(all_settings)
        await interaction.response.send_message(f"✅ Granted admin access to {role.mention}.", ephemeral=True)

    @adminrole_group.command(name="remove", description="[Admin] Revoke a role's admin command access.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_admin_role(self, interaction: discord.Interaction, role: discord.Role):
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        admin_roles = all_settings.get(guild_id_str, {}).get("ADMIN_ROLES", [])
        if role.id not in admin_roles:
            await interaction.response.send_message(f"❌ {role.mention} is not an admin role.", ephemeral=True)
            return
        admin_roles.remove(role.id)
        all_settings[guild_id_str]["ADMIN_ROLES"] = admin_roles
        save_all_settings(all_settings)
        await interaction.response.send_message(f"✅ Revoked admin access from {role.mention}.", ephemeral=True)

    @adminrole_group.command(name="list", description="[Admin] List all roles with admin command access.")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_admin_roles(self, interaction: discord.Interaction):
        guild_settings = get_guild_settings(interaction.guild.id)
        admin_role_ids = guild_settings.get("ADMIN_ROLES", [])
        if not admin_role_ids:
            await interaction.response.send_message("No admin roles have been configured for this server.", ephemeral=True)
            return
        roles = [interaction.guild.get_role(r_id) for r_id in admin_role_ids]
        description = "Users with these roles can use admin commands:\n\n" + "\n".join(r.mention for r in roles if r)
        embed = discord.Embed(title="⚙️ Configured Admin Roles", description=description, color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="givecoins", description="[Admin] Give coins to a user.")
    @app_commands.check(is_owner_or_has_admin_role)
    async def givecoins(self, interaction: discord.Interaction, user: discord.User, amount: int):
        await interaction.response.defer()
        player = await self.bot.db.get_user_data(user.id, interaction.guild.id)
        new_balance = player['balance'] + amount
        await self.bot.db.update_user_data(user.id, interaction.guild.id, {"balance": new_balance})
        await interaction.followup.send(f"✅ Gave **{amount:,}** coins to {user.mention}. Their new balance is **{new_balance:,}**.")

    @app_commands.command(name="removeitem", description="[Admin] Remove an item from the shop.")
    @app_commands.check(is_owner_or_has_admin_role)
    async def removeitem(self, interaction: discord.Interaction, item_id: int):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.delete_item(item_id, interaction.guild.id)
        await interaction.followup.send(f"Successfully removed item ID `{item_id}` from the shop.")

    @app_commands.command(name="resetlevels", description="[Admin] Reset levels for players above level 11.")
    @app_commands.check(is_owner_or_has_admin_role)
    async def resetlevels(self, interaction: discord.Interaction, user: discord.User = None):
        await interaction.response.defer(ephemeral=True)
        if user:
            await self.bot.db.update_user_data(user.id, interaction.guild.id, {"level": 1, "xp": 0})
            await interaction.followup.send(f"✅ Reset level and XP for {user.mention}.")
        else:
            all_users = await self.bot.db.get_all_users_in_guild(interaction.guild.id)
            updated_count = 0
            for user_data in all_users:
                if user_data['level'] > 11:
                    await self.bot.db.update_user_data(user_data['user_id'], interaction.guild.id, {"level": 9, "xp": 0})
                    updated_count += 1
            await interaction.followup.send(f"✅ Level reset complete! Affected **{updated_count}** players.")

    @app_commands.command(name="featureitem", description="[Admin] Feature an item in the new shop view.")
    @app_commands.check(is_owner_or_has_admin_role)
    @app_commands.describe(item_id="The ID of the item to feature.")
    async def feature_item(self, interaction: discord.Interaction, item_id: int):
        await interaction.response.defer(ephemeral=True)
        item = await self.bot.db.get_item_details(item_id, interaction.guild.id)
        if not item:
            await interaction.followup.send(f"❌ No item with ID `{item_id}` was found.", ephemeral=True)
            return
        await self.bot.db.set_featured_item(item_id, interaction.guild.id)
        await interaction.followup.send(f"✅ **{item['item_name']}** is now the featured item in the shop!")

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))

