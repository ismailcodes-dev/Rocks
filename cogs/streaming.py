import discord
from discord.ext import commands
import datetime
import time

class StreamingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.streaming_users = {}  # Stores {user_id: start_time}

        # --- CONFIGURATION ---
        self.COINS_PER_MINUTE = 5
        self.XP_PER_MINUTE = 40
        self.DAILY_COIN_LIMIT = 500 # Max coins a user can earn from streaming per day
        self.MINIMUM_STREAM_MINUTES = 1 # User must stream for at least this many minutes to get rewards

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Ignore bots
        if member.bot:
            return

        # --- USER STARTS STREAMING ---
        if after.self_stream and not before.self_stream:
            self.streaming_users[member.id] = time.time()
            try:
                # Optionally DM the user that they are now earning rewards
                await member.send(f"🎥 You've started streaming in **{member.guild.name}**! You'll earn rewards for as long as you stream.")
            except discord.Forbidden:
                print(f"Could not DM {member.name} about starting their stream.")

        # --- USER STOPS STREAMING ---
        elif before.self_stream and not after.self_stream:
            start_time = self.streaming_users.pop(member.id, None)
            if not start_time:
                return # User was not being tracked (e.g., bot restarted while they were streaming)

            duration_minutes = int((time.time() - start_time) / 60)

            # Don't give rewards for very short streams
            if duration_minutes < self.MINIMUM_STREAM_MINUTES:
                return

            try:
                # Get user data from the database
                player = await self.bot.db.get_user_data(member.id, member.guild.id)
                
                # Check and reset daily limit if it's a new day
                today = datetime.date.today().isoformat()
                last_daily_str = player.get('last_daily')
                if last_daily_str != today:
                    player['daily_stream_coins'] = 0
                
                # Calculate rewards
                xp_earned = duration_minutes * self.XP_PER_MINUTE
                
                # Calculate coins earned, respecting the daily limit
                remaining_coins_for_day = self.DAILY_COIN_LIMIT - player.get('daily_stream_coins', 0)
                potential_coins = duration_minutes * self.COINS_PER_MINUTE
                coins_earned = max(0, min(potential_coins, remaining_coins_for_day))

                # Prepare data for database update
                data_to_update = {
                    "xp": player["xp"] + xp_earned,
                    "balance": player["balance"] + coins_earned,
                    "daily_stream_coins": player.get('daily_stream_coins', 0) + coins_earned,
                    "last_daily": today # Update the 'last_daily' field to mark the activity day
                }

                await self.bot.db.update_user_data(member.id, member.guild.id, data_to_update)
                
                # This log message is commented out to prevent console spam.
                # print(f"{member.name} streamed for {duration_minutes} minutes and earned {xp_earned} XP and {coins_earned} coins.")

                # DM the user with their rewards
                await member.send(f"🎉 Thanks for streaming! You earned **{xp_earned:,} XP** and **{coins_earned:,} coins** for your {duration_minutes}-minute stream.")

            except discord.Forbidden:
                print(f"Could not DM {member.name} about their streaming rewards.")
            except Exception as e:
                print(f"An error occurred in on_voice_state_update for {member.name}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(StreamingCog(bot))