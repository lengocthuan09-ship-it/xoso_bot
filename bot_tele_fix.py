import os
import threading
import time
from datetime import datetime, timedelta

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
    clear_history,
)

# =============================
# CONFIG
# =============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = os.getenv("BASE_URL")   # ví dụ: https://xoso-bot.onrender.com
WEBHOOK_URL = f"{BASE_URL}/{BOT_TOKEN}"

AUTO_CHAT_ID = 0
WAITING_INPUT = {}
LAST_SELECTED_DAI = {}

# =============================
# AUTO DAILY TASK
# =============================
def auto_scheduler():
    while True:
        now = datetime.now()
        run = now.replace(hour=16, minute=35, second=0, microsecond=0)
        if now >= run:
            run += timedelta(days=1)

        wait = (run - now).total_seconds()
        print(f"⏳ Chờ tới {run} để chạy auto…")
        time.sleep(wait)

        msg = "📅 Auto dự đoán:\n\n"
        for dai in ["1", "2", "3"]:
            preds = get_prediction_for_dai(dai)
            msg += format_prediction(dai, preds) + "\n\n"

        if AUTO_CHAT_ID:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": AUTO_CHAT_ID, "text": msg},
            )

        backup_data()
        print("✔ Auto xong 1 lượt.")

# =============================
# UI / BUTTON
# =============================
def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Dự đoán", callback_data="pred_menu")],
        [
            InlineKeyboardButton("📜 Lịch sử", callback_data="hist_menu"),
            InlineKeyboardButton("📊 Thống kê", callback_data="stat_menu"),
        ],
        [
            InlineKeyboardButton("🗑 Xóa", callback_data="del_menu"),
            InlineKeyboardButton("📝 Nhập", callback_data="input_menu"),
        ]
    ])

def dai_select_keyboard(prefix):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Đài 1 (TP.HCM)", callback_data=f"{prefix}_1"),
            InlineKeyboardButton("Đài 2 (Vĩnh Long)", callback_data=f"{prefix}_2"),
            InlineKeyboardButton("Đài 3 (An Giang)", callback_data=f"{prefix}_3"),
        ],
        [InlineKeyboardButton("⬅ Quay lại", callback_data="menu_main")]
    ])

def format_prediction(dai, preds):
    name = DAI_MAP.get(dai, "?")

    if not preds or (len(preds) == 1 and "Chưa có dữ liệu" in preds[0]):
        return (
            f"🎯 {name}:\n⚠ Chưa đủ dữ liệu!\n\n👉 Nhập 18 số dạng 00 11 22 ..."
        )

    line1 = " – ".join(preds[:6])
    line2 = " – ".join(preds[6:12])
    all_nums = " ".join(preds)

    return (
        f"🎯 Dự đoán 12 lô – {name}\n\n"
        f"➡ {line1}\n➡ {line2}\n\n"
        f"{all_nums}"
    )

# =============================
# HANDLERS
# =============================
async def start(update, context):
    await update.message.reply_text("🤖 Bot đã sẵn sàng!\n👉 Nhấn /menu")

async def menu_cmd(update, context):
    await update.message.reply_text("📌 Chọn chức năng:", reply_markup=menu_keyboard())

async def menu_callback(update, context):
    q = update.callback_query
    await q.answer()

    data = q.data
    if data == "menu_main":
        await q.edit_message_text("📌 Chọn chức năng:", reply_markup=menu_keyboard())
        return

    if data.endswith("_menu"):
        prefix = data.split("_")[0]
        await q.edit_message_text("📌 Chọn đài:", reply_markup=dai_select_keyboard(prefix))
        return

    action, dai = data.split("_")
    LAST_SELECTED_DAI[q.from_user.id] = dai

    if action == "pred":
        preds = get_prediction_for_dai(dai)
        await q.edit_message_text(format_prediction(dai, preds), reply_markup=menu_keyboard())
        return

    if action == "hist":
        hist = get_last_n_history(dai, 7)
        msg = f"📜 Lịch sử – {DAI_MAP[dai]}:\n"
        for h in hist:
            msg += f"- {h['date']}: {' '.join(h['numbers'])}\n"
        await q.edit_message_text(msg, reply_markup=menu_keyboard())
        return

    if action == "stat":
        st = stats_for_dai(dai, 7)
        msg = (
            f"📊 Thống kê – {DAI_MAP[dai]}\n"
            f"- Tổng lượt: {st['total_draws']}\n"
            f"- Chẵn: {st['even']} | Lẻ: {st['odd']}\n"
            f"- Nóng: {st['hot']} | Gan: {st['cold']}"
        )
        await q.edit_message_text(msg, reply_markup=menu_keyboard())
        return

    if action == "del":
        clear_history(dai)
        await q.edit_message_text("🗑 Đã xóa!", reply_markup=menu_keyboard())
        return

    if action == "input":
        uid = q.from_user.id
        WAITING_INPUT[uid] = dai
        await q.edit_message_text(f"📝 Nhập 18 số cho {DAI_MAP[dai]}:")
        return

async def handle_input(update, context):
    uid = update.message.from_user.id
    if uid not in WAITING_INPUT:
        return

    dai = WAITING_INPUT.pop(uid)
    parts = update.message.text.strip().split()

    if len(parts) != 18:
        WAITING_INPUT[uid] = dai
        await update.message.reply_text("❌ Bạn phải nhập đúng 18 số!")
        return

    nums = [f"{int(x):02d}" for x in parts]
    save_today_numbers(dai, nums)
    preds = get_prediction_for_dai(dai)

    await update.message.reply_text(
        f"📅 Đã lưu cho {DAI_MAP[dai]}!\n\n"
        f"{' '.join(nums)}\n\n"
        + format_prediction(dai, preds),
        reply_markup=menu_keyboard()
    )

# =============================
# MAIN WEBOOK SERVER (CHUẨN RENDER)
# =============================
async def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))

    # Auto thread
    threading.Thread(target=auto_scheduler, daemon=True).start()

    print("🚀 Set webhook:", WEBHOOK_URL)
    await app.bot.delete_webhook()
    await app.bot.set_webhook(WEBHOOK_URL)

    print("🚀 Webhook server listening...")
    await app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        url_path=BOT_TOKEN,
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
