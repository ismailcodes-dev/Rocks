# cogs/games.py

import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio

# --- Blackjack Game View (Standard Fair Rules) ---
class BlackjackView(discord.ui.View):
    def __init__(self, bot, author, player_data, bet):
        super().__init__(timeout=120)
        self.bot = bot
        self.author = author
        self.player_data = player_data
        self.bet = bet

        self.deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
        random.shuffle(self.deck)

        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return False
        return True

    def calculate_hand_value(self, hand):
        value = sum(hand)
        aces = hand.count(11)
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    async def update_message(self, interaction: discord.Interaction):
        player_score = self.calculate_hand_value(self.player_hand)
        embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.dark_green())
        embed.set_author(name=f"{self.author.display_name}'s game")
        embed.add_field(name="Your Hand", value=f"{' '.join(map(str, self.player_hand))}  (**{player_score}**)", inline=False)
        embed.add_field(name="Dealer's Hand", value=f"{self.dealer_hand[0]} ?", inline=False)
        await interaction.edit_original_response(embed=embed, view=self)

    async def handle_game_end(self, interaction, result):
        dealer_score = self.calculate_hand_value(self.dealer_hand)
        
        if result == "win":
            new_balance = self.player_data['balance'] + self.bet
            title = "🎉 You Won! 🎉"
            desc = f"You won **{self.bet*2:,}** coins!"
        elif result == "blackjack":
            new_balance = self.player_data['balance'] + int(self.bet * 1.5)
            title = "✨ BLACKJACK! ✨"
            desc = f"You won **{int(self.bet * 2.5):,}** coins!"
        elif result == "push":
            new_balance = self.player_data['balance']
            title = "🤝 Push 🤝"
            desc = "It's a tie! Your bet has been returned."
        else: # loss
            new_balance = self.player_data['balance'] - self.bet
            title = "💔 You Lost 💔"
            desc = f"The dealer won. You lost **{self.bet:,}** coins."
            
        await self.bot.db.update_user_data(self.author.id, self.author.guild.id, {"balance": new_balance})
        
        embed = discord.Embed(title=title, description=desc, color=discord.Color.blue())
        embed.add_field(name="Your Hand", value=f"{' '.join(map(str, self.player_hand))} (**{self.calculate_hand_value(self.player_hand)}**)", inline=True)
        embed.add_field(name="Dealer's Hand", value=f"{' '.join(map(str, self.dealer_hand))} (**{dealer_score}**)", inline=True)
        embed.set_footer(text=f"New Balance: {new_balance:,}")

        await interaction.edit_original_response(embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.player_hand.append(self.deck.pop())
        player_score = self.calculate_hand_value(self.player_hand)
        
        if player_score > 21:
            await self.handle_game_end(interaction, "loss")
        else:
            await self.update_message(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        player_score = self.calculate_hand_value(self.player_hand)
        dealer_score = self.calculate_hand_value(self.dealer_hand)
        
        while dealer_score < 17:
            self.dealer_hand.append(self.deck.pop())
            dealer_score = self.calculate_hand_value(self.dealer_hand)
            
        if dealer_score > 21 or player_score > dealer_score:
            await self.handle_game_end(interaction, "win")
        elif player_score == dealer_score: # MODIFIED: Ties are now a push
            await self.handle_game_end(interaction, "push")
        else:
            await self.handle_game_end(interaction, "loss")


class GamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')

    # --- REBALANCED SLOT MACHINE (~52% Win Rate) ---
    @app_commands.command(name="slots", description="Play the slot machine for a chance to win big!")
    @app_commands.describe(bet="The amount of coins you want to bet.")
    async def slots(self, interaction: discord.Interaction, bet: int):
        await interaction.response.defer()
        player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        if bet <= 0:
            await interaction.followup.send("❌ You must bet a positive amount of coins.", ephemeral=True); return
        if player['balance'] < bet:
            await interaction.followup.send(f"❌ You don't have enough coins! Your balance is **{player['balance']:,}**.", ephemeral=True); return

        # MODIFIED: Returned to 5 symbols for a natural ~52% win rate
        emojis = ["🍒", "🍊", "🔔", "💎", "💰"] 
        reels = [random.choice(emojis) for _ in range(3)]
        result_str = " | ".join(reels)
        
        payout = 0
        if reels[0] == reels[1] == reels[2]: # Three of a kind
            if reels[0] == "💰": payout = bet * 8
            elif reels[0] == "💎": payout = bet * 7
            elif reels[0] == "🔔": payout = bet * 6
            else: payout = bet * 4
        elif reels[0] == reels[1] or reels[1] == reels[2]: # Two of a kind (adjacent)
            payout = int(bet * 1.5)
        elif reels[0] == reels[2]: # Two of a kind (corners)
            payout = bet # Return the bet

        new_balance = player['balance'] - bet + payout
        await self.bot.db.update_user_data(interaction.user.id, interaction.guild.id, {"balance": new_balance})
        embed = discord.Embed(title="🎰 Slot Machine 🎰", color=discord.Color.gold())
        embed.set_author(name=f"{interaction.user.display_name}'s game")
        embed.add_field(name="Result", value=f"**[ {result_str} ]**", inline=False)
        
        if payout > bet:
            embed.description = f"🎉 **YOU WON!** 🎉\nYou won **{payout:,}** coins!"
            embed.color = discord.Color.green()
        elif payout == bet:
            embed.description = f"🙌 **PUSH!** 🙌\nYou got your bet of **{bet:,}** back!"
            embed.color = discord.Color.light_grey()
        else:
            embed.description = f"💔 **You lost.** Better luck next time!"
            embed.color = discord.Color.red()
            
        embed.set_footer(text=f"You bet {bet:,} | New Balance: {new_balance:,}")
        await interaction.followup.send(embed=embed)


    # --- MODIFIED COIN FLIP (52% Win Rate) ---
    @app_commands.command(name="coinflip", description="Bet on a coin flip (player favored).")
    @app_commands.describe(bet="The amount of coins you want to bet.", choice="Your choice: heads or tails.")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Heads", value="heads"),
        app_commands.Choice(name="Tails", value="tails")
    ])
    async def coinflip(self, interaction: discord.Interaction, bet: int, choice: str):
        await interaction.response.defer()
        player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        if bet <= 0:
            await interaction.followup.send("❌ You must bet a positive amount of coins.", ephemeral=True); return
        if player['balance'] < bet:
            await interaction.followup.send(f"❌ You don't have enough coins! Your balance is **{player['balance']:,}**.", ephemeral=True); return

        # Rigged logic: 52% chance for the player to win
        won = random.random() < 0.52
        
        if won:
            outcome = choice.lower()
            new_balance = player['balance'] + bet
            title = "🎉 You Won! 🎉"
            color = discord.Color.green()
            description = f"The coin landed on **{outcome.title()}**. You won **{bet*2:,}** coins!"
        else:
            outcome = "tails" if choice.lower() == "heads" else "heads"
            new_balance = player['balance'] - bet
            title = "💔 You Lost 💔"
            color = discord.Color.red()
            description = f"The coin landed on **{outcome.title()}**. You lost **{bet:,}** coins."
            
        await self.bot.db.update_user_data(interaction.user.id, interaction.guild.id, {"balance": new_balance})
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_author(name=f"{interaction.user.display_name}'s coin flip")
        embed.set_footer(text=f"New Balance: {new_balance:,}")
        await interaction.followup.send(embed=embed)


    # --- Fair BLACKJACK COMMAND ---
    @app_commands.command(name="blackjack", description="Play a game of Blackjack against the bot.")
    @app_commands.describe(bet="The amount of coins to bet.")
    async def blackjack(self, interaction: discord.Interaction, bet: int):
        await interaction.response.defer()
        player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        if bet <= 0:
            await interaction.followup.send("❌ You must bet a positive amount of coins.", ephemeral=True); return
        if player['balance'] < bet:
            await interaction.followup.send(f"❌ You don't have enough coins! Your balance is **{player['balance']:,}**.", ephemeral=True); return

        view = BlackjackView(self.bot, interaction.user, player, bet)
        player_score = view.calculate_hand_value(view.player_hand)
        
        embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.dark_green())
        embed.set_author(name=f"{interaction.user.display_name}'s game")
        embed.add_field(name="Your Hand", value=f"{' '.join(map(str, view.player_hand))}  (**{player_score}**)", inline=False)
        embed.add_field(name="Dealer's Hand", value=f"{view.dealer_hand[0]} ?", inline=False)
        await interaction.followup.send(embed=embed, view=view)

        if player_score == 21:
            await view.handle_game_end(interaction, "blackjack")


    # --- ROULETTE (Unchanged) ---
    @app_commands.command(name="roulette", description="Play a game of Roulette.")
    @app_commands.describe(bet="The amount to bet.", space="The space to bet on (e.g., 'red', 'black', 'even', 'odd', or a number 0-36).")
    async def roulette(self, interaction: discord.Interaction, bet: int, space: str):
        # This function remains unchanged
        await interaction.response.defer()
        player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        if bet <= 0:
            await interaction.followup.send("❌ You must bet a positive amount of coins.", ephemeral=True); return
        if player['balance'] < bet:
            await interaction.followup.send(f"❌ You don't have enough coins! Your balance is **{player['balance']:,}**.", ephemeral=True); return
        space = space.lower()
        red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
        winning_number = random.randint(0, 36)
        payout = 0; won = False
        if space.isdigit() and 0 <= int(space) <= 36:
            if int(space) == winning_number:
                payout = bet * 35; won = True
        elif space == "red":
            if winning_number in red_numbers:
                payout = bet; won = True
        elif space == "black":
            if winning_number != 0 and winning_number not in red_numbers:
                payout = bet; won = True
        elif space == "even":
            if winning_number != 0 and winning_number % 2 == 0:
                payout = bet; won = True
        elif space == "odd":
            if winning_number % 2 != 0:
                payout = bet; won = True
        else:
            await interaction.followup.send("❌ Invalid space. Please bet on 'red', 'black', 'even', 'odd', or a number between 0 and 36.", ephemeral=True); return
        result_color = "Red" if winning_number in red_numbers else ("Green" if winning_number == 0 else "Black")
        embed = discord.Embed(title="🎡 Roulette 🎡", description=f"The ball landed on **{winning_number} ({result_color})**", color=discord.Color.dark_magenta())
        if won:
            new_balance = player['balance'] + payout
            embed.add_field(name="🎉 You Won! 🎉", value=f"Your bet on **{space.title()}** won! You get **{payout:,}** coins!")
        else:
            new_balance = player['balance'] - bet
            embed.add_field(name="💔 You Lost 💔", value=f"Your bet on **{space.title()}** lost. You lose **{bet:,}** coins.")
        await self.bot.db.update_user_data(interaction.user.id, interaction.guild.id, {"balance": new_balance})
        embed.set_footer(text=f"New Balance: {new_balance:,}")
        await interaction.followup.send(embed=embed)


    # --- MODIFIED ROCK, PAPER, SCISSORS (52% Win Rate) ---
    @app_commands.command(name="rps", description="Play Rock, Paper, Scissors (player favored).")
    @app_commands.describe(bet="The amount to bet.", choice="Your choice.")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Rock ✊", value="rock"),
        app_commands.Choice(name="Paper ✋", value="paper"),
        app_commands.Choice(name="Scissors ✌️", value="scissors")
    ])
    async def rps(self, interaction: discord.Interaction, bet: int, choice: str):
        await interaction.response.defer()
        player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        if bet <= 0:
            await interaction.followup.send("❌ You must bet a positive amount of coins.", ephemeral=True); return
        if player['balance'] < bet:
            await interaction.followup.send(f"❌ You don't have enough coins! Your balance is **{player['balance']:,}**.", ephemeral=True); return
        
        # Rigged logic: 52% win, 24% tie, 24% lose
        chance = random.random()
        
        if chance < 0.52: # Player wins
            if choice == "rock": bot_choice = "scissors"
            elif choice == "paper": bot_choice = "rock"
            else: bot_choice = "paper"
        elif chance < 0.76: # Player ties (0.52 + 0.24)
            bot_choice = choice
        else: # Player loses
            if choice == "rock": bot_choice = "paper"
            elif choice == "paper": bot_choice = "scissors"
            else: bot_choice = "rock"

        winner = None 
        if choice == bot_choice: winner = None
        elif (choice == "rock" and bot_choice == "scissors") or \
             (choice == "paper" and bot_choice == "rock") or \
             (choice == "scissors" and bot_choice == "paper"):
            winner = True
        else: winner = False

        if winner is True:
            new_balance = player['balance'] + bet
            result_text = f"You won! You chose **{choice.title()}** and I chose **{bot_choice.title()}**."
        elif winner is False:
            new_balance = player['balance'] - bet
            result_text = f"You lost! You chose **{choice.title()}** and I chose **{bot_choice.title()}**."
        else: # Tie
            new_balance = player['balance']
            result_text = f"It's a tie! We both chose **{choice.title()}**."
            
        await self.bot.db.update_user_data(interaction.user.id, interaction.guild.id, {"balance": new_balance})
        embed = discord.Embed(title="✊ Rock, Paper, Scissors ✌️", description=result_text, color=discord.Color.orange())
        embed.set_footer(text=f"New Balance: {new_balance:,}")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GamesCog(bot))