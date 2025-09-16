import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import typing

CONFIG_FILE = "channel_config.json"

def get_all_settings():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {}
    return {}

def save_all_settings(settings: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(settings, f, indent=4)

def get_guild_settings(guild_id: int) -> dict:
    all_settings = get_all_settings()
    return all_settings.get(str(guild_id), {})

def is_owner_or_has_admin_role(interaction: discord.Interaction) -> bool:
    if interaction.user.id == interaction.guild.owner_id:
        return True
    guild_settings = get_guild_settings(interaction.guild.id)
    admin_role_ids = set(guild_settings.get("ADMIN_ROLES", []))
    if not admin_role_ids:
        return False
    user_role_ids = {role.id for role in interaction.user.roles}
    return not user_role_ids.isdisjoint(admin_role_ids)

class ChannelConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    config_group = app_commands.Group(
        name="config",
        description="Commands for bot configuration.",
        default_permissions=discord.Permissions(administrator=True)
    )

    @config_group.command(name="setup", description="Set up important channels for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_channels(self, interaction: discord.Interaction,
        shop_channel: typing.Optional[discord.TextChannel] = None,
        purchase_log_channel: typing.Optional[discord.TextChannel] = None,
        admin_log_channel: typing.Optional[discord.TextChannel] = None,
        upload_channel: typing.Optional[discord.TextChannel] = None,
        new_item_log_channel: typing.Optional[discord.TextChannel] = None,
        database_view_channel: typing.Optional[discord.TextChannel] = None,
        level_up_channel: typing.Optional[discord.TextChannel] = None
    ):
        await interaction.response.defer()
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in all_settings:
            all_settings[guild_id_str] = {}
            
        updated_channels = []
        channels_to_set = {
            "SHOP_CHANNEL_ID": shop_channel, "PURCHASE_LOG_CHANNEL_ID": purchase_log_channel,
            "ADMIN_LOG_CHANNEL_ID": admin_log_channel, "UPLOAD_CHANNEL_ID": upload_channel,
            "NEW_ITEM_LOG_CHANNEL_ID": new_item_log_channel, "DATABASE_VIEW_CHANNEL_ID": database_view_channel,
            "LEVEL_UP_CHANNEL_ID": level_up_channel
        }
        for key, channel in channels_to_set.items():
            if channel is not None:
                all_settings[guild_id_str][key] = channel.id
                updated_channels.append(f"**{key.replace('_ID', '')}** → {channel.mention}")
        save_all_settings(all_settings)
        if not updated_channels:
            await interaction.followup.send("You didn't specify any channels to update.", ephemeral=True)
            return
        embed = discord.Embed(title=f"✅ Bot Channels Updated", description="\n".join(updated_channels), color=discord.Color.green())
        await interaction.followup.send(embed=embed)

    # --- MODIFIED: Renamed and updated to add roles to a list ---
    @config_group.command(name="addcreatorrole", description="Add a role to the list of roles that can upload items.")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_creator_role(self, interaction: discord.Interaction, role: discord.Role):
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in all_settings:
            all_settings[guild_id_str] = {}
        
        creator_roles = all_settings[guild_id_str].get("CREATOR_ROLE_IDS", [])
        if role.id in creator_roles:
            await interaction.response.send_message(f"❌ {role.mention} is already a creator role.", ephemeral=True)
            return
            
        creator_roles.append(role.id)
        all_settings[guild_id_str]["CREATOR_ROLE_IDS"] = creator_roles
        save_all_settings(all_settings)
        
        embed = discord.Embed(title="✅ Creator Role Added", description=f"Members with the {role.mention} role can now use the `/upd` command.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- NEW: Command to remove a creator role ---
    @config_group.command(name="removecreatorrole", description="Remove a role from the list of roles that can upload items.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_creator_role(self, interaction: discord.Interaction, role: discord.Role):
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in all_settings:
            all_settings[guild_id_str] = {}

        creator_roles = all_settings[guild_id_str].get("CREATOR_ROLE_IDS", [])
        if role.id not in creator_roles:
            await interaction.response.send_message(f"❌ {role.mention} is not a creator role.", ephemeral=True)
            return
            
        creator_roles.remove(role.id)
        all_settings[guild_id_str]["CREATOR_ROLE_IDS"] = creator_roles
        save_all_settings(all_settings)

        embed = discord.Embed(title="✅ Creator Role Removed", description=f"Members with the {role.mention} role can no longer use the `/upd` command.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="view", description="View all configured bot channels and roles for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def view_config(self, interaction: discord.Interaction):
        guild_settings = get_guild_settings(interaction.guild.id)
        if not guild_settings:
            await interaction.response.send_message("⚠ No settings configured. Use `/config setup` and `/config addcreatorrole`.", ephemeral=True)
            return
        embed = discord.Embed(title=f"📌 Bot Configuration for {interaction.guild.name}", color=discord.Color.blurple())
        
        description = ""
        channel_keys = ["SHOP_CHANNEL_ID", "PURCHASE_LOG_CHANNEL_ID", "ADMIN_LOG_CHANNEL_ID", "UPLOAD_CHANNEL_ID", "NEW_ITEM_LOG_CHANNEL_ID", "DATABASE_VIEW_CHANNEL_ID", "LEVEL_UP_CHANNEL_ID"]
        for key in channel_keys:
            channel_id = guild_settings.get(key)
            name = key.replace('_ID', '')
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                description += f"**{name}** → {channel.mention if channel else 'Not Found'}\n"
            else:
                description += f"**{name}** → *Not Set*\n"

        # --- MODIFIED: Now lists multiple creator roles ---
        creator_role_ids = guild_settings.get("CREATOR_ROLE_IDS", [])
        description += "\n**CREATOR_ROLES** → "
        if creator_role_ids:
            role_mentions = []
            for role_id in creator_role_ids:
                role = interaction.guild.get_role(role_id)
                role_mentions.append(role.mention if role else "`Not Found`")
            description += ", ".join(role_mentions)
        else:
            description += "*Not Set*"

        embed.description = description
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelConfigCog(bot))

