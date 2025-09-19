import discord
from discord.ext import commands
from discord import app_commands
import time
import random
from .channel_config import get_guild_settings, get_member_perks, PERKS # Import PERKS dictionary

class EconomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'{self.__class__.__name__} cog has been loaded.')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.interaction_metadata is not None or message.author.bot or not message.guild:
            return

        user_id = message.author.id
        guild_id = message.guild.id
        current_time = time.time()
        
        try:
            player = await self.bot.db.get_user_data(user_id, guild_id)
            perks = get_member_perks(message.author)
            data_to_update = {}
            
            if current_time - player['last_coin_claim'] > 25:
                base_coins = random.randint(5, 20)
                coins_earned = int(base_coins * perks["multiplier"])
                data_to_update['balance'] = player['balance'] + coins_earned
                data_to_update['last_coin_claim'] = current_time

            if current_time - player['last_xp_claim'] > 20:
                base_xp = random.randint(10, 25)
                xp_earned = int(base_xp * perks["multiplier"])
                new_xp = player['xp'] + xp_earned
                
                current_level = player['level']
                xp_needed = 100 + (current_level * 50)
                
                leveled_up = False
                while new_xp >= xp_needed:
                    current_level += 1
                    new_xp -= xp_needed
                    xp_needed = 100 + (current_level * 50)
                    leveled_up = True
                
                if leveled_up:
                    data_to_update['xp'] = new_xp
                    data_to_update['level'] = current_level

                    guild_settings = get_guild_settings(message.guild.id)
                    level_up_channel_id = guild_settings.get("LEVEL_UP_CHANNEL_ID")
                    target_channel = self.bot.get_channel(level_up_channel_id) or message.channel
                    await target_channel.send(f"🎉 Congratulations {message.author.mention}, you have reached **Level {current_level}**!")
                    
                    # --- UPDATED: Automatic Role Assignment with Detailed Perk DMs ---
                    roles_to_assign = {
                        50: (guild_settings.get("ELITE_ROLE_ID"), "elite"),
                        75: (guild_settings.get("MASTER_ROLE_ID"), "master"),
                        100: (guild_settings.get("SUPREME_ROLE_ID"), "supreme")
                    }
                    for level_req, (role_id, perk_key) in roles_to_assign.items():
                        if current_level >= level_req and role_id:
                            role = message.guild.get_role(role_id)
                            if role and role not in message.author.roles:
                                try:
                                    await message.author.add_roles(role, reason=f"Reached Level {level_req}")
                                    
                                    # --- NEW: Send a detailed DM with an embed ---
                                    perk_info = PERKS[perk_key]
                                    embed = discord.Embed(
                                        title="🎉 Rank Up!",
                                        description=f"Congratulations! You've been promoted to **{role.name}** in **{message.guild.name}** for reaching level {level_req}!",
                                        color=discord.Color.brand_green()
                                    )
                                    embed.add_field(name="💰 Economy Boost", value=f"You now earn **{perk_info['multiplier']:.1f}x** Coins & XP!", inline=False)
                                    embed.add_field(name="🎁 Daily Bonus", value=f"You get an extra **{perk_info['daily_bonus']:,}** coins from `/daily`.", inline=False)
                                    
                                    if perk_info['shop_discount'] > 0:
                                        embed.add_field(name="🛍️ Shop Discount", value=f"You now get a **{perk_info['shop_discount']:.0%}** discount on all shop items!", inline=False)
                                    
                                    if perk_key == "supreme":
                                         embed.add_field(name="🚀 Supreme Perk", value="You can now use the `/bumpitem` command once per week to promote your shop items!", inline=False)

                                    await message.author.send(embed=embed)

                                except (discord.Forbidden, discord.HTTPException):
                                    print(f"Failed to assign rank role or DM {message.author.name}")
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
    async def profile(self, interaction: discord.Interaction, user: discord.Member = None):
        target_user = user or interaction.user
        await interaction.response.defer(ephemeral=False)
        
        player = await self.bot.db.get_user_data(target_user.id, interaction.guild.id)
        perks = get_member_perks(target_user)
        
        level, xp, balance, streak = player['level'], player['xp'], player['balance'], player['daily_streak']
        xp_needed = 100 + (level * 50)
        
        embed = discord.Embed(title=f"{perks['flair']} Profile for {target_user.display_name}", color=target_user.color)
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.add_field(name="💰 Balance", value=f"**{balance:,}** coins", inline=True)
        embed.add_field(name="🔥 Daily Streak", value=f"**{streak}** days", inline=True)
        embed.add_field(name="✨ Multiplier", value=f"**{perks['multiplier']:.1f}x**", inline=True)
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
        if recipient.id == interaction.user.id or recipient.bot:
            await interaction.followup.send("❌ You cannot send coins to yourself or a bot.", ephemeral=True); return

        sender_data = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        sender_perks = get_member_perks(interaction.user)
        
        if amount > sender_perks['pay_limit']:
            await interaction.followup.send(f"❌ Your rank's pay limit is **{sender_perks['pay_limit']:,}** coins.", ephemeral=True); return
        if sender_data['balance'] < amount:
            await interaction.followup.send(f"❌ You don't have enough coins!", ephemeral=True); return

        recipient_data = await self.bot.db.get_user_data(recipient.id, interaction.guild.id)
        
        await self.bot.db.update_user_data(interaction.user.id, interaction.guild.id, {"balance": sender_data['balance'] - amount})
        await self.bot.db.update_user_data(recipient.id, interaction.guild.id, {"balance": recipient_data['balance'] + amount})

        embed = discord.Embed(title="💸 Transaction Successful", description=f"{interaction.user.mention} sent **{amount:,}** coins to {recipient.mention}.", color=discord.Color.green())
        await interaction.followup.send(embed=embed, ephemeral=False)

    @app_commands.command(name="droprates", description="View your current drop rates for coins and XP.")
    async def droprates(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        player = await self.bot.db.get_user_data(interaction.user.id, interaction.guild.id)
        perks = get_member_perks(interaction.user)
        embed = discord.Embed(title="💧 Your Drop Rates", description=f"Your rewards are based on your current rank.", color=discord.Color.teal())
        embed.add_field(name="💰 Coin Multiplier", value=f"**{perks['multiplier']:.1f}x**", inline=True)
        embed.add_field(name="📈 XP Multiplier", value=f"**{perks['multiplier']:.1f}x**", inline=True)
        embed.set_footer(text="Increase your rank by leveling up to improve your rewards!")
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="leaderboard", description="View the server's top members by level.")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        top_users = await self.bot.db.get_leaderboard(interaction.guild.id, limit=10)

        if not top_users:
            await interaction.followup.send("There are no users to rank on the leaderboard yet!"); return

        embed = discord.Embed(title=f"🏆 Leaderboard for {interaction.guild.name}", color=discord.Color.gold())
        leaderboard_text = ""
        rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉"}

        for i, user_data in enumerate(top_users, 1):
            member = interaction.guild.get_member(user_data['user_id'])
            if member:
                perks = get_member_perks(member)
                user_name = f"{perks['flair']} {member.mention}"
            else:
                user_name = f"*User Left (ID: {user_data['user_id']})*"
            
            rank = rank_emojis.get(i, f"**{i}.**")
            leaderboard_text += f"{rank} {user_name} - **Level {user_data['level']}**\n"

        embed.description = leaderboard_text
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))

