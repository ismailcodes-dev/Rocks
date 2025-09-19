💎 Rocks - The Ultimate Discord Economy Bot
Rocks is a powerful, highly configurable Discord bot designed to build a thriving and interactive community. It features a robust economy, a user-driven creator marketplace, a comprehensive leveling system with tiered roles, and much more. This bot is the all-in-one solution for boosting server engagement.
This project also includes a companion website with a live, dynamic leaderboard that connects directly to the bot's database via a secure API.
✨ Core Features
* Advanced Economy: A dynamic currency system where users earn coins for chatting, streaming, and claiming daily rewards. Includes daily streaks that provide a luck multiplier for better rewards.
* Creator Marketplace: Empower your members! Users with a "Creator" role can upload their own digital products (like project files, overlays, etc.) to a server-wide shop and earn an 80% commission from every sale.
* Tiered Role System: A complete rank system to reward your most active members. As users level up, they automatically unlock the Elite, Master, and Supreme roles, each granting significant perks like:
   * Increased Coin & XP multipliers (up to 2x)
   * Daily coin bonuses
   * Shop discounts (up to 10%)
   * An exclusive /bumpitem command for Supreme members to promote their shop items.
* Automatic Role Management:
   * Assign a default role to all new members on join.
   * Automatically promote members to rank roles when they reach level 50, 75, and 100.
   * Clean up user data from the database when a member leaves.
* Giveaway System: A full-featured giveaway system for admins. Easily create timed giveaways with multiple winners, an interactive "Join" button, and automatic prize distribution.
* Full Configurability: Server admins have complete control via simple slash commands. Set up dedicated channels for the shop, purchase logs, and item uploads. Configure which roles have admin and creator permissions.
* Live Website Integration: Includes a separate Flask API to securely serve bot data to a public website, featuring a dynamic, real-time server leaderboard.
🚀 Getting Started
Follow these steps to get your own instance of the Rocks bot running.
1. Prerequisites
* Python 3.10 or higher
* A Discord Bot Token (How to get one)
2. Installation
1. Clone the repository:
git clone [https://github.com/your-username/Rocks.git](https://github.com/your-username/Rocks.git)
cd Rocks

2. Create a virtual environment (recommended):
python -m venv .venv
# On Windows
.venv\Scripts\activate
# On macOS/Linux
source .venv/bin/activate

3. Install the required packages:
The bot and the API have separate requirements.
# For the Discord Bot
pip install -r requirements.txt 

# For the Website API (if you plan to run it)
pip install -r requirements-api.txt 

(Note: You will need to create a requirements.txt for your bot and a requirements-api.txt for the Flask server.)
3. Configuration
   1. Create a .env file in the main project directory.
   2. Add your Discord bot token to it like this:
DISCORD_BOT_TOKEN=YourActualBotTokenHere

   3. Run the main bot file (e.g., app.py):
python app.py

4. Basic Bot Setup (in Discord)
Once the bot is online, you must configure it as a server administrator.
      * Set up channels:/config setup
Follow the prompts to set your shop channel, log channels, etc.
      * Set up roles:/config addcreatorrole <role>
/config setrankrole elite <role>
/config setrankrole master <role>
/config setrankrole supreme <role>
      * Sync roles for existing members:/syncranks and /synccreators
Run these commands once to give roles to members who already meet the level requirements.
💻 Technology Stack
         * Bot Framework: discord.py
         * Database: SQLite3 for economy and shop data.
         * Web API: Flask
         * Website Frontend: HTML, Tailwind CSS, JavaScript