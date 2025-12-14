import os
import threading
import time
from datetime import datetime, timedelta
import json

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from xoso_core import (
    save_today_numbers,
    get_prediction_for_dai,
    get_last_n_history,
    stats_for_dai,
    backup_data,
    DAI_MAP,
    clear_history,
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANK_QR_PATH = os.path.join(BASE_DIR, "bank_qr.png")

# =============================
# CONFIG (GIỮ NGUYÊN + ADD)
# =============================

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Thiếu BOT_TOKEN")

AUTO_CHAT_ID = int(os.getenv("AUTO_CHAT_ID", "0"))
PORT = int(os.environ.get("PORT", "10000"))

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_URL = f"{RENDER_URL}/{BOT_TOKEN}"

WAITING_INPUT: dict[int, str] = {}
LAST_SELECTED_DAI: dict[int, str] = {}

# ===== ADD CONFIG =====
ADMIN_USERNAME = "x117277"
ADMIN_IDS = {5546717219}

ANALYZE_FEE = 1.5  # USDT / 1 lần dự đoán
MIN_DEPOSIT_VND = 200_000
USDT_RATE = 27000  # fix cứng, giống edit.py bản đơn giản

BALANCE_FILE = "balances.json"
BILL_FILE = "bank_bills.json"

# =============================
# BALANCE SYSTEM (ADD)
# =============================

def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_balance(uid: int) -> float:
    return _load_json(BALANCE_FILE, {}).get(str(uid), 0.0)

def add_balance(uid: int, amount: float):
    data = _load_json(BALANCE_FILE, {})
    k = str(uid)
    data[k] = data.get(k, 0.0) + amount
    _save_json(BALANCE_FILE, data)

def sub_balance(uid: int, amount: float):
    data = _load_json(BALANCE_FILE, {})
    k = str(uid)
    data[k] = data.get(k, 0.0) - amount
    _save_json(BALANCE_FILE, data)
dd
# =============================
# FORMAT PREDICTION (GIỮ NGUYÊN)
# =============================

def format_prediction(dai: str, preds: list[str]) -> str:
    name = DAI_MAP.get(dai, "?")

    if not preds or (len(preds) == 1 and "Chưa có dữ liệu" in preds[0]):
        return (
            f"🎯 {name}:\n"
            f"⚠ Chưa đủ dữ liệu để dự đoán!\n\n"
            f"👉 Nhập 18 số theo dạng:\n00 11 22 ..."
        )

    return (
        f"🎯 Dự đoán – {name}\n\n"
        f"{' '.join(preds)}"
    )

# =============================
# ADD: PREDICTION WITH FEE
# =============================

def get_prediction_with_fee(uid: int, dai: str) -> str:
    bal = get_balance(uid)
    if bal < ANALYZE_FEE:
        return (
            "❌ Không đủ số dư\n"
            f"💰 Cần: {ANALYZE_FEE} USDT\n"
            f"💼 Có: {bal:.2f} USDT\n\n"
            f"📞 Admin: @{ADMIN_USERNAME}"
        )

    preds = get_prediction_for_dai(dai)
    sub_balance(uid, ANALYZE_FEE)

    return (
        format_prediction(dai, preds)
        + f"\n\n💰 Phí: {ANALYZE_FEE} USDT"
        + f"\n💼 Số dư: {get_balance(uid):.2f} USDT"
        + f"\n📞 Admin: @{ADMIN_USERNAME}"
    )

# =============================
# AUTO DAILY (GIỮ NGUYÊN)
# =============================

def auto_scheduler():
    while True:
        now = datetime.now()
        run = now.replace(hour=16, minute=35, second=0, microsecond=0)
        if now >= run:
            run += timedelta(days=1)
        time.sleep(max((run - now).total_seconds(), 1))

        msg = "📅 Auto dự đoán:\n\n"
        for dai in ["1", "2", "3"]:
            msg += format_prediction(dai, get_prediction_for_dai(dai)) + "\n\n"

        if AUTO_CHAT_ID:
            httpx.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": AUTO_CHAT_ID, "text": msg},
            )
        backup_data()

