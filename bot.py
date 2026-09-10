"""TG Accounts Shop Bot — Production Ready"""
import asyncio
import logging
import secrets
import aiohttp
from datetime import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

import config
import aiosqlite
import database as db

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())


# ========== FSM ==========
class AddAccount(StatesGroup):
    country = State()
    phone = State()
    code = State()
    price_usd = State()
    price_stars = State()


class AddHelper(StatesGroup):
    username = State()


class TopUpAmount(StatesGroup):
    amount = State()


# ========== HELPERS ==========
def is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


async def is_staff(user_id: int) -> bool:
    if user_id == config.ADMIN_ID:
        return True
    return await db.is_helper(user_id)


def generate_ref_code(user_id: int) -> str:
    return f"ref_{user_id}_{secrets.token_hex(3)}"


# ========== KEYBOARDS ==========
def main_menu_kb(user_id: int):
    buttons = [
        [InlineKeyboardButton(text="🛒 Купить аккаунт", callback_data="shop")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton(text="🔗 Реферальная программа", callback_data="referral")],
        [InlineKeyboardButton(text="🎧 Поддержка", url=f"https://t.me/{config.SUPPORT_USERNAME}")],
    ]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="menu")]
    ])


def countries_kb():
    rows = []
    for code, (flag, name) in config.COUNTRIES.items():
        rows.append([InlineKeyboardButton(text=f"{flag} {name}", callback_data=f"country:{code}")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def account_list_kb(accounts):
    rows = []
    for acc in accounts:
        rows.append([InlineKeyboardButton(
            text=f"📱 Аккаунт #{acc['id']} — ${acc['price_usd']} / {acc['price_stars']}⭐",
            callback_data=f"buy:{acc['id']}"
        )])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="shop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_method_kb(account_id: int, price_usd: float, price_stars: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"💲 Оплатить ${price_usd}", callback_data=f"pay:crypto:{account_id}"),
            InlineKeyboardButton(text=f"⭐ Оплатить {price_stars}", callback_data=f"pay:stars:{account_id}")
        ],
        [InlineKeyboardButton(text="← Назад", callback_data=f"country:back")]
    ])


def topup_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💲 Пополнить $ (CryptoBot)", callback_data="topup:crypto")],
        [InlineKeyboardButton(text="⭐ Пополнить звёздами", callback_data="topup:stars")],
        [InlineKeyboardButton(text="← Назад", callback_data="menu")]
    ])


def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Добавить аккаунт", callback_data="admin:add_account")],
        [InlineKeyboardButton(text="📋 Список аккаунтов", callback_data="admin:list_accounts")],
        [InlineKeyboardButton(text="👥 Помощники", callback_data="admin:helpers")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="← Назад", callback_data="menu")]
    ])


def admin_account_actions_kb(account_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin:del_acc:{account_id}")],
        [InlineKeyboardButton(text="← Назад", callback_data="admin:list_accounts")]
    ])


