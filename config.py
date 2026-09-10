"""Конфигурация бота"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_ЗДЕСЬ")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "ТВОЙ_CRYPTOBOT_ТОКЕН")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Твой Telegram ID (число)

# Настройки
SUPPORT_USERNAME = "wanstrelovv"
REF_BONUS_USD = 5.0
REF_BONUS_STARS = 10

# Страны
COUNTRIES = {
    "ru": ("🇷🇺", "Россия"),
    "kz": ("🇰🇿", "Казахстан"),
    "uz": ("🇺🇿", "Узбекистан"),
    "ua": ("🇺🇦", "Украина"),
    "by": ("🇧🇾", "Беларусь"),
    "kg": ("🇰🇬", "Кыргызстан"),
}

# Дизайн кнопок (можно менять через админку)
BTN_COLOR = "🔲"  # заглушка, в коде используем стандартные
