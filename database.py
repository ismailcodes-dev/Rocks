import sqlite3
import functools
from discord.ext import commands
import time
import os

class DatabaseManager:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy_db_path = "economy.db"
        self.shop_db_path = "shop.db"
        self._init_sync()

    def _run_sync(self, func, *args, **kwargs):
        partial_func = functools.partial(func, *args, **kwargs)
        return self.bot.loop.run_in_executor(None, partial_func)

    def _init_sync(self):
        with sqlite3.connect(self.economy_db_path) as con:
            cur = con.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,
                    balance INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
                    last_daily TEXT, daily_streak INTEGER DEFAULT 0,
                    last_coin_claim REAL DEFAULT 0, last_xp_claim REAL DEFAULT 0,
                    daily_spam_count INTEGER DEFAULT 0,
                    daily_stream_coins INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            # --- NEW: Add column for bump command cooldown ---
            try:
                cur.execute("ALTER TABLE users ADD COLUMN last_bump_timestamp REAL DEFAULT 0")
            except sqlite3.OperationalError:
                pass # Column already exists
        print(f"Economy database initialized successfully at: {self.economy_db_path}")

        with sqlite3.connect(self.shop_db_path) as con:
            cur = con.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL, item_name TEXT NOT NULL, application TEXT NOT NULL,
                    category TEXT NOT NULL, price INTEGER NOT NULL, product_link TEXT NOT NULL,
                    screenshot_link TEXT, screenshot_link_2 TEXT, screenshot_link_3 TEXT
                )
            """)
            try:
                cur.execute("ALTER TABLE items ADD COLUMN purchase_count INTEGER DEFAULT 0")
                cur.execute("ALTER TABLE items ADD COLUMN upload_timestamp REAL DEFAULT 0")
                cur.execute("ALTER TABLE items ADD COLUMN is_featured INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
        print(f"Shop database initialized successfully at: {self.shop_db_path}")

    # ... (get_user_data, update_user_data, delete_user_data, etc. are mostly unchanged)
    def _get_user_data_sync(self, user_id: int, guild_id: int):
        with sqlite3.connect(self.economy_db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT * FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
            user_data = cur.fetchone()
            if not user_data:
                cur.execute("INSERT INTO users (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))
                con.commit()
                cur.execute("SELECT * FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
                user_data = cur.fetchone()
            return dict(user_data)

    async def get_user_data(self, user_id: int, guild_id: int):
        return await self._run_sync(self._get_user_data_sync, user_id, guild_id)

    def _update_user_data_sync(self, user_id: int, guild_id: int, data: dict):
        with sqlite3.connect(self.economy_db_path) as con:
            cur = con.cursor()
            set_clause = ", ".join([f"{key} = ?" for key in data.keys()])
            values = list(data.values()) + [user_id, guild_id]
            query = f"UPDATE users SET {set_clause} WHERE user_id = ? AND guild_id = ?"
            cur.execute(query, tuple(values))
            con.commit()

    async def update_user_data(self, user_id: int, guild_id: int, data: dict):
        await self._run_sync(self._update_user_data_sync, user_id, guild_id, data)

    def _delete_user_data_sync(self, user_id: int, guild_id: int):
        with sqlite3.connect(self.economy_db_path) as con:
            cur = con.cursor()
            cur.execute("DELETE FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
            con.commit()

    async def delete_user_data(self, user_id: int, guild_id: int):
        await self._run_sync(self._delete_user_data_sync, user_id, guild_id)

    def _add_item_to_shop_sync(self, creator_id, guild_id, item_name, application, category, price, product_link, screenshot_link, screenshot_link_2, screenshot_link_3):
        with sqlite3.connect(self.shop_db_path) as con:
            cur = con.cursor()
            upload_timestamp = time.time()
            cur.execute("INSERT INTO items (creator_id, guild_id, item_name, application, category, price, product_link, screenshot_link, screenshot_link_2, screenshot_link_3, upload_timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",(creator_id, guild_id, item_name, application, category, price, product_link, screenshot_link, screenshot_link_2, screenshot_link_3, upload_timestamp))
            con.commit()

    async def add_item_to_shop(self, creator_id, guild_id, item_name, application, category, price, product_link, screenshot_link, screenshot_link_2, screenshot_link_3):
        await self._run_sync(self._add_item_to_shop_sync, creator_id, guild_id, item_name, application, category, price, product_link, screenshot_link, screenshot_link_2, screenshot_link_3)

    # --- NEW: Function to get all items a specific user has created ---
    def _get_items_by_creator_sync(self, creator_id: int, guild_id: int):
        with sqlite3.connect(self.shop_db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT * FROM items WHERE creator_id = ? AND guild_id = ? ORDER BY upload_timestamp DESC", (creator_id, guild_id))
            return [dict(row) for row in cur.fetchall()]

    async def get_items_by_creator(self, creator_id: int, guild_id: int):
        return await self._run_sync(self._get_items_by_creator_sync, creator_id, guild_id)

    # --- NEW: Function to update an item's timestamp to now ---
    def _bump_item_sync(self, item_id: int):
        with sqlite3.connect(self.shop_db_path) as con:
            cur = con.cursor()
            new_timestamp = time.time()
            cur.execute("UPDATE items SET upload_timestamp = ? WHERE item_id = ?", (new_timestamp, item_id))
            con.commit()

    async def bump_item(self, item_id: int):
        await self._run_sync(self._bump_item_sync, item_id)
        
    # ... (rest of the file is unchanged)
    def _increment_purchase_count_sync(self, item_id: int, guild_id: int):
        with sqlite3.connect(self.shop_db_path) as con:
            cur = con.cursor()
            cur.execute("UPDATE items SET purchase_count = purchase_count + 1 WHERE item_id = ? AND guild_id = ?", (item_id, guild_id))
            con.commit()

    async def increment_purchase_count(self, item_id: int, guild_id: int):
        await self._run_sync(self._increment_purchase_count_sync, item_id, guild_id)
        
    def _get_item_details_sync(self, item_id, guild_id):
        with sqlite3.connect(self.shop_db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT * FROM items WHERE item_id = ? AND guild_id = ?", (item_id, guild_id))
            item = cur.fetchone()
            return dict(item) if item else None

    async def get_item_details(self, item_id, guild_id):
        return await self._run_sync(self._get_item_details_sync, item_id, guild_id)

    def _delete_item_sync(self, item_id, guild_id):
        with sqlite3.connect(self.shop_db_path) as con:
            cur = con.cursor()
            cur.execute("DELETE FROM items WHERE item_id = ? AND guild_id = ?", (item_id, guild_id))
            con.commit()

    async def delete_item(self, item_id, guild_id):
        await self._run_sync(self._delete_item_sync, item_id, guild_id)

    def _get_all_users_in_guild_sync(self, guild_id: int):
        with sqlite3.connect(self.economy_db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT * FROM users WHERE guild_id = ?", (guild_id,))
            return [dict(row) for row in cur.fetchall()]

    async def get_all_users_in_guild(self, guild_id: int):
        return await self._run_sync(self._get_all_users_in_guild_sync, guild_id)
        
    def _get_shop_items_sync(self, guild_id, order_by, limit=None):
        with sqlite3.connect(self.shop_db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            if order_by not in ["purchase_count", "upload_timestamp", "item_name"]: order_by = "upload_timestamp"
            order_direction = "ASC" if order_by == "item_name" else "DESC"
            query = f"SELECT * FROM items WHERE guild_id = ? ORDER BY {order_by} {order_direction}"
            params = [guild_id]
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            cur.execute(query, tuple(params))
            return [dict(row) for row in cur.fetchall()]

    async def get_new_arrivals(self, guild_id, limit=5):
        return await self._run_sync(self._get_shop_items_sync, guild_id, "upload_timestamp", limit)
    
    async def get_all_items(self, guild_id):
        return await self._run_sync(self._get_shop_items_sync, guild_id, "item_name")

    def _get_leaderboard_sync(self, guild_id: int, limit: int = 10):
        with sqlite3.connect(self.economy_db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            query = "SELECT user_id, level, xp, balance FROM users WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT ?"
            cur.execute(query, (guild_id, limit))
            return [dict(row) for row in cur.fetchall()]

    async def get_leaderboard(self, guild_id: int, limit: int = 10):
        return await self._run_sync(self._get_leaderboard_sync, guild_id, limit)

    def _get_featured_item_sync(self, guild_id):
        with sqlite3.connect(self.shop_db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT * FROM items WHERE guild_id = ? AND is_featured = 1 LIMIT 1", (guild_id,))
            item = cur.fetchone()
            return dict(item) if item else None

    async def get_featured_item(self, guild_id):
        return await self._run_sync(self._get_featured_item_sync, guild_id)

    def _set_featured_item_sync(self, item_id, guild_id):
        with sqlite3.connect(self.shop_db_path) as con:
            cur = con.cursor()
            cur.execute("UPDATE items SET is_featured = 0 WHERE guild_id = ?", (guild_id,))
            cur.execute("UPDATE items SET is_featured = 1 WHERE item_id = ? AND guild_id = ?", (item_id, guild_id))
            con.commit()
            
    async def set_featured_item(self, item_id, guild_id):
        await self._run_sync(self._set_featured_item_sync, item_id, guild_id)

    def _search_items_sync(self, guild_id, query):
        with sqlite3.connect(self.shop_db_path) as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT item_id, item_name, price FROM items WHERE guild_id = ? AND item_name LIKE ?", (guild_id, f'%{query}%'))
            return [dict(row) for row in cur.fetchall()]

    async def search_items(self, guild_id, query):
        return await self._run_sync(self._search_items_sync, guild_id, query)