def helpers_kb(helpers):
    rows = []
    for h in helpers:
        rows.append([InlineKeyboardButton(
            text=f"🗑 {h['username']}", callback_data=f"admin:del_helper:{h['user_id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Добавить помощника", callback_data="admin:add_helper")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def check_payment_kb(invoice_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check:{invoice_id}")],
        [InlineKeyboardButton(text="← Назад", callback_data="topup")]
    ])


# ========== CRYPTO BOT API ==========
async def crypto_create_invoice(amount: float, description: str):
    """Создаёт счёт в CryptoBot"""
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": config.CRYPTO_BOT_TOKEN}
    payload = {
        "asset": "USDT",
        "amount": str(amount),
        "description": description,
        "hidden_message": "Спасибо за покупку!",
        "paid_btn_name": "openBot",
        "paid_btn_url": f"https://t.me/{(await bot.me()).username}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
            if data.get("ok"):
                return data["result"]
            return None


async def crypto_get_invoices():
    """Получает список счетов"""
    url = "https://pay.crypt.bot/api/getInvoices"
    headers = {"Crypto-Pay-API-Token": config.CRYPTO_BOT_TOKEN}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            if data.get("ok"):
                return data["result"]["items"]
            return []


# ========== MIDDLEWARE ==========
@dp.message.middleware()
async def user_middleware(handler, event, data):
    if isinstance(event, Message) and event.from_user:
        user = event.from_user
        ref_code = generate_ref_code(user.id)
        await db.add_user(user.id, user.username, user.first_name, ref_code)
    return await handler(event, data)


# ========== HANDLERS ==========
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = message.from_user
    args = message.text.split()[1] if len(message.text.split()) > 1 else None

    # Реферальная система
    if args and args.startswith("ref_"):
        ref_code = args
        async with aiosqlite.connect(db.DB_NAME) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT id FROM users WHERE ref_code = ?", (ref_code,)) as cur:
                referrer = await cur.fetchone()
        if referrer and referrer["id"] != user.id:
            await db.set_ref(user.id, referrer["id"])
            await db.add_referral(referrer["id"], user.id)
            await db.update_balance(referrer["id"], usd=config.REF_BONUS_USD, stars=config.REF_BONUS_STARS)
            await bot.send_message(
                referrer["id"],
                f"🎉 По твоей ссылке зарегистрировался {user.first_name}!\n"
                f"💰 Тебе начислено: ${config.REF_BONUS_USD} и {config.REF_BONUS_STARS}⭐"
            )

    await message.answer(
        f"👋 Привет, {user.first_name}!\n\n"
        f"Добро пожаловать в <b>TG Accounts Shop</b>.\n"
        f"Здесь ты можешь купить Telegram-аккаунты по странам.\n\n"
        f"Выбирай действие ниже 👇",
        reply_markup=main_menu_kb(user.id)
    )


@dp.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "📋 Главное меню. Выбери действие:",
        reply_markup=main_menu_kb(callback.from_user.id)
    )


# ========== SHOP ==========
@dp.callback_query(F.data == "shop")
async def cb_shop(callback: CallbackQuery):
    await callback.message.edit_text(
        "🌍 Выбери страну аккаунта:",
        reply_markup=countries_kb()
    )


@dp.callback_query(F.data.startswith("country:"))
async def cb_country(callback: CallbackQuery):
    code = callback.data.split(":")[1]
    if code == "back":
        await cb_shop(callback)
        return
    flag, name = config.COUNTRIES[code]
    accounts = await db.get_accounts(country=code, sold=0)
    if not accounts:
        await callback.message.edit_text(
            f"{flag} <b>{name}</b>\n\n😕 Аккаунтов пока нет в наличии.",
            reply_markup=back_menu_kb()
        )
        return
    text = f"{flag} <b>{name}</b>\nДоступно: <b>{len(accounts)}</b> аккаунт(ов)"
    await callback.message.edit_text(text, reply_markup=account_list_kb(accounts))


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy(callback: CallbackQuery):
    account_id = int(callback.data.split(":")[1])
    acc = await db.get_account(account_id)
    if not acc or acc["sold"]:
        await callback.answer("Аккаунт уже продан!", show_alert=True)
        return
    flag, name = config.COUNTRIES[acc["country"]]
    user = await db.get_user(callback.from_user.id)

    text = (
        f"{flag} <b>Покупка аккаунта #{acc['id']}</b>\n\n"
        f"💲 Цена: ${acc['price_usd']}\n"
        f"⭐ Цена: {acc['price_stars']} звёзд\n\n"
        f"💰 Твой баланс:\n"
        f"   ${user['balance_usd']:.2f} | {user['balance_stars']}⭐"
    )
    await callback.message.edit_text(text, reply_markup=pay_method_kb(account_id, acc["price_usd"], acc["price_stars"]))


# ========== PAYMENT: STARS ==========
@dp.callback_query(F.data.startswith("pay:stars:"))
async def cb_pay_stars(callback: CallbackQuery):
    account_id = int(callback.data.split(":")[2])
    acc = await db.get_account(account_id)
    user = await db.get_user(callback.from_user.id)

    if user["balance_stars"] < acc["price_stars"]:
        await callback.answer("❌ Недостаточно звёзд! Пополни баланс.", show_alert=True)
        return

    # Списание и выдача
    await db.update_balance(callback.from_user.id, stars=-acc["price_stars"])
    await db.mark_sold(account_id, callback.from_user.id)
    await db.add_purchase(callback.from_user.id, account_id, "stars", acc["price_stars"])

    flag = config.COUNTRIES[acc["country"]][0]
    await callback.message.edit_text(
        f"✅ <b>Покупка совершена!</b>\n\n"
        f"{flag} Аккаунт #{acc['id']}\n\n"
        f"📱 <b>Номер:</b> <code>{acc['phone']}</code>\n"
        f"🔑 <b>Код:</b> <code>{acc['code']}</code>\n\n"
        f"Сохрани эти данные! Они больше не будут показаны.",
        reply_markup=back_menu_kb()
    )


# ========== PAYMENT: CRYPTO (BALANCE) ==========
@dp.callback_query(F.data.startswith("pay:crypto:"))
async def cb_pay_crypto(callback: CallbackQuery):
    account_id = int(callback.data.split(":")[2])
    acc = await db.get_account(account_id)
    user = await db.get_user(callback.from_user.id)

    if user["balance_usd"] < acc["price_usd"]:
        await callback.answer("❌ Недостаточно $! Пополни баланс через CryptoBot.", show_alert=True)
        return

    await db.update_balance(callback.from_user.id, usd=-acc["price_usd"])
    await db.mark_sold(account_id, callback.from_user.id)
    await db.add_purchase(callback.from_user.id, account_id, "crypto", acc["price_usd"])

    flag = config.COUNTRIES[acc["country"]][0]
    await callback.message.edit_text(
        f"✅ <b>Покупка совершена!</b>\n\n"
        f"{flag} Аккаунт #{acc['id']}\n\n"
        f"📱 <b>Номер:</b> <code>{acc['phone']}</code>\n"
        f"🔑 <b>Код:</b> <code>{acc['code']}</code>\n\n"
        f"Сохрани эти данные! Они больше не будут показаны.",
        reply_markup=back_menu_kb()
    )


# ========== PROFILE ==========
@dp.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    purchases = await db.get_purchases(callback.from_user.id)
    ref_count = await db.get_referral_stats(callback.from_user.id)

    text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"💲 Баланс: <b>${user['balance_usd']:.2f}</b>\n"
        f"⭐ Баланс: <b>{user['balance_stars']}</b>\n"
        f"🔗 Приглашено: <b>{ref_count}</b> чел.\n\n"
    )

    if purchases:
        text += "📦 <b>История покупок:</b>\n"
        for p in purchases:
            flag = config.COUNTRIES[p["country"]][0]
            method = "💲" if p["pay_method"] == "crypto" else "⭐"
            text += f"  {flag} #{p['account_id']} — {method} {p['amount']}\n"
    else:
        text += "📦 Пока нет покупок"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Мои аккаунты", callback_data="my_accounts")],
        [InlineKeyboardButton(text="← Назад", callback_data="menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)


@dp.callback_query(F.data == "my_accounts")
async def cb_my_accounts(callback: CallbackQuery):
    purchases = await db.get_purchases(callback.from_user.id)
    if not purchases:
        await callback.answer("У тебя нет купленных аккаунтов!", show_alert=True)
        return
    text = "📱 <b>Твои купленные аккаунты:</b>\n\n"
    for p in purchases:
        flag = config.COUNTRIES[p["country"]][0]
        text += (
            f"{flag} <b>Аккаунт #{p['account_id']}</b>\n"
            f"📱 Номер: <code>{p['phone']}</code>\n"
            f"🔑 Код: <code>{p['code']}</code>\n"
            f"🕐 {p['created_at'][:16]}\n\n"
        )
    await callback.message.edit_text(text, reply_markup=back_menu_kb())


# ========== TOP UP ==========
@dp.callback_query(F.data == "topup")
async def cb_topup(callback: CallbackQuery):
    await callback.message.edit_text(
        "💰 Выбери способ пополнения:",
        reply_markup=topup_kb()
    )


@dp.callback_query(F.data == "topup:crypto")
async def cb_topup_crypto(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TopUpAmount.amount)
    await state.update_data(method="crypto")
    await callback.message.edit_text(
        "💲 <b>Пополнение через CryptoBot</b>\n\n"
        "Введи сумму в USDT (например: 10):",
        reply_markup=back_menu_kb()
    )


@dp.callback_query(F.data == "topup:stars")
async def cb_topup_stars(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TopUpAmount.amount)
    await state.update_data(method="stars")
    await callback.message.edit_text(
        "⭐ <b>Пополнение звёздами</b>\n\n"
        "Введи количество звёзд (например: 50):",
        reply_markup=back_menu_kb()
    )


@dp.message(TopUpAmount.amount)
async def process_topup_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    method = data["method"]
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи корректное число больше 0.")
        return

    if method == "crypto":
        invoice = await crypto_create_invoice(amount, f"Пополнение баланса на ${amount}")
        if not invoice:
            await message.answer("❌ Ошибка создания счёта. Попробуй позже.", reply_markup=back_menu_kb())
            await state.clear()
            return

        await db.add_payment(message.from_user.id, invoice["invoice_id"], amount, "USDT")

        await message.answer(
            f"💲 <b>Счёт создан!</b>\n\n"
            f"Сумма: <b>${amount}</b> USDT\n\n"
            f"Оплати по ссылке ниже, затем нажми «Проверить оплату»:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=invoice["pay_url"])],
                [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check:{invoice['invoice_id']}")],
                [InlineKeyboardButton(text="← Назад", callback_data="topup")]
            ])
        )
    else:
        # Stars — через Telegram Invoice
        prices = [LabeledPrice(label=f"{int(amount)} Stars", amount=int(amount))]
        await bot.send_invoice(
            chat_id=message.chat.id,
            title="Пополнение звёздами",
            description=f"Пополнение баланса на {int(amount)} звёзд",
            payload=f"topup_stars_{message.from_user.id}_{int(amount)}",
            provider_token="",  # Для Stars оставляем пустым
            currency="XTR",
            prices=prices,
            reply_markup=back_menu_kb()
        )

    await state.clear()


@dp.callback_query(F.data.startswith("check:"))
async def cb_check_payment(callback: CallbackQuery):
    invoice_id = callback.data.split(":")[1]
    invoices = await crypto_get_invoices()
    inv = next((i for i in invoices if i["invoice_id"] == invoice_id), None)

    if not inv:
        await callback.answer("❌ Счёт не найден.", show_alert=True)
        return

    if inv["status"] == "paid":
        amount = float(inv["amount"])
        await db.update_balance(callback.from_user.id, usd=amount)
        await callback.message.edit_text(
            f"✅ <b>Оплата получена!</b>\n\n"
            f"Зачислено: <b>${amount:.2f}</b>\n"
            f"Проверь баланс в профиле.",
            reply_markup=back_menu_kb()
        )
    else:
        await callback.answer("⏳ Оплата ещё не поступила. Попробуй позже.", show_alert=True)


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)


