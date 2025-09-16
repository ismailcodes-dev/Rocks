# cogs/streaks.py

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone

# --- Helper Functions ---

def calculate_luck(streak: int) -> float:
    """Calculates the luck multiplier based on the daily streak."""
    return min(1 + (0.5 * (streak // 7)), 10.0)

def format_timedelta(td: timedelta) -> str:
    """Formats a timedelta object into a human-readable string."""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        
    return ", ".join(parts) if parts else "now"

# --- Cog Class ---

class StreaksCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')

    @app_commands.command(name="daily", description="Claim your daily reward.")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        try:
            player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
            
            current_time_utc = datetime.now(timezone.utc)
            today_utc = current_time_utc.date()
            
            last_claim_str = player.get('last_daily')
            last_claim_time = None

            # --- NEW: Try to parse the full timestamp ---
            if last_claim_str:
                try:
                    # New format: '2025-08-25T18:46:15.123456+00:00'
                    last_claim_time = datetime.fromisoformat(last_claim_str)
                except ValueError:
                    # Fallback for old date-only format: '2025-08-25'
                    last_claim_time = datetime.strptime(last_claim_str, '%Y-%m-%d')

            # Check if the user has already claimed today (in UTC)
            if last_claim_time and last_claim_time.date() == today_utc:
                # --- NEW: Calculate time remaining until next UTC day ---
                next_claim_time = datetime.combine(today_utc + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
                time_left = next_claim_time - current_time_utc
                
                await interaction.followup.send(
                    f"<:wtf:1403067096782340167>. Wait for **{format_timedelta(time_left)}**.",
                    ephemeral=True
                )
                return

            # Determine if the streak should continue or be reset to 1
            new_streak = 1
            if last_claim_time:
                if last_claim_time.date() == today_utc - timedelta(days=1):
                    new_streak = player['daily_streak'] + 1
            
            # Calculate reward
            level_bonus = (player['level'] // 50) * 50
            total_reward = min(50 + level_bonus, 500)
            new_balance = player['balance'] + total_reward
            
            # Prepare data for database update
            data_to_update = {
                "balance": new_balance,
                "daily_streak": new_streak,
                # --- NEW: Store the full ISO format timestamp ---
                "last_daily": current_time_utc.isoformat(),
                "daily_spam_count": 0
            }
            
            await self.bot.db.update_user_data(interaction.user.id, interaction.guild.id, data_to_update)

            # Send confirmation message
            embed = discord.Embed(
                title="✅ Daily Reward Claimed!", 
                description=f"You received **{total_reward:,}** coins!", 
                color=discord.Color.green()
            )
            embed.add_field(name="New Balance", value=f"{new_balance:,} coins")
            embed.add_field(name="Current Streak", value=f"🔥 {new_streak} days")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in /daily command: {e}")
            await interaction.followup.send("An error occurred while processing your daily reward. Please try again later.", ephemeral=True)

    @app_commands.command(name="streak", description="Check your current daily streak and luck bonus.")
    async def streak(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        
        current_streak = player.get('daily_streak', 0)
        luck = calculate_luck(current_streak)

        embed = discord.Embed(
            title="🔥 Your Daily Streak",
            description=f"You are currently on a **{current_streak}-day** streak!",
            color=discord.Color.orange()
        )
        embed.add_field(name="Luck Bonus", value=f"This gives you a **{luck:.2f}x** luck multiplier on chat rewards.", inline=False)
        embed.add_field(name="How to Keep It", value="Use the `/daily` command every 24 hours to maintain your streak.", inline=False)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="luck", description="Check your current luck boost from your streak.")
    async def luck(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        
        current_streak = player.get('daily_streak', 0)
        luck = calculate_luck(current_streak)

        embed = discord.Embed(
            title="✨ Your Luck Stats", 
            description=f"Your luck multiplier is **{luck:.2f}x** based on your **{current_streak}-day** streak.", 
            color=discord.Color.purple()
        )
        embed.set_footer(text="A higher luck multiplier increases your chances of better rewards from chatting.")
        await interaction.followup.send(embed=embed)

# --- Setup Function ---

async def setup(bot: commands.Bot):
    """Adds the cog to the bot."""
    await bot.add_cog(StreaksCog(bot))