import os
import threading
import time
import asyncio
from datetime import datetime, timedelta

from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import requests

from xoso_core import (
    save_today_numbers,
    get_prediction_for_dai,
    get_last_n_history,
    stats_for_dai,
    backup_data,
    DAI_MAP,
    clear_history
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
AUTO_CHAT_ID = 0

WAITING_INPUT = {}
LAST_SELECTED_DAI = {}

flask_app = Flask(__name__)
tg_app = Application.builder().token(BOT_TOKEN).build()

# =============================
# FORMAT
# =============================
def format_prediction(dai, preds):
    name = DAI_MAP.get(dai, "?")
    if not preds:
        return f"⚠ Chưa có dữ liệu {name}"
    return f"🎯 {name}:\n" + " ".join(preds)

# =============================
# AUTO THREAD
# =============================
def auto_scheduler():
    while True:
        now = datetime.now()
        run = now.replace(hour=16, minute=35, second=0)
        if now >= run:
            run += timedelta(days=1)

        time.sleep((run - now).total_seconds())

        msg = "📅 Auto dự đoán:\n\n"
        for dai in ["1","2","3"]:
            preds = get_prediction_for_dai(dai)
            msg += format_prediction(dai, preds) + "\n\n"

        if AUTO_CHAT_ID:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": AUTO_CHAT_ID, "text": msg},
            )

# =============================
# COMMANDS
# =============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot đã sẵn sàng!\nGõ /menu")

async def menu_cmd(update: Update, context):
    await update.message.reply_text("📌 Chọn chức năng:", reply_markup=menu_keyboard())

async def handle_input(update: Update, context):
    await update.message.reply_text("Bot đã nhận tin nhắn thành công!")

# =============================
# KEYBOARDS
# =============================
def menu_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("OK", callback_data="ok")]])

# =============================
# HANDLERS
# =============================
tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CommandHandler("menu", menu_cmd))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))

# =============================
# WEBHOOK
# =============================
@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(), tg_app.bot)
    asyncio.run(tg_app.process_update(update))
    return "OK", 200

# =============================
# START BOT
# =============================
def start_bot():
    threading.Thread(target=auto_scheduler, daemon=True).start()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(tg_app.initialize())
    loop.run_until_complete(tg_app.start())

    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

if __name__ == "__main__":
    start_bot()