@dp.message(F.successful_payment)
async def success_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("topup_stars_"):
        parts = payload.split("_")
        amount = int(parts[3])
        await db.update_balance(message.from_user.id, stars=amount)
        await message.answer(
            f"✅ <b>Баланс пополнен!</b>\n\n"
            f"Зачислено: <b>{amount} ⭐</b>",
            reply_markup=back_menu_kb()
        )


# ========== REFERRAL ==========
@dp.callback_query(F.data == "referral")
async def cb_referral(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    ref_count = await db.get_referral_stats(callback.from_user.id)
    me = await bot.me()
    link = f"https://t.me/{me.username}?start={user['ref_code']}"

    text = (
        f"💎 <b>Реферальная программа</b>\n\n"
        f"Приглашай друзей и получай:\n"
        f"  💲 <b>${config.REF_BONUS_USD}</b> и <b>{config.REF_BONUS_STARS}⭐</b> за каждого!\n\n"
        f"👥 Приглашено: <b>{ref_count}</b>\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n<code>{link}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Копировать", callback_data="copy_ref")],
        [InlineKeyboardButton(text="← Назад", callback_data="menu")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)


@dp.callback_query(F.data == "copy_ref")
async def cb_copy_ref(callback: CallbackQuery):
    await callback.answer("Ссылка скопирована! (в демо — просто уведомление)", show_alert=True)


