# Railway setup

1. Put the contents of this folder in the root of a GitHub repository (bot.py, config.py, database.py, requirements.txt, etc.).
2. In Railway: New Project -> Deploy from GitHub Repo -> select the repository.
3. Service -> Variables: add BOT_TOKEN, CRYPTO_BOT_TOKEN and ADMIN_ID.
4. Add a Railway Volume to the service and set mount path to `/app/data`.
5. Add variable `DB_PATH=/app/data/shop.db`.
6. Start command is `python bot.py` (already in railway.json).
7. Redeploy and check Deploy Logs. A successful launch contains `Бот запущен!`.

Do not commit `.env` or real tokens to GitHub.
