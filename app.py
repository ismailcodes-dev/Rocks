import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import database # Import the database file

# --- SETUP ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- BOT INITIALIZATION ---
# We create a custom bot class to attach our database manager to it.
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        # FIX 1: Add the voice_states intent for the streaming cog to work
        intents.voice_states = True 
        
        super().__init__(command_prefix="/", intents=intents)
        # Attach the database manager to the bot instance
        self.db = database.DatabaseManager(self)

    async def on_ready(self):
        """Event that runs when the bot is online and all cogs are loaded."""
        print(f'Logged in as {self.user.name}')
        print(f'Discord.py Version: {discord.__version__}')
        try:
            # Sync commands after all cogs are loaded
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

bot = MyBot()

# --- MAIN FUNCTION ---
async def main():
    """The main function to run the bot."""
    cog_folder = "cogs"
    
    async with bot:
        # Load all .py files from the cogs folder
        for filename in os.listdir(cog_folder):
            # FIX 2: Add a check to ignore the __init__.py file
            if filename.endswith(".py") and filename != "__init__.py":
                try:
                    await bot.load_extension(f"{cog_folder}.{filename[:-3]}")
                    print(f"Loaded cog: {filename}")
                except Exception as e:
                    print(f"Failed to load cog {filename}: {e}")
        
        # Start the bot
        await bot.start(BOT_TOKEN)

# --- RUN THE BOT ---
if __name__ == "__main__":
    if BOT_TOKEN is None:
        print("Error: BOT_TOKEN environment variable not found.")
        print("Please create a .env file and add your bot token.")
    else:
        asyncio.run(main())