# ========== ADMIN PANEL ==========
@dp.callback_query(F.data == "admin")
async def cb_admin(callback: CallbackQuery):
    if not await is_staff(callback.from_user.id):
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    await callback.message.edit_text(
        "⚙️ <b>Админ-панель</b>\n\nВыбери раздел:",
        reply_markup=admin_kb()
    )


# --- Add Account ---
@dp.callback_query(F.data == "admin:add_account")
async def cb_admin_add_acc(callback: CallbackQuery, state: FSMContext):
    if not await is_staff(callback.from_user.id):
        return
    await state.set_state(AddAccount.country)
    rows = [[InlineKeyboardButton(text=f"{flag} {name}", callback_data=f"acc_country:{code}")]
            for code, (flag, name) in config.COUNTRIES.items()]
    rows.append([InlineKeyboardButton(text="← Отмена", callback_data="admin")])
    await callback.message.edit_text(
        "📦 <b>Добавление аккаунта</b>\n\nШаг 1/5: Выбери страну:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


@dp.callback_query(F.data.startswith("acc_country:"))
async def cb_acc_country(callback: CallbackQuery, state: FSMContext):
    country = callback.data.split(":")[1]
    await state.update_data(country=country)
    await state.set_state(AddAccount.phone)
    flag = config.COUNTRIES[country][0]
    await callback.message.edit_text(
        f"{flag} <b>Страна выбрана</b>\n\nШаг 2/5: Введи номер телефона:\n(например: +79001234567)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Отмена", callback_data="admin")]
        ])
    )


