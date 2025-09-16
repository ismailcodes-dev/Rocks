import discord
from discord.ext import commands
from discord import app_commands, ui
from .channel_config import get_guild_settings
import asyncio

# --- DYNAMIC PERMISSION CHECK ---
async def can_upload_check(interaction: discord.Interaction) -> bool:
    # First, check for admin permissions
    if interaction.user.guild_permissions.administrator:
        return True
        
    # Then, fetch the configured veteran role ID for this server
    guild_settings = get_guild_settings(interaction.guild.id)
    veteran_role_id = guild_settings.get("VETERAN_ROLE_ID")
    
    # If no role is configured or the user doesn't have it, deny access
    if not veteran_role_id:
        return False
    
    veteran_role = discord.utils.get(interaction.user.roles, id=veteran_role_id)
    return veteran_role is not None

# --- The Modal (Pop-up Form) for item details ---
class UploadModal(ui.Modal, title="Upload New Shop Item"):
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
                await interaction.response.send_message("❌ Price must be a positive number.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Price must be a valid number.", ephemeral=True)
            return

        await interaction.response.send_message(
            "✅ Details received! Now, please send a message in this channel with your **main thumbnail** (PNG/JPG). You can attach up to 3 images.",
            ephemeral=True
        )
        
        creator_cog = self.bot.get_cog("CreatorCog")
        if creator_cog:
            creator_cog.pending_uploads[interaction.user.id] = {
                "details": {
                    "item_name": self.item_name.value,
                    "application": self.application.value,
                    "category": self.category.value,
                    "price": price_value,
                    "product_link": self.product_link.value
                },
                "channel_id": interaction.channel_id
            }

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"Error in UploadModal: {error}")
        await interaction.response.send_message("Oops! Something went wrong.", ephemeral=True)


# --- The View with the initial "Create" button ---
class StartUploadView(ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180)
        self.bot = bot

    @ui.button(label="Create New Item", style=discord.ButtonStyle.green, emoji="✨")
    async def create_item(self, interaction: discord.Interaction, button: ui.Button):
        modal = UploadModal(self.bot)
        await interaction.response.send_modal(modal)
        self.stop()

# --- The Main Cog ---
class CreatorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pending_uploads = {}

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')
        
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            # Give a more helpful error if the role isn't configured
            guild_settings = get_guild_settings(interaction.guild.id)
            if not guild_settings.get("VETERAN_ROLE_ID"):
                await interaction.response.send_message("❌ The Veteran role has not been set up on this server. An admin must set it with `/config setveteranrole`.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Only Veteran Members or Admins can upload items to the shop.", ephemeral=True)
        else:
            print(f"An unhandled error occurred in CreatorCog: {error}")

    @app_commands.command(name="upd", description="[Veterans] Upload a new item to the shop.")
    @app_commands.check(can_upload_check) # Using the new permission check
    async def upload(self, interaction: discord.Interaction):
        view = StartUploadView(self.bot)
        await interaction.response.send_message(
            "Click the button below to start uploading a new item to the shop.",
            view=view,
            ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.attachments:
            return

        if message.author.id in self.pending_uploads:
            pending_data = self.pending_uploads[message.author.id]
            
            if message.channel.id == pending_data["channel_id"]:
                
                details = pending_data["details"]
                screenshots = [att.url for att in message.attachments]
                
                try:
                    await self.bot.db.add_item_to_shop(
                        creator_id=message.author.id,
                        guild_id=message.guild.id,
                        item_name=details["item_name"],
                        application=details["application"],
                        category=details["category"],
                        price=details["price"],
                        product_link=details["product_link"],
                        screenshot_link=screenshots[0] if len(screenshots) > 0 else None,
                        screenshot_link_2=screenshots[1] if len(screenshots) > 1 else None,
                        screenshot_link_3=screenshots[2] if len(screenshots) > 2 else None,
                    )

                    del self.pending_uploads[message.author.id]
                    await message.reply("✅ **Upload Complete!** Your item has been added to the shop.")

                    guild_settings = get_guild_settings(message.guild.id)
                    log_channel_id = guild_settings.get("NEW_ITEM_LOG_CHANNEL_ID")
                    if log_channel_id:
                        log_channel = self.bot.get_channel(log_channel_id)
                        if log_channel:
                            embed = discord.Embed(title="🚀 New Item Alert!", description=f"**{details['item_name']}** was just added by {message.author.mention}!", color=discord.Color.green())
                            embed.set_image(url=screenshots[0])
                            await log_channel.send(embed=embed)

                except Exception as e:
                    print(f"Error during final upload step: {e}")
                    await message.reply("❌ An error occurred while saving your item. Please try again.")

async def setup(bot: commands.Bot):
    await bot.add_cog(CreatorCog(bot))

