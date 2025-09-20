import discord
from discord.ext import commands
from discord import app_commands, ui
from .channel_config import get_guild_settings, get_member_perks
import time

async def can_upload_check(interaction: discord.Interaction) -> bool:
    guild_settings = get_guild_settings(interaction.guild.id)
    creator_role_ids = set(guild_settings.get("CREATOR_ROLE_IDS", []))
    if not creator_role_ids: return False
    user_role_ids = {role.id for role in interaction.user.roles}
    return not user_role_ids.isdisjoint(creator_role_ids)

class UploadModal(ui.Modal, title="Upload New Shop Item"):
    # ... (This class is unchanged)
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=300)
        self.bot = bot
    item_name = ui.TextInput(label="Item Name", placeholder="e.g., 'Galaxy Project File'", style=discord.TextStyle.short, required=True)
    application = ui.TextInput(label="Application", placeholder="e.g., 'After Effects', 'Alight Motion', 'General'", style=discord.TextStyle.short, required=True)
    category = ui.TextInput(label="Category", placeholder="e.g., 'Project File', 'CC', 'Overlays'", style=discord.TextStyle.short, required=True)
    price = ui.TextInput(label="Price (Coins)", placeholder="e.g., '500'", style=discord.TextStyle.short, required=True)
    product_link = ui.TextInput(label="Download Link", placeholder="e.g., a Google Drive or Mega link", style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_value = int(self.price.value)
            if price_value < 0:
                await interaction.response.send_message("❌ Price must be a positive number.", ephemeral=True); return
        except ValueError:
            await interaction.response.send_message("❌ Price must be a valid number.", ephemeral=True); return
        await interaction.response.send_message("✅ Details received! Now, send your attachments in this channel.", ephemeral=True)
        creator_cog = self.bot.get_cog("CreatorCog")
        if creator_cog:
            creator_cog.pending_uploads[interaction.user.id] = {
                "details": {"item_name": self.item_name.value, "application": self.application.value, "category": self.category.value, "price": price_value, "product_link": self.product_link.value},
                "channel_id": interaction.channel_id
            }
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"Error in UploadModal: {error}")
        await interaction.response.send_message("Oops! Something went wrong.", ephemeral=True)

class StartUploadView(ui.View):
    # ... (This class is unchanged)
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180)
        self.bot = bot
    @ui.button(label="Create New Item", style=discord.ButtonStyle.green, emoji="✨")
    async def create_item(self, interaction: discord.Interaction, button: ui.Button):
        modal = UploadModal(self.bot)
        await interaction.response.send_modal(modal)
        self.stop()

# --- NEW: View for the /bumpitem command ---
class BumpItemView(ui.View):
    def __init__(self, bot, items):
        super().__init__(timeout=180)
        self.bot = bot
        options = [discord.SelectOption(label=f"{item['item_name'][:100]}", value=str(item['item_id'])) for item in items[:25]]
        self.select_menu = ui.Select(placeholder="Select one of your items to bump...", options=options)
        self.select_menu.callback = self.on_select
        self.add_item(self.select_menu)

    async def on_select(self, interaction: discord.Interaction):
        item_id = int(self.select_menu.values[0])
        await self.bot.db.bump_item(item_id)
        await self.bot.db.update_user_data(interaction.user.id, interaction.guild.id, {"last_bump_timestamp": time.time()})
        
        embed = discord.Embed(title="🚀 Item Bumped!", description=f"Your item has been moved to the top of the 'New Arrivals' list.", color=discord.Color.green())
        await interaction.response.edit_message(embed=embed, view=None)

class CreatorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pending_uploads = {}

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')
        
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            guild_settings = get_guild_settings(interaction.guild.id)
            if not guild_settings.get("CREATOR_ROLE_IDS"):
                await interaction.response.send_message("❌ No Creator roles are set up. An admin must use `/config addcreatorrole`.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ You do not have a required Creator Role to use this command.", ephemeral=True)
        else:
            print(f"An unhandled error occurred in CreatorCog: {error}")

    @app_commands.command(name="upd", description="[Creators] Upload a new item to the shop.")
    @app_commands.check(can_upload_check)
    async def upload(self, interaction: discord.Interaction):
        view = StartUploadView(self.bot)
        await interaction.response.send_message("Click the button below to start uploading a new item.", view=view, ephemeral=True)

    # --- NEW: /bumpitem command for Supreme Members ---
    @app_commands.command(name="bumpitem", description="[Supreme Members] Move one of your items to the top of the shop.")
    async def bump_item(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        perks = get_member_perks(interaction.user)
        
        # Check for Supreme rank
        if perks['flair'] != "👑":
            await interaction.followup.send("❌ This command is only available to **Supreme Members** (Level 100+).", ephemeral=True)
            return
            
        # Check cooldown
        player_data = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        last_bump = player_data.get('last_bump_timestamp', 0)
        cooldown = 604800 # 7 days in seconds
        
        if time.time() - last_bump < cooldown:
            time_left = cooldown - (time.time() - last_bump)
            await interaction.followup.send(f"❌ Your item bump is on cooldown. Please wait **{time.strftime('%d days, %H hours, %M minutes', time.gmtime(time_left))}**.", ephemeral=True)
            return

        # Fetch user's items and show dropdown
        user_items = await self.bot.db.get_items_by_creator(interaction.user.id, interaction.guild.id)
        if not user_items:
            await interaction.followup.send("❌ You don't have any items in the shop to bump.", ephemeral=True)
            return
            
        await interaction.followup.send("Please select one of your items from the dropdown to bump it to the top.", view=BumpItemView(self.bot, user_items), ephemeral=True)


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.attachments or message.author.id not in self.pending_uploads:
            return
            
        pending_data = self.pending_uploads[message.author.id]
        if message.channel.id == pending_data["channel_id"]:
            details = pending_data["details"]
            screenshots = [att.url for att in message.attachments]
            
            try:
                await self.bot.db.add_item_to_shop(
                    creator_id=message.author.id, guild_id=message.guild.id,
                    item_name=details["item_name"], application=details["application"],
                    category=details["category"], price=details["price"],
                    product_link=details["product_link"], screenshot_link=screenshots[0] if screenshots else None,
                    screenshot_link_2=screenshots[1] if len(screenshots) > 1 else None,
                    screenshot_link_3=screenshots[2] if len(screenshots) > 2 else None,
                )
                del self.pending_uploads[message.author.id]
                await message.reply("✅ **Upload Complete!** Your item has been added.")

                guild_settings = get_guild_settings(message.guild.id)
                log_channel_id = guild_settings.get("NEW_ITEM_LOG_CHANNEL_ID")
                if log_channel_id:
                    log_channel = self.bot.get_channel(log_channel_id)
                    if log_channel:
                        embed = discord.Embed(title="🚀 New Item Alert!", description=f"**{details['item_name']}** was just added by {message.author.mention}!", color=discord.Color.green())
                        if screenshots: embed.set_image(url=screenshots[0])
                        await log_channel.send(embed=embed)
            except Exception as e:
                print(f"Error during final upload step: {e}")
                await message.reply("❌ An error occurred while saving your item.")

async def setup(bot: commands.Bot):
    await bot.add_cog(CreatorCog(bot))