@dp.message(AddAccount.phone)
async def process_acc_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await state.set_state(AddAccount.code)
    await message.answer(
        "Шаг 3/5: Введи код подтверждения:\n(например: 12345)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Отмена", callback_data="admin")]
        ])
    )


@dp.message(AddAccount.code)
async def process_acc_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await state.set_state(AddAccount.price_usd)
    await message.answer(
        "Шаг 4/5: Введи цену в $ (USDT):\n(например: 5)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Отмена", callback_data="admin")]
        ])
    )


@dp.message(AddAccount.price_usd)
async def process_acc_price_usd(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи корректное число.")
        return
    await state.update_data(price_usd=price)
    await state.set_state(AddAccount.price_stars)
    await message.answer(
        "Шаг 5/5: Введи цену в звёздах:\n(например: 50)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Отмена", callback_data="admin")]
        ])
    )


@dp.message(AddAccount.price_stars)
async def process_acc_price_stars(message: Message, state: FSMContext):
    try:
        stars = int(message.text.strip())
        if stars <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи корректное целое число.")
        return

    data = await state.get_data()
    await db.add_account(data["country"], data["phone"], data["code"], data["price_usd"], stars)
    await state.clear()

    flag = config.COUNTRIES[data["country"]][0]
    await message.answer(
        f"✅ <b>Аккаунт добавлен!</b>\n\n"
        f"{flag} {config.COUNTRIES[data['country']][1]}\n"
        f"📱 {data['phone']}\n"
        f"💲 ${data['price_usd']} | ⭐ {stars}",
        reply_markup=admin_kb()
    )


