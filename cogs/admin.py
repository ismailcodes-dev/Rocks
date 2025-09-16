import discord
from discord.ext import commands
from discord import app_commands
from .channel_config import get_guild_settings, save_all_settings, get_all_settings, is_owner_or_has_admin_role
import asyncio

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

    # --- DYNAMIC COMMAND TO RETROACTIVELY ASSIGN VETERAN ROLE ---
    @app_commands.command(name="syncveterans", description="[Admin] Give the Veteran role to all members at or above level 25.")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_veterans(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        guild_settings = get_guild_settings(interaction.guild.id)
        veteran_role_id = guild_settings.get("VETERAN_ROLE_ID")
        upload_channel_id = guild_settings.get("UPLOAD_CHANNEL_ID")

        if not veteran_role_id:
            await interaction.followup.send(
                "❌ The Veteran role has not been configured for this server. "
                "Please set it first using `/config setveteranrole`.",
                ephemeral=True
            )
            return

        veteran_role = interaction.guild.get_role(veteran_role_id)
        if not veteran_role:
            await interaction.followup.send("❌ The configured Veteran role could not be found. It may have been deleted.", ephemeral=True)
            return

        all_users_data = await self.bot.db.get_all_users_in_guild(interaction.guild.id)
        eligible_users = [user for user in all_users_data if user['level'] >= 25]
        
        updated_count = 0
        
        await interaction.followup.send(f"Found {len(eligible_users)} members at or above level 25. Starting role sync...", ephemeral=True)

        for user_data in eligible_users:
            member = interaction.guild.get_member(user_data['user_id'])
            
            if member and veteran_role not in member.roles:
                try:
                    await member.add_roles(veteran_role, reason="Syncing roles for existing high-level members")
                    
                    try:
                        dm_message = (
                            f"Congratulations! You've been promoted to **{veteran_role.name}** in **{interaction.guild.name}**.\n\n"
                            f"You can now upload your items to the store using the `/upd` command"
                        )
                        if upload_channel_id:
                            dm_message += f" in the <#{upload_channel_id}> channel."
                        else:
                            dm_message += "."
                        
                        await member.send(dm_message)
                    except discord.Forbidden:
                        print(f"Could not DM {member.display_name} about their promotion (DMs disabled).")

                    updated_count += 1
                    await asyncio.sleep(0.5) 
                except discord.Forbidden:
                    print(f"Failed to add role to {member.display_name} - Missing Permissions")
                except Exception as e:
                    print(f"Failed to add role to {member.display_name} due to an error: {e}")

        final_embed = discord.Embed(
            title="✅ Veteran Role Sync Complete",
            description=f"Successfully granted the {veteran_role.mention} role to **{updated_count}** members.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=final_embed, ephemeral=True)


    # (Your other admin commands remain unchanged)
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
    async def resetlevels(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
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