# =============================
# KEYBOARD (ADD NẠP TIỀN)
# =============================

def menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎯 Dự đoán", callback_data="pred_menu")],
            [InlineKeyboardButton("💳 Nạp tiền", callback_data="deposit")],
            [
                InlineKeyboardButton("📜 Lịch sử", callback_data="hist_menu"),
                InlineKeyboardButton("📊 Thống kê", callback_data="stat_menu"),
            ],
        ]
    )

def dai_keyboard(prefix):
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("TP.HCM", callback_data=f"{prefix}_1"),
            InlineKeyboardButton("Vĩnh Long", callback_data=f"{prefix}_2"),
            InlineKeyboardButton("An Giang", callback_data=f"{prefix}_3"),
        ]]
    )

# =============================
# HANDLERS
# =============================

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot sẵn sàng\n/menu")

async def menu_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 Menu:", reply_markup=menu_keyboard())

async def menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data == "deposit":
        ctx.user_data["deposit"] = True
        await q.edit_message_text(
            f"💳 Nhập số tiền VND (tối thiểu {MIN_DEPOSIT_VND:,}):"
        )
        return

    if data.endswith("_menu"):
        await q.edit_message_text("📌 Chọn đài:", reply_markup=dai_keyboard("pred"))
        return

    if "_" in data:
        action, dai = data.split("_")
        if action == "pred":
            msg = get_prediction_with_fee(uid, dai)
            await q.edit_message_text(msg, reply_markup=menu_keyboard())
            return

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    text = update.message.text.strip()

    if ctx.user_data.get("deposit"):
        try:
            vnd = int(text.replace(",", ""))
            if vnd < MIN_DEPOSIT_VND:
                raise ValueError
        except:
            await update.message.reply_text("❌ Số tiền không hợp lệ")
            return

        # tạo bill
        bill_id = create_bill(uid, vnd)
        ctx.user_data.clear()

        # ===== GỬI QR CHO USER =====
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        BANK_QR_PATH = os.path.join(BASE_DIR, "bank_qr.png")

        caption = (
            f"🏦 THÔNG TIN CHUYỂN KHOẢN\n"
            f"💰 Số tiền: {vnd:,} VND\n"
            f"🧾 Nội dung CK: ID {uid}\n\n"
            f"📌 Sau khi chuyển khoản, vui lòng chờ admin duyệt bill\n"
            f"📞 Admin: @{ADMIN_USERNAME}"
        )

        try:
            with open(BANK_QR_PATH, "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=caption
                )
        except FileNotFoundError:
            await update.message.reply_text(
                caption + "\n\n⚠️ Không tìm thấy QR, liên hệ admin @x117277."
            )

        # ===== GỬI BILL CHO ADMIN =====
        for aid in ADMIN_IDS:
            await ctx.bot.send_message(
                aid,
                f"🧾 BILL #{bill_id}\n"
                f"UID: {uid}\n"
                f"💰 {vnd:,} VND\n"
                f"/admin_ok {bill_id}"
            )
        return


# =============================
# ADMIN COMMAND
# =============================

async def admin_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        return
    try:
        bill_id = int(ctx.args[0])
    except:
        return

    uid, usdt = approve_bill(bill_id)
    if not uid:
        await update.message.reply_text("❌ Bill không hợp lệ")
        return

    await update.message.reply_text(f"✅ Đã duyệt bill #{bill_id}")
    await ctx.bot.send_message(
        uid,
        f"✅ Nạp thành công +{usdt} USDT\n"
        f"💼 Số dư: {get_balance(uid):.2f} USDT"
    )

# =============================
# APP INIT
# =============================

app = Application.builder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("menu", menu_cmd))
app.add_handler(CommandHandler("admin_ok", admin_ok))
app.add_handler(CallbackQueryHandler(menu_callback))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# =============================
# MAIN
# =============================

def main():
    if AUTO_CHAT_ID:
        threading.Thread(target=auto_scheduler, daemon=True).start()

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=WEBHOOK_URL,
    )

if __name__ == "__main__":
    main()
