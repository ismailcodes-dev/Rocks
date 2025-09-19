import discord
from discord.ext import commands
from discord import app_commands, ui
from .channel_config import get_guild_settings, get_member_perks
import math
import traceback

COMMISSION_RATE = 0.80

class PurchaseView(ui.View):
    def __init__(self, bot: commands.Bot, item_id: int, original_price: int, final_price: int, discount: float):
        super().__init__(timeout=180)
        self.bot = bot
        self.item_id = item_id
        self.original_price = original_price
        self.final_price = final_price
        self.discount = discount

    @ui.button(label="Buy Now", style=discord.ButtonStyle.green, emoji="🛒")
    async def buy_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            item = await self.bot.db.get_item_details(self.item_id, interaction.guild.id)
            player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)

            if not item:
                return await interaction.followup.send("❌ This item seems to have been removed from the shop.", ephemeral=True)
            if player['balance'] < self.final_price:
                return await interaction.followup.send(f"❌ You don't have enough coins! You need **{self.final_price:,}** coins.", ephemeral=True)

            commission_amount = int(self.original_price * COMMISSION_RATE)
            new_balance_buyer = player['balance'] - self.final_price
            await self.bot.db.update_user_data(interaction.user.id, interaction.guild.id, {"balance": new_balance_buyer})
            
            creator_data = await self.bot.db.get_user_data(item['creator_id'], interaction.guild.id)
            new_balance_creator = creator_data['balance'] + commission_amount
            await self.bot.db.update_user_data(item['creator_id'], interaction.guild.id, {"balance": new_balance_creator})
            await self.bot.db.increment_purchase_count(self.item_id, interaction.guild.id)
            
            # ... (Purchase Log is unchanged)
            dm_desc = f"Thank you for purchasing **{item['item_name']}**."
            if self.discount > 0:
                dm_desc += f"\n\nYour rank gave you a **{self.discount:.0%} discount**, saving you **{(self.original_price - self.final_price):,}** coins!"
            
            dm_embed = discord.Embed(title="✅ Purchase Successful!", description=dm_desc, color=discord.Color.brand_green())
            dm_embed.add_field(name="Download Link", value=f"**[Click Here to Download]({item['product_link']})**")
            await interaction.user.send(embed=dm_embed)
            await interaction.followup.send("✅ Purchase complete! I've sent the download link to your DMs.", ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send("⚠️ **Purchase Failed.** I couldn't send you a DM.", ephemeral=True)
        except Exception as e:
            print(f"Error during purchase: {e}")
            await interaction.followup.send("An unexpected error occurred. Please try again.", ephemeral=True)

class SearchResultsView(ui.View):
    # ... (This class is unchanged)
    def __init__(self, bot, results):
        super().__init__(timeout=180)
        self.bot = bot
        options = [discord.SelectOption(label=f"{item['item_name'][:100]}", description=f"Price: {item['price']:,} coins", value=str(item['item_id'])) for item in results[:25]]
        self.select_menu = ui.Select(placeholder="Select an item to view details...", options=options)
        self.select_menu.callback = self.on_select
        self.add_item(self.select_menu)

    async def on_select(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item_id = int(self.select_menu.values[0])
        item = await self.bot.db.get_item_details(item_id, interaction.guild.id)
        if not item: return await interaction.followup.send("❌ This item could not be found.", ephemeral=True)
        creator = await self.bot.fetch_user(item['creator_id'])
        perks = get_member_perks(interaction.user)
        final_price = int(item['price'] * (1 - perks['shop_discount']))
        embed = discord.Embed(title=item['item_name'], color=discord.Color.from_str("#5865F2"))
        embed.set_author(name=f"Created by {creator.display_name}", icon_url=creator.display_avatar.url)
        price_str = f"**{final_price:,}** coins"
        if perks['shop_discount'] > 0:
            price_str += f" (~~{item['price']:,}~~) with your **{perks['shop_discount']:.0%}** discount!"
        embed.add_field(name="Price", value=price_str)
        if item.get('screenshot_link'): embed.set_image(url=item['screenshot_link'])
        await interaction.followup.send(embed=embed, view=PurchaseView(self.bot, item_id, item['price'], final_price, perks['shop_discount']), ephemeral=True)

class ShopView(ui.View):
    # ... (This class is mostly unchanged)
    def __init__(self, bot: commands.Bot, author_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.author_id = author_id
        self.guild_id = guild_id
        self.current_tab = "featured"
        self.current_items = []
        self.selected_index = 0
        self.items_in_view = 10

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This is not your shop session.", ephemeral=True)
            return False
        return True

    # --- UPDATED: To handle discounts on featured item quick view ---
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.data.get("custom_id", "").startswith("quick_view_"):
            await interaction.response.defer(ephemeral=True)
            item_id = int(interaction.data["custom_id"].split("_")[2])
            item = await self.bot.db.get_item_details(item_id, interaction.guild.id)
            if not item: return await interaction.followup.send("❌ Item not found.", ephemeral=True)
            creator = await self.bot.fetch_user(item['creator_id'])
            perks = get_member_perks(interaction.user)
            final_price = int(item['price'] * (1 - perks['shop_discount']))
            embed = discord.Embed(title=item['item_name'], color=discord.Color.from_str("#5865F2"))
            embed.set_author(name=f"Created by {creator.display_name}", icon_url=creator.display_avatar.url)
            price_str = f"**{final_price:,}** coins"
            if perks['shop_discount'] > 0:
                price_str += f" (~~{item['price']:,}~~) with your **{perks['shop_discount']:.0%}** discount!"
            embed.add_field(name="Price", value=price_str)
            if item.get('screenshot_link'): embed.set_image(url=item['screenshot_link'])
            await interaction.followup.send(embed=embed, view=PurchaseView(self.bot, item_id, item['price'], final_price, perks['shop_discount']), ephemeral=True)
    
    # --- UPDATED: select_item_button to pass discount info ---
    @ui.button(label="View Item", style=discord.ButtonStyle.green, custom_id="select_item", row=1)
    async def select_item_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.current_items: return
        item_data = self.current_items[self.selected_index]
        await interaction.response.defer(ephemeral=True)
        item = await self.bot.db.get_item_details(item_data['item_id'], interaction.guild.id)
        if not item: return await interaction.followup.send("❌ This item could not be found.", ephemeral=True)
        
        creator = await self.bot.fetch_user(item['creator_id'])
        perks = get_member_perks(interaction.user)
        final_price = int(item['price'] * (1 - perks['shop_discount']))

        embed = discord.Embed(title=item['item_name'], color=discord.Color.from_str("#5865F2"))
        embed.set_author(name=f"Created by {creator.display_name}", icon_url=creator.display_avatar.url)
        price_str = f"**{final_price:,}** coins"
        if perks['shop_discount'] > 0:
            price_str += f" (~~{item['price']:,}~~) with your **{perks['shop_discount']:.0%}** discount!"
        embed.add_field(name="Price", value=price_str)
        if item.get('screenshot_link'): embed.set_image(url=item['screenshot_link'])
        
        await interaction.followup.send(embed=embed, view=PurchaseView(self.bot, item['item_id'], item['price'], final_price, perks['shop_discount']), ephemeral=True)

    # ... (The rest of the file is unchanged)
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
        if self.current_tab == "new": self.current_items = await self.bot.db.get_new_arrivals(self.guild_id, limit=None)
        elif self.current_tab == "all_items": self.current_items = await self.bot.db.get_all_items(self.guild_id)
        else: self.current_items = []
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

class ShopCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')
    @app_commands.command(name="shop", description="Open the interactive marketplace.")
    async def shop(self, interaction: discord.Interaction):
        guild_settings = get_guild_settings(interaction.guild.id)
        shop_channel_id = guild_settings.get("SHOP_CHANNEL_ID")
        if shop_channel_id and interaction.channel.id != shop_channel_id:
            shop_channel = self.bot.get_channel(shop_channel_id)
            await interaction.response.send_message(f"❌ The shop can only be used in {shop_channel.mention if shop_channel else 'a missing channel'}.", ephemeral=True)
            return
        await interaction.response.defer()
        view = ShopView(self.bot, interaction.user.id, interaction.guild.id)
        await view.handle_tab_switch(interaction, "featured")
    @app_commands.command(name="search", description="Search for an item in the shop.")
    @app_commands.describe(query="What are you looking for?")
    async def search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)
        if len(query) < 3:
            await interaction.followup.send("Please enter at least 3 characters to search.", ephemeral=True)
            return
        results = await self.bot.db.search_items(interaction.guild.id, query)
        if not results:
            await interaction.followup.send(f"No items found matching `{query}`.", ephemeral=True)
            return
        embed = discord.Embed(title=f"🔎 Search Results for `{query}`", description=f"Found **{len(results)}** item(s). Please select one to view details.", color=discord.Color.from_str("#5865F2"))
        await interaction.followup.send(embed=embed, view=SearchResultsView(self.bot, results), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCog(bot))

