import discord
from discord.ext import commands
from discord import app_commands
import time
import random
from .channel_config import get_guild_settings

def calculate_luck(streak: int) -> float:
    luck_multiplier = 1 + (0.5 * (streak / 7))
    return min(luck_multiplier, 10.0)

class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # --- FIX: Changed message.interaction to message.interaction_metadata ---
        if message.interaction_metadata is not None or message.author.bot or not message.guild:
            return

        user_id = message.author.id
        guild_id = message.guild.id
        current_time = time.time()
        
        try:
            player = await self.bot.db.get_user_data(user_id, guild_id)
            data_to_update = {}
            
            if current_time - player['last_coin_claim'] > 25:
                luck_multiplier = calculate_luck(player['daily_streak'])
                max_coins = 20 + (player['level'] * 5)
                low_tier_cap = int(max_coins * 0.80)
                high_tier_chance = min(0.05 * luck_multiplier, 1.0)
                coins_earned = random.randint(low_tier_cap + 1, max_coins) if random.random() < high_tier_chance else random.randint(1, low_tier_cap)
                data_to_update['balance'] = player['balance'] + coins_earned
                data_to_update['last_coin_claim'] = current_time

            if current_time - player['last_xp_claim'] > 20:
                luck_multiplier = calculate_luck(player['daily_streak'])
                max_xp = 25 + (player['level'] * 5)
                low_tier_cap = int(max_xp * 0.80)
                high_tier_chance = min(0.20 * luck_multiplier, 1.0)
                xp_earned = random.randint(low_tier_cap + 1, max_xp) if random.random() < high_tier_chance else random.randint(1, low_tier_cap)
                new_xp = player['xp'] + xp_earned
                xp_needed = 100 + (player['level'] * 50)
                
                if new_xp >= xp_needed:
                    new_level = player['level'] + 1
                    xp_after_levelup = new_xp - xp_needed
                    data_to_update['xp'] = xp_after_levelup
                    data_to_update['level'] = new_level

                    guild_settings = get_guild_settings(message.guild.id)
                    level_up_channel_id = guild_settings.get("LEVEL_UP_CHANNEL_ID")
                    target_channel = self.bot.get_channel(level_up_channel_id) if level_up_channel_id else message.channel
                    
                    if target_channel:
                         await target_channel.send(f"🎉 Congratulations {message.author.mention}, you have reached **Level {new_level}**!")
                    
                    if new_level >= 25:
                        veteran_role_id = guild_settings.get("VETERAN_ROLE_ID")
                        upload_channel_id = guild_settings.get("UPLOAD_CHANNEL_ID")
                        
                        if veteran_role_id:
                            member = message.guild.get_member(message.author.id)
                            veteran_role = message.guild.get_role(veteran_role_id)
                            if member and veteran_role and veteran_role not in member.roles:
                                try:
                                    await member.add_roles(veteran_role, reason="Reached Level 25")
                                    
                                    dm_message = (
                                        f"Congratulations! You've been promoted to **{veteran_role.name}** in **{message.guild.name}**.\n\n"
                                        f"You can now upload your items to the store using the `/upd` command"
                                    )
                                    if upload_channel_id:
                                        dm_message += f" in the <#{upload_channel_id}> channel."
                                    else:
                                        dm_message += "."
                                    
                                    await member.send(dm_message)

                                except discord.Forbidden:
                                    print(f"Could not add Veteran role or DM {member.display_name}.")
                else:
                    data_to_update['xp'] = new_xp
                data_to_update['last_xp_claim'] = current_time

            if data_to_update:
                await self.bot.db.update_user_data(user_id, guild_id, data_to_update)
        except Exception as e:
            print(f"Error in on_message economy processing for {message.author.name}: {e}")

    @app_commands.command(name="balance", description="Check your current coin balance.")
    async def balance(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        embed = discord.Embed(title="💰 Your Balance", description=f"You currently have **{player['balance']:,}** coins.", color=discord.Color.gold())
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="lvl", description="Check your current level and XP.")
    async def lvl(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        level, xp = player['level'], player['xp']
        xp_needed = 100 + (level * 50)
        embed = discord.Embed(title="📈 Your Level", color=discord.Color.blue())
        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        embed.add_field(name="XP", value=f"**{xp:,} / {xp_needed:,}**", inline=True)
        progress = min(xp / xp_needed, 1.0)
        bar = '🟩' * int(20 * progress) + '⬛' * (20 - int(20 * progress))
        embed.add_field(name="Progress", value=f"`{bar}`", inline=False)
        await interaction.followup.send(embed=embed)
        
    @app_commands.command(name="profile", description="View your (or another user's) complete profile.")
    @app_commands.describe(user="The user whose profile you want to view (optional).")
    async def profile(self, interaction: discord.Interaction, user: discord.User = None):
        target_user = user or interaction.user
        await interaction.response.defer(ephemeral=False)
        
        player = await self.bot.db.get_user_data(target_user.id, interaction.guild.id)
        level, xp, balance, streak = player['level'], player['xp'], player['balance'], player['daily_streak']
        xp_needed = 100 + (level * 50)
        
        embed = discord.Embed(title=f"👤 Profile for {target_user.display_name}", color=target_user.color)
        embed.set_thumbnail(url=target_user.display_avatar.url)
        
        embed.add_field(name="💰 Balance", value=f"**{balance:,}** coins", inline=True)
        embed.add_field(name="🔥 Daily Streak", value=f"**{streak}** days", inline=True)
        embed.add_field(name="✨ Luck", value=f"**{calculate_luck(streak):.2f}x** multiplier", inline=True)
        
        embed.add_field(name="📈 Level", value=f"**{level}**", inline=False)
        embed.add_field(name="📊 XP", value=f"**{xp:,} / {xp_needed:,}**", inline=True)
        
        progress = min(xp / xp_needed, 1.0) if xp_needed > 0 else 0
        bar = '🟩' * int(20 * progress) + '⬛' * (20 - int(20 * progress))
        embed.add_field(name="Progress to Next Level", value=f"`{bar}`", inline=False)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="pay", description="Send coins to another user.")
    @app_commands.describe(recipient="The user you want to send coins to.", amount="The amount of coins to send.")
    async def pay(self, interaction: discord.Interaction, recipient: discord.User, amount: int):
        await interaction.response.defer(ephemeral=True)

        if amount <= 0:
            await interaction.followup.send("❌ You must send a positive amount of coins.", ephemeral=True); return
        if recipient.id == interaction.user.id:
            await interaction.followup.send("❌ You cannot send coins to yourself.", ephemeral=True); return
        if recipient.bot:
            await interaction.followup.send("❌ You cannot send coins to a bot.", ephemeral=True); return

        sender_data = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        if sender_data['balance'] < amount:
            await interaction.followup.send(f"❌ You don't have enough coins! You only have **{sender_data['balance']:,}** coins.", ephemeral=True); return

        recipient_data = await self.bot.db.get_user_data(recipient.id, interaction.guild.id)
        
        await self.bot.db.update_user_data(interaction.user.id, interaction.guild.id, {"balance": sender_data['balance'] - amount})
        await self.bot.db.update_user_data(recipient.id, interaction.guild.id, {"balance": recipient_data['balance'] + amount})

        embed = discord.Embed(
            title="💸 Transaction Successful",
            description=f"{interaction.user.mention} sent **{amount:,}** coins to {recipient.mention}.",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

    @app_commands.command(name="droprates", description="View your current drop rates for coins and XP.")
    async def droprates(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        level, streak = player['level'], player['daily_streak']
        luck_multiplier = calculate_luck(streak)
        max_coins = 20 + (level * 5); base_high_tier_chance_coin = 0.05
        final_high_tier_chance_coin = min(base_high_tier_chance_coin * luck_multiplier, 1.0)
        max_xp = 25 + (level * 5); base_high_tier_chance_xp = 0.20
        final_high_tier_chance_xp = min(base_high_tier_chance_xp * luck_multiplier, 1.0)
        embed = discord.Embed(title="💧 Your Drop Rates", description=f"Your rewards are based on your **Level {level}** and **{luck_multiplier:.2f}x Luck Multiplier**.", color=discord.Color.teal())
        embed.add_field(name="💰 Coin Drops", value=f"**Range:** 1 - {max_coins} coins\n**High-Tier Chance:** {final_high_tier_chance_coin:.1%}", inline=True)
        embed.add_field(name="📈 XP Gains", value=f"**Range:** 1 - {max_xp} XP\n**High-Tier Chance:** {final_high_tier_chance_xp:.1%}", inline=True)
        embed.set_footer(text="Increase your level and daily streak to improve your rewards!")
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="leaderboard", description="View the server's top members by level.")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        try:
            top_users = await self.bot.db.get_leaderboard(interaction.guild.id, limit=10)

            if not top_users:
                await interaction.followup.send("There are no users to rank on the leaderboard yet!")
                return

            embed = discord.Embed(
                title=f"🏆 Leaderboard for {interaction.guild.name}",
                description="Top members based on their level and XP.",
                color=discord.Color.gold()
            )

            leaderboard_text = ""
            rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉"}

            for i, user_data in enumerate(top_users, 1):
                user_id = user_data['user_id']
                level = user_data['level']
                balance = user_data['balance']
                
                member = interaction.guild.get_member(user_id)
                user_name = member.mention if member else f"*User Left (ID: {user_id})*"
                
                rank = rank_emojis.get(i, f"**{i}.**")
                leaderboard_text += f"{rank} {user_name} - **Level {level}** | {balance:,} coins\n"

            embed.description = leaderboard_text
            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Error in /leaderboard command: {e}")
            await interaction.followup.send("An error occurred while fetching the leaderboard.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))

