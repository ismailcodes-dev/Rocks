import discord
from discord.ext import commands
from discord import app_commands, ui
from .channel_config import get_guild_settings
import math
import traceback

# --- Set your commission rate here ---
# This means the creator gets 80% of the sale price.
COMMISSION_RATE = 0.80

# --- The View for Purchasing an Item (Contains the "Buy Now" button) ---
class PurchaseView(ui.View):
    def __init__(self, bot: commands.Bot, item_id: int):
        super().__init__(timeout=180)
        self.bot = bot
        self.item_id = item_id

    @ui.button(label="Buy Now", style=discord.ButtonStyle.green, emoji="🛒")
    async def buy_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            item = await self.bot.db.get_item_details(self.item_id, interaction.guild.id)
            player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)

            if not item:
                return await interaction.followup.send("❌ This item seems to have been removed from the shop.", ephemeral=True)
            if player['balance'] < item['price']:
                return await interaction.followup.send(f"❌ You don't have enough coins! You need **{item['price']:,}** coins.", ephemeral=True)

            # --- COMMISSION LOGIC ---
            creator_id = item['creator_id']
            commission_amount = int(item['price'] * COMMISSION_RATE)

            # 1. Deduct full price from the buyer
            new_balance_buyer = player['balance'] - item['price']
            await self.bot.db.update_user_data(interaction.user.id, interaction.guild.id, {"balance": new_balance_buyer})
            
            # 2. Add commission to the creator's balance
            creator_data = await self.bot.db.get_user_data(creator_id, interaction.guild.id)
            new_balance_creator = creator_data['balance'] + commission_amount
            await self.bot.db.update_user_data(creator_id, interaction.guild.id, {"balance": new_balance_creator})

            # 3. Finalize the purchase
            await self.bot.db.increment_purchase_count(self.item_id, interaction.guild.id)
            
            # --- SEND PURCHASE LOG ---
            try:
                guild_settings = get_guild_settings(interaction.guild.id)
                log_channel_id = guild_settings.get("PURCHASE_LOG_CHANNEL_ID")
                if log_channel_id:
                    log_channel = self.bot.get_channel(log_channel_id)
                    if log_channel:
                        creator = await self.bot.fetch_user(creator_id)
                        buyer = interaction.user
                        
                        log_embed = discord.Embed(
                            title="🛍️ New Purchase",
                            color=discord.Color.blurple(),
                            timestamp=discord.utils.utcnow()
                        )
                        log_embed.add_field(name="Item", value=f"`{item['item_name']}` (ID: {self.item_id})", inline=False)
                        log_embed.add_field(name="Buyer", value=buyer.mention, inline=True)
                        log_embed.add_field(name="Seller", value=creator.mention, inline=True)
                        log_embed.add_field(name="Price", value=f"{item['price']:,} coins", inline=False)
                        log_embed.add_field(name="Commission Paid", value=f"{commission_amount:,} coins ({COMMISSION_RATE:.0%})", inline=False)
                        log_embed.set_footer(text=f"Buyer ID: {buyer.id} | Seller ID: {creator.id}")
                        
                        await log_channel.send(embed=log_embed)
            except Exception as e:
                print(f"Failed to send purchase log: {e}")

            dm_embed = discord.Embed(title="✅ Purchase Successful!", description=f"Thank you for purchasing **{item['item_name']}**.", color=discord.Color.brand_green())
            dm_embed.add_field(name="Download Link", value=f"**[Click Here to Download]({item['product_link']})**")
            await interaction.user.send(embed=dm_embed)
            await interaction.followup.send("✅ Purchase complete! I've sent the download link to your DMs.", ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send("⚠️ **Purchase Failed.** I couldn't send you a DM. Please enable DMs from server members.", ephemeral=True)
        except Exception as e:
            print(f"Error during purchase: {e}")
            await interaction.followup.send("An unexpected error occurred. Please try again.", ephemeral=True)

# The rest of the ShopView and ShopCog remain unchanged...
class ShopView(ui.View):
    def __init__(self, bot: commands.Bot, author_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.author_id = author_id
        self.guild_id = guild_id
        self.current_tab = "featured"
        self.current_items = []
        self.selected_index = 0
        self.items_in_view = 10

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        print(f"--- Unhandled View Error ---\nUser: {interaction.user} | Item: {item}")
        traceback.print_exc()
        if not interaction.response.is_done():
            await interaction.response.send_message("An unexpected error occurred.", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This is not your shop session. Please use `/shop` to open your own.", ephemeral=True)
            return False
        return True

    async def build_embed_and_components(self):
        guild = self.bot.get_guild(self.guild_id)
        embed = discord.Embed(title=f"{guild.name} Marketplace", color=discord.Color.from_str("#5865F2"))
        self.clear_items()
        self.add_item(self.featured_button)
        self.add_item(self.new_button)
        self.add_item(self.all_items_button)
        content_description = ""
        thumbnail_url = "https://placehold.co/900x300/2b2d31/ffffff?text=Creator+Marketplace&font=raleway"
        if self.current_tab == "featured":
            featured_item = await self.bot.db.get_featured_item(self.guild_id)
            if featured_item:
                creator = await self.bot.fetch_user(featured_item['creator_id'])
                content_description = f"## ⭐ {featured_item['item_name']}\n*By {creator.display_name}*\n\n> A special item highlighted by our staff.\n\n**Price:** {featured_item['price']:,} coins"
                thumbnail_url = featured_item.get('screenshot_link')
                self.add_item(ui.Button(style=discord.ButtonStyle.green, label="🔍 View Item", custom_id=f"quick_view_{featured_item['item_id']}", row=1))
            else:
                content_description = "## ⭐ Featured Item\n\n> There is no featured item at the moment."
        elif self.current_tab in ["new", "all_items"]:
            title = "🚀 New Arrivals" if self.current_tab == "new" else "📚 All Items"
            content_description = f"## {title}\nUse the buttons to scroll and select an item.\n\n"
            if self.current_items:
                start = max(0, self.selected_index - math.floor(self.items_in_view / 2))
                end = min(len(self.current_items), start + self.items_in_view)
                start = max(0, end - self.items_in_view)
                list_str = ""
                for i in range(start, end):
                    item = self.current_items[i]
                    prefix = "➤" if i == self.selected_index else "•"
                    list_str += f"{prefix} `{item['item_name']}` - **{item.get('price', 0):,}** coins\n"
                content_description += list_str
                embed.set_footer(text=f"Showing item {self.selected_index + 1} of {len(self.current_items)}")
                if len(self.current_items) > 1:
                    self.scroll_up_button.disabled = self.selected_index == 0
                    self.scroll_down_button.disabled = self.selected_index == len(self.current_items) - 1
                    self.add_item(self.scroll_up_button)
                    self.add_item(self.scroll_down_button)
                self.add_item(self.select_item_button)
            else:
                content_description += "> Nothing to show here yet!"
        embed.set_image(url=thumbnail_url)
        embed.description = content_description
        return embed

    async def update_view(self, interaction: discord.Interaction):
        embed = await self.build_embed_and_components()
        await interaction.edit_original_response(embed=embed, view=self)

    async def handle_tab_switch(self, interaction: discord.Interaction, tab_name: str):
        self.current_tab = tab_name
        self.selected_index = 0
        if self.current_tab == "new":
            self.current_items = await self.bot.db.get_new_arrivals(self.guild_id)
        elif self.current_tab == "all_items":
            self.current_items = await self.bot.db.get_all_items(self.guild_id)
        else:
            self.current_items = []
        self.featured_button.style = discord.ButtonStyle.primary if tab_name == "featured" else discord.ButtonStyle.secondary
        self.new_button.style = discord.ButtonStyle.primary if tab_name == "new" else discord.ButtonStyle.secondary
        self.all_items_button.style = discord.ButtonStyle.primary if tab_name == "all_items" else discord.ButtonStyle.secondary
        await self.update_view(interaction)

    @ui.button(label="⭐ Featured", style=discord.ButtonStyle.primary, custom_id="featured_tab", row=0)
    async def featured_button(self, i: discord.Interaction, b: ui.Button):
        await i.response.defer()
        await self.handle_tab_switch(i, "featured")
    
    @ui.button(label="🚀 New Arrivals", style=discord.ButtonStyle.secondary, custom_id="new_tab", row=0)
    async def new_button(self, i: discord.Interaction, b: ui.Button):
        await i.response.defer()
        await self.handle_tab_switch(i, "new")
    
    @ui.button(label="📚 All Items", style=discord.ButtonStyle.secondary, custom_id="all_items_tab", row=0)
    async def all_items_button(self, i: discord.Interaction, b: ui.Button):
        await i.response.defer()
        await self.handle_tab_switch(i, "all_items")

    @ui.button(label="View Item", style=discord.ButtonStyle.green, custom_id="select_item", row=1)
    async def select_item_button(self, interaction: discord.Interaction, button: ui.Button):
        item = self.current_items[self.selected_index]
        await interaction.response.defer(ephemeral=True)
        full_item_details = await self.bot.db.get_item_details(item['item_id'], interaction.guild.id)
        if not full_item_details:
            return await interaction.followup.send("❌ This item could not be found.", ephemeral=True)
        creator = await self.bot.fetch_user(full_item_details['creator_id'])
        embed = discord.Embed(title=full_item_details['item_name'], color=discord.Color.from_str("#5865F2"))
        embed.set_author(name=f"Created by {creator.display_name}", icon_url=creator.display_avatar.url)
        embed.add_field(name="Price", value=f"**{full_item_details['price']:,}** coins")
        if full_item_details.get('screenshot_link'):
            embed.set_image(url=full_item_details['screenshot_link'])
        await interaction.followup.send(embed=embed, view=PurchaseView(self.bot, item['item_id']), ephemeral=True)

    @ui.button(emoji="🔼", style=discord.ButtonStyle.grey, custom_id="scroll_up", row=2)
    async def scroll_up_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index > 0:
            self.selected_index -= 1
            await interaction.response.defer()
            await self.update_view(interaction)
    
    @ui.button(emoji="🔽", style=discord.ButtonStyle.grey, custom_id="scroll_down", row=2)
    async def scroll_down_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.selected_index < len(self.current_items) - 1:
            self.selected_index += 1
            await interaction.response.defer()
            await self.update_view(interaction)

    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.data.get("custom_id", "").startswith("quick_view_"):
            await interaction.response.defer(ephemeral=True)
            item_id = int(interaction.data["custom_id"].split("_")[2])
            item = await self.bot.db.get_item_details(item_id, interaction.guild.id)
            if not item: return await interaction.followup.send("❌ Item not found.", ephemeral=True)
            creator = await self.bot.fetch_user(item['creator_id'])
            embed = discord.Embed(title=item['item_name'], color=discord.Color.from_str("#5865F2"))
            embed.set_author(name=f"Created by {creator.display_name}", icon_url=creator.display_avatar.url)
            embed.add_field(name="Price", value=f"**{item['price']:,}** coins")
            if item.get('screenshot_link'): embed.set_image(url=item['screenshot_link'])
            await interaction.followup.send(embed=embed, view=PurchaseView(self.bot, item_id), ephemeral=True)

class ShopCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')

    @app_commands.command(name="shop", description="Open the interactive marketplace.")
    async def shop(self, interaction: discord.Interaction):
        # --- NEW: Channel Check ---
        guild_settings = get_guild_settings(interaction.guild.id)
        shop_channel_id = guild_settings.get("SHOP_CHANNEL_ID")

        if shop_channel_id and interaction.channel.id != shop_channel_id:
            shop_channel = self.bot.get_channel(shop_channel_id)
            if shop_channel:
                await interaction.response.send_message(
                    f"❌ The shop can only be used in {shop_channel.mention}.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ A shop channel has been configured, but I couldn't find it. Please contact an administrator.",
                    ephemeral=True
                )
            return
        # --- End of check ---

        await interaction.response.defer()
        view = ShopView(self.bot, interaction.user.id, interaction.guild.id)
        embed = await view.build_embed_and_components()
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCog(bot))

