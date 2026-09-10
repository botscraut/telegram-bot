"""Работа с базой данных (SQLite)"""
import aiosqlite
import asyncio
import os
from datetime import datetime

DB_NAME = os.getenv("DB_PATH", "shop.db")


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Пользователи
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance_usd REAL DEFAULT 0,
                balance_stars INTEGER DEFAULT 0,
                ref_code TEXT UNIQUE,
                ref_by INTEGER DEFAULT NULL,
                created_at TEXT
            )
        """)
        # Аккаунты ТГ
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT NOT NULL,
                phone TEXT NOT NULL,
                code TEXT NOT NULL,
                price_usd REAL NOT NULL,
                price_stars INTEGER NOT NULL,
                sold INTEGER DEFAULT 0,
                buyer_id INTEGER DEFAULT NULL,
                sold_at TEXT DEFAULT NULL
            )
        """)
        # Покупки
        await db.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                pay_method TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT
            )
        """)
        # Помощники (админы)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS helpers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                added_by INTEGER,
                created_at TEXT
            )
        """)
        # Настройки дизайна
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # Рефералы
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                invited_id INTEGER NOT NULL,
                created_at TEXT
            )
        """)
        # Платежи (CryptoBot)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                invoice_id TEXT,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                status TEXT DEFAULT "pending",
                created_at TEXT
            )
        """)
        # Дефолтные настройки
        await db.execute("""
            INSERT OR IGNORE INTO settings (key, value) VALUES
            ("btn_radius", "10px"),
            ("admin_visible", "1")
        """)
        await db.commit()


# ===== USERS =====
async def add_user(user_id: int, username: str, first_name: str, ref_code: str):
    async with aiosqlite.connect(DB_NAME) as db:
        now = datetime.now().isoformat()
        await db.execute(
            "INSERT OR IGNORE INTO users (id, username, first_name, ref_code, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, first_name, ref_code, now)
        )
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_balance(user_id: int, usd: float = None, stars: int = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if usd is not None:
            await db.execute("UPDATE users SET balance_usd = balance_usd + ? WHERE id = ?", (usd, user_id))
        if stars is not None:
            await db.execute("UPDATE users SET balance_stars = balance_stars + ? WHERE id = ?", (stars, user_id))
        await db.commit()


async def set_ref(user_id: int, ref_by: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET ref_by = ? WHERE id = ?", (ref_by, user_id))
        await db.commit()


async def add_referral(referrer_id: int, invited_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        now = datetime.now().isoformat()
        await db.execute(
            "INSERT INTO referrals (referrer_id, invited_id, created_at) VALUES (?, ?, ?)",
            (referrer_id, invited_id, now)
        )
        await db.commit()


async def get_referral_stats(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)) as cur:
            count = (await cur.fetchone())[0]
        return count


# ===== ACCOUNTS =====
async def add_account(country: str, phone: str, code: str, price_usd: float, price_stars: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO accounts (country, phone, code, price_usd, price_stars) VALUES (?, ?, ?, ?, ?)",
            (country, phone, code, price_usd, price_stars)
        )
        await db.commit()
        return db.last_insert_rowid


async def get_accounts(country: str = None, sold: int = 0):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        if country:
            async with db.execute(
                "SELECT * FROM accounts WHERE country = ? AND sold = ?", (country, sold)
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute("SELECT * FROM accounts WHERE sold = ?", (sold,)) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_account(account_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def mark_sold(account_id: int, buyer_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        now = datetime.now().isoformat()
        await db.execute(
            "UPDATE accounts SET sold = 1, buyer_id = ?, sold_at = ? WHERE id = ?",
            (buyer_id, now, account_id)
        )
        await db.commit()


async def delete_account(account_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        await db.commit()


# ===== PURCHASES =====
async def add_purchase(user_id: int, account_id: int, pay_method: str, amount: float):
    async with aiosqlite.connect(DB_NAME) as db:
        now = datetime.now().isoformat()
        await db.execute(
            "INSERT INTO purchases (user_id, account_id, pay_method, amount, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, account_id, pay_method, amount, now)
        )
        await db.commit()


async def get_purchases(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT p.*, a.phone, a.code, a.country FROM purchases p JOIN accounts a ON p.account_id = a.id WHERE p.user_id = ? ORDER BY p.created_at DESC",
            (user_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ===== HELPERS =====
async def add_helper(user_id: int, username: str, added_by: int):
    async with aiosqlite.connect(DB_NAME) as db:
        now = datetime.now().isoformat()
        await db.execute(
            "INSERT OR IGNORE INTO helpers (user_id, username, added_by, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, added_by, now)
        )
        await db.commit()


async def remove_helper(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM helpers WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_helpers():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM helpers") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def is_helper(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT 1 FROM helpers WHERE user_id = ?", (user_id,)) as cur:
            return (await cur.fetchone()) is not None


# ===== SETTINGS =====
async def get_setting(key: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()


# ===== STATS =====
async def get_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM accounts WHERE sold = 1") as cur:
            sold = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM accounts WHERE sold = 0") as cur:
            stock = (await cur.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(amount), 0) FROM purchases WHERE pay_method = 'crypto'") as cur:
            revenue_usd = (await cur.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(amount), 0) FROM purchases WHERE pay_method = 'stars'") as cur:
            revenue_stars = (await cur.fetchone())[0]
        return {"sold": sold, "stock": stock, "revenue_usd": revenue_usd, "revenue_stars": revenue_stars}


async def add_payment(user_id: int, invoice_id: str, amount: float, currency: str):
    async with aiosqlite.connect(DB_NAME) as db:
        now = datetime.now().isoformat()
        await db.execute(
            "INSERT INTO payments (user_id, invoice_id, amount, currency, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, invoice_id, amount, currency, now)
        )
        await db.commit()