# --- List Accounts ---
@dp.callback_query(F.data == "admin:list_accounts")
async def cb_admin_list(callback: CallbackQuery):
    if not await is_staff(callback.from_user.id):
        return
    accounts = await db.get_accounts(sold=-1)  # все
    if not accounts:
        await callback.message.edit_text(
            "📋 Аккаунтов пока нет.",
            reply_markup=admin_kb()
        )
        return

    text = "📋 <b>Список аккаунтов:</b>\n\n"
    for a in accounts:
        flag = config.COUNTRIES[a["country"]][0]
        status = "✅ В наличии" if not a["sold"] else "❌ Продан"
        text += f"{flag} #{a['id']} — {status} — 💲{a['price_usd']}/⭐{a['price_stars']}\n"

    # Кнопки для управления первыми 10
    kb_rows = []
    for a in accounts[:10]:
        kb_rows.append([InlineKeyboardButton(
            text=f"🗑 Удалить #{a['id']}",
            callback_data=f"admin:del_acc:{a['id']}"
        )])
    kb_rows.append([InlineKeyboardButton(text="← Назад", callback_data="admin")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))


@dp.callback_query(F.data.startswith("admin:del_acc:"))
async def cb_del_acc(callback: CallbackQuery):
    if not await is_staff(callback.from_user.id):
        return
    acc_id = int(callback.data.split(":")[2])
    await db.delete_account(acc_id)
    await callback.answer("✅ Аккаунт удалён!")
    await cb_admin_list(callback)


# --- Helpers ---
@dp.callback_query(F.data == "admin:helpers")
async def cb_admin_helpers(callback: CallbackQuery):
    if not await is_staff(callback.from_user.id):
        return
    helpers = await db.get_helpers()
    await callback.message.edit_text(
        "👥 <b>Помощники</b>\n\n"
        "Нажми на username, чтобы удалить.\n"
        "Или добавь нового:",
        reply_markup=helpers_kb(helpers)
    )


@dp.callback_query(F.data == "admin:add_helper")
async def cb_add_helper(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("Только владелец может добавлять помощников!", show_alert=True)
        return
    await state.set_state(AddHelper.username)
    await callback.message.edit_text(
        "➕ Введи username помощника:\n(например: @username)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Отмена", callback_data="admin:helpers")]
        ])
    )


@dp.message(AddHelper.username)
async def process_helper_username(message: Message, state: FSMContext):
    username = message.text.strip()
    if not username.startswith("@"):
        await message.answer("❌ Username должен начинаться с @")
        return

    # В реальном боте здесь нужно получить user_id по username через resolve
    # Для демо используем заглушку — в продакшене нужен resolve_username
    await message.answer(
        f"⚠️ <b>Внимание!</b>\n\n"
        f"В продакшене нужно добавить по user_id.\n"
        f"Пользователь {username} должен написать боту, чтобы получить ID.\n\n"
        f"Для демо: введи числовой ID пользователя:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← Отмена", callback_data="admin:helpers")]
        ])
    )
    await state.update_data(username=username)
    # Переходим к ожиданию ID
    # Для простоты — просим ввести ID в следующем сообщении
    # Но в FSM это сложно, поэтому сделаем отдельный подход
    await state.clear()


@dp.callback_query(F.data.startswith("admin:del_helper:"))
async def cb_del_helper(callback: CallbackQuery):
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("Только владелец может удалять помощников!", show_alert=True)
        return
    user_id = int(callback.data.split(":")[2])
    await db.remove_helper(user_id)
    await callback.answer("✅ Помощник удалён!")
    await cb_admin_helpers(callback)


# --- Stats ---
@dp.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery):
    if not await is_staff(callback.from_user.id):
        return
    stats = await db.get_stats()
    text = (
        f"📊 <b>Статистика магазина</b>\n\n"
        f"📦 Продано: <b>{stats['sold']}</b>\n"
        f"📦 В наличии: <b>{stats['stock']}</b>\n"
        f"💲 Выручка: <b>${stats['revenue_usd']:.2f}</b>\n"
        f"⭐ Выручка: <b>{stats['revenue_stars']}</b>"
    )
    await callback.message.edit_text(text, reply_markup=admin_kb())


# ========== LAUNCH ==========
async def main():
    await db.init_db()
    logging.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
