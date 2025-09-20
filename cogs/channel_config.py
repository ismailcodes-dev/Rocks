# cogs/channel_config.py

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import typing
import random # --- ADDED ---
import aiohttp # --- ADDED ---

# --- ADDED: Load the Tenor API Key ---
from dotenv import load_dotenv
load_dotenv()
TENOR_API_KEY = os.getenv("TENOR_API_KEY")

CONFIG_FILE = "channel_config.json"

# --- Perk Definitions (unchanged) ---
PERKS = {
    "default": {"multiplier": 1.0, "daily_bonus": 0, "shop_discount": 0.0, "pay_limit": 10000, "flair": ""},
    "elite": {"multiplier": 1.2, "daily_bonus": 250, "shop_discount": 0.0, "pay_limit": 25000, "flair": "💠"},
    "master": {"multiplier": 1.5, "daily_bonus": 750, "shop_discount": 0.05, "pay_limit": 25000, "flair": "🏆"},
    "supreme": {"multiplier": 2.0, "daily_bonus": 2000, "shop_discount": 0.10, "pay_limit": 25000, "flair": "👑"}
}

# --- Helper functions (get_all_settings, save_all_settings, etc. are unchanged) ---
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

def get_member_perks(member: discord.Member) -> dict:
    if not member or not isinstance(member, discord.Member): return PERKS["default"]
    guild_settings = get_guild_settings(member.guild.id)
    role_ids = {role.id for role in member.roles}
    if guild_settings.get("SUPREME_ROLE_ID") in role_ids: return PERKS["supreme"]
    if guild_settings.get("MASTER_ROLE_ID") in role_ids: return PERKS["master"]
    if guild_settings.get("ELITE_ROLE_ID") in role_ids: return PERKS["elite"]
    return PERKS["default"]

def is_owner_or_has_admin_role(interaction: discord.Interaction) -> bool:
    if interaction.user.id == interaction.guild.owner_id: return True
    guild_settings = get_guild_settings(interaction.guild.id)
    admin_role_ids = set(guild_settings.get("ADMIN_ROLES", []))
    if not admin_role_ids: return False
    user_role_ids = {role.id for role in interaction.user.roles}
    return not user_role_ids.isdisjoint(admin_role_ids)

# --- NEW: Function to get a random GIF from Tenor ---
async def get_random_gif(search_term: str) -> str:
    """Fetches a random GIF URL from Tenor based on a search term."""
    fallback_gif = "https://i.imgur.com/gJ3s2T3.gif" # A default GIF if the API fails
    if not TENOR_API_KEY:
        print("Warning: TENOR_API_KEY is not set. Using fallback GIF.")
        return fallback_gif

    try:
        url = f"https://tenor.googleapis.com/v2/search?q={search_term}&key={TENOR_API_KEY}&limit=20&media_filter=minimal"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("results"):
                        gif = random.choice(data["results"])
                        return gif["media_formats"]["gif"]["url"]
    except Exception as e:
        print(f"Error fetching GIF from Tenor: {e}")

    return fallback_gif # Return the fallback if anything goes wrong

class ChannelConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot: return
        guild_settings = get_guild_settings(member.guild.id)
        
        # Auto-role logic
        join_role_id = guild_settings.get("JOIN_ROLE_ID")
        if join_role_id:
            role = member.guild.get_role(join_role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Automatic role assignment on join.")
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"Failed to assign join role in {member.guild.name}: {e}")

        # --- Welcome Message Logic ---
        welcome_channel_id = guild_settings.get("WELCOME_CHANNEL_ID")
        if welcome_channel_id:
            welcome_channel = member.guild.get_channel(welcome_channel_id)
            if welcome_channel:
                
                # 1. Load the local GIF file
                file = discord.File("cogs/welcome.gif", filename="welcome.gif")

                # Create the main embed
                embed = discord.Embed(
                    title=f"Welcome to {member.guild.name}!",
                    description=f"Welcome, {member.mention}! We're glad you're here.\n\n"
                                "• Make sure to read the <#1386665353916186655>.\n"
                                "• Check out our <#1402656692398719026> and consider Buying From them!",
                    color=discord.Color.from_str("#2b2d31")
                )
                
                if member.guild.icon:
                    embed.set_thumbnail(url=member.guild.icon.url)
                
                # 2. Tell the embed to use the attached file
                embed.set_image(url="attachment://welcome.gif")
                
                embed.set_footer(text=f"We are now at {member.guild.member_count} members!")

                try:
                    # 3. Send the embed AND the file together
                    await welcome_channel.send(file=file, embed=embed)
                except (discord.Forbidden, discord.HTTPException) as e:
                    print(f"Failed to send welcome message in {member.guild.name}: {e}")

    # (The rest of the file, including on_member_remove, setup_channels, etc., remains the same as the previous version)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot: return
        try:
            await self.bot.db.delete_user_data(member.id, member.guild.id)
            print(f"Removed data for former member {member.display_name} from {member.guild.name}.")
        except Exception as e:
            print(f"An error occurred while cleaning up data for member {member.id}: {e}")

    config_group = app_commands.Group(
        name="config",
        description="Commands for bot configuration.",
        default_permissions=discord.Permissions(administrator=True)
    )

    @config_group.command(name="setup", description="Set up important channels for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_channels(self, interaction: discord.Interaction,
        shop_channel: typing.Optional[discord.TextChannel] = None, purchase_log_channel: typing.Optional[discord.TextChannel] = None,
        admin_log_channel: typing.Optional[discord.TextChannel] = None, upload_channel: typing.Optional[discord.TextChannel] = None,
        new_item_log_channel: typing.Optional[discord.TextChannel] = None, database_view_channel: typing.Optional[discord.TextChannel] = None,
        level_up_channel: typing.Optional[discord.TextChannel] = None, welcome_channel: typing.Optional[discord.TextChannel] = None):
        await interaction.response.defer()
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in all_settings: all_settings[guild_id_str] = {}
        updated_channels = []
        channels_to_set = {
            "SHOP_CHANNEL_ID": shop_channel, "PURCHASE_LOG_CHANNEL_ID": purchase_log_channel, "ADMIN_LOG_CHANNEL_ID": admin_log_channel,
            "UPLOAD_CHANNEL_ID": upload_channel, "NEW_ITEM_LOG_CHANNEL_ID": new_item_log_channel,
            "DATABASE_VIEW_CHANNEL_ID": database_view_channel, "LEVEL_UP_CHANNEL_ID": level_up_channel,
            "WELCOME_CHANNEL_ID": welcome_channel
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

    @config_group.command(name="addcreatorrole", description="Add a role to the list of roles that can upload items.")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_creator_role(self, interaction: discord.Interaction, role: discord.Role):
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in all_settings: all_settings[guild_id_str] = {}
        creator_roles = all_settings[guild_id_str].get("CREATOR_ROLE_IDS", [])
        if role.id in creator_roles:
            await interaction.response.send_message(f"❌ {role.mention} is already a creator role.", ephemeral=True)
            return
        creator_roles.append(role.id)
        all_settings[guild_id_str]["CREATOR_ROLE_IDS"] = creator_roles
        save_all_settings(all_settings)
        embed = discord.Embed(title="✅ Creator Role Added", description=f"Members with the {role.mention} role can now use the `/upd` command.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="removecreatorrole", description="Remove a role from the list of roles that can upload items.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_creator_role(self, interaction: discord.Interaction, role: discord.Role):
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in all_settings: all_settings[guild_id_str] = {}
        creator_roles = all_settings[guild_id_str].get("CREATOR_ROLE_IDS", [])
        if role.id not in creator_roles:
            await interaction.response.send_message(f"❌ {role.mention} is not a creator role.", ephemeral=True)
            return
        creator_roles.remove(role.id)
        all_settings[guild_id_str]["CREATOR_ROLE_IDS"] = creator_roles
        save_all_settings(all_settings)
        embed = discord.Embed(title="✅ Creator Role Removed", description=f"Members with the {role.mention} role can no longer use the `/upd` command.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="setjoinrole", description="Set the role to be automatically given to new members.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_join_role(self, interaction: discord.Interaction, role: discord.Role):
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in all_settings: all_settings[guild_id_str] = {}
        all_settings[guild_id_str]["JOIN_ROLE_ID"] = role.id
        save_all_settings(all_settings)
        embed = discord.Embed(title="✅ Join Role Set", description=f"New members will now automatically receive the {role.mention} role when they join.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    setrankrole_group = app_commands.Group(name="setrankrole", description="Configure the roles for member ranks.", default_permissions=discord.Permissions(administrator=True))

    @setrankrole_group.command(name="elite", description="Set the role for Elite Members (Level 50+).")
    async def set_elite_role(self, interaction: discord.Interaction, role: discord.Role):
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in all_settings: all_settings[guild_id_str] = {}
        all_settings[guild_id_str]["ELITE_ROLE_ID"] = role.id
        save_all_settings(all_settings)
        await interaction.response.send_message(f"✅ Set **Elite Member** role to {role.mention}. Perks will apply automatically.", ephemeral=True)

    @setrankrole_group.command(name="master", description="Set the role for Master Members (Level 75+).")
    async def set_master_role(self, interaction: discord.Interaction, role: discord.Role):
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in all_settings: all_settings[guild_id_str] = {}
        all_settings[guild_id_str]["MASTER_ROLE_ID"] = role.id
        save_all_settings(all_settings)
        await interaction.response.send_message(f"✅ Set **Master Member** role to {role.mention}. Perks will apply automatically.", ephemeral=True)

    @setrankrole_group.command(name="supreme", description="Set the role for Supreme Members (Level 100+).")
    async def set_supreme_role(self, interaction: discord.Interaction, role: discord.Role):
        all_settings = get_all_settings()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in all_settings: all_settings[guild_id_str] = {}
        all_settings[guild_id_str]["SUPREME_ROLE_ID"] = role.id
        save_all_settings(all_settings)
        await interaction.response.send_message(f"✅ Set **Supreme Member** role to {role.mention}. Perks will apply automatically.", ephemeral=True)

    @config_group.command(name="view", description="View all configured bot channels and roles for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def view_config(self, interaction: discord.Interaction):
        guild_settings = get_guild_settings(interaction.guild.id)
        embed = discord.Embed(title=f"📌 Bot Configuration for {interaction.guild.name}", color=discord.Color.blurple())
        
        description = ""
        channel_keys = ["SHOP_CHANNEL_ID", "PURCHASE_LOG_CHANNEL_ID", "ADMIN_LOG_CHANNEL_ID", "UPLOAD_CHANNEL_ID", "NEW_ITEM_LOG_CHANNEL_ID", "DATABASE_VIEW_CHANNEL_ID", "LEVEL_UP_CHANNEL_ID", "WELCOME_CHANNEL_ID"]
        for key in channel_keys:
            channel_id = guild_settings.get(key)
            name = key.replace('_ID', '')
            description += f"**{name}** → {f'<#{channel_id}>' if channel_id else '*Not Set*'}\n"

        creator_role_ids = guild_settings.get("CREATOR_ROLE_IDS", [])
        description += "\n**CREATOR_ROLES** → "
        description += ", ".join([f"<@&{r}>" for r in creator_role_ids]) if creator_role_ids else "*Not Set*"
        
        join_role_id = guild_settings.get("JOIN_ROLE_ID")
        description += f"\n**JOIN_ROLE** → {f'<@&{join_role_id}>' if join_role_id else '*Not Set*'}"

        description += "\n\n**Rank Roles**"
        elite_id = guild_settings.get("ELITE_ROLE_ID")
        master_id = guild_settings.get("MASTER_ROLE_ID")
        supreme_id = guild_settings.get("SUPREME_ROLE_ID")
        description += f"\n**Elite (Lvl 50)** → {f'<@&{elite_id}>' if elite_id else '*Not Set*'}"
        description += f"\n**Master (Lvl 75)** → {f'<@&{master_id}>' if master_id else '*Not Set*'}"
        description += f"\n**Supreme (Lvl 100)** → {f'<@&{supreme_id}>' if supreme_id else '*Not Set*'}"
        
        embed.description = description
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelConfigCog(bot))