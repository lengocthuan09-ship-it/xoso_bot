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

# =============================
# PATHS
# =============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANK_QR_PATH = os.path.join(BASE_DIR, "bank_qr.png")

# =============================
# CONFIG
# =============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Thiếu BOT_TOKEN")

AUTO_CHAT_ID = int(os.getenv("AUTO_CHAT_ID", "0"))
PORT = int(os.environ.get("PORT", "10000"))

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_URL = f"{RENDER_URL}/{BOT_TOKEN}"

ADMIN_USERNAME = "x117277"
ADMIN_IDS = {5546717219}

ANALYZE_FEE = 1.5
MIN_DEPOSIT_VND = 200_000
USDT_RATE = 27000

BALANCE_FILE = "balances.json"
BILL_FILE = "bank_bills.json"

# =============================
# JSON HELPERS
# =============================
def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# =============================
# BALANCE SYSTEM
# =============================
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

# =============================
# BILL SYSTEM
# =============================
def create_bill(uid: int, vnd: int):
    bills = _load_json(BILL_FILE, [])
    bill_id = len(bills) + 1
    bills.append({
        "id": bill_id,
        "uid": uid,
        "vnd": vnd,
        "status": "WAIT",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    _save_json(BILL_FILE, bills)
    return bill_id

def approve_bill(bill_id: int):
    bills = _load_json(BILL_FILE, [])
    for b in bills:
        if b["id"] == bill_id and b["status"] == "WAIT":
            usdt = round(b["vnd"] / USDT_RATE, 2)
            b["status"] = "DONE"
            add_balance(b["uid"], usdt)
            _save_json(BILL_FILE, bills)
            return b["uid"], usdt
    return None, 0.0

# =============================
# ✅ CHỐNG 2 BILL / 1 USER
# =============================
def has_pending_bill(uid: int) -> bool:
    bills = _load_json(BILL_FILE, [])
    for b in bills:
        if b["uid"] == uid and b["status"] == "WAIT":
            return True
    return False

# =============================
# FORMAT PREDICTION
# =============================
def format_prediction(dai: str, preds: list[str]) -> str:
    name = DAI_MAP.get(dai, "?")
    if not preds:
        return f"🎯 {name}\n⚠ Chưa đủ dữ liệu"
    return f"🎯 Dự đoán – {name}\n\n{' '.join(preds)}"

# =============================
# PREDICTION WITH FEE
# =============================
def get_prediction_with_fee(uid: int, dai: str) -> str:
    bal = get_balance(uid)
    if bal < ANALYZE_FEE:
        return (
            f"❌ Không đủ số dư\n"
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
    )

# =============================
# AUTO DAILY
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
# KEYBOARD
# =============================
def menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎯 Dự đoán", callback_data="pred_menu")],
            [InlineKeyboardButton("💳 Nạp tiền", callback_data="deposit")],
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

    # 🚫 CHẶN NGAY TỪ MENU
    if data == "deposit":
        if has_pending_bill(uid):
            await q.edit_message_text(
                "❌ Bạn đang có 1 bill chưa được duyệt.\n"
                "📌 Vui lòng chờ admin xử lý trước khi nạp tiếp.\n\n"
                f"📞 Admin: @{ADMIN_USERNAME}",
                reply_markup=menu_keyboard()
            )
            return

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
            await q.edit_message_text(
                get_prediction_with_fee(uid, dai),
                reply_markup=menu_keyboard()
            )
            return

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    text = update.message.text.strip()

    if ctx.user_data.get("deposit"):
        # 🚫 CHẶN LẦN CUỐI (AN TOÀN TUYỆT ĐỐI)
        if has_pending_bill(uid):
            await update.message.reply_text(
                "❌ Bạn đã có bill đang chờ duyệt.\n"
                "📌 Không thể tạo bill mới.\n\n"
                f"📞 Admin: @{ADMIN_USERNAME}"
            )
            ctx.user_data.clear()
            return

        try:
            vnd = int(text.replace(",", ""))
            if vnd < MIN_DEPOSIT_VND:
                raise ValueError
        except:
            await update.message.reply_text("❌ Số tiền không hợp lệ")
            return

        bill_id = create_bill(uid, vnd)
        ctx.user_data.clear()

        caption = (
            f"🏦 THÔNG TIN CHUYỂN KHOẢN\n"
            f"💰 {vnd:,} VND\n"
            f"🧾 Nội dung CK: ID {uid}\n\n"
            f"📌 Sau khi chuyển khoản, chờ admin duyệt\n"
            f"📞 Admin: @{ADMIN_USERNAME}"
        )

        try:
            with open(BANK_QR_PATH, "rb") as f:
                await update.message.reply_photo(photo=f, caption=caption)
        except:
            await update.message.reply_text(caption)

# =============================
# APP INIT
# =============================
app = Application.builder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("menu", menu_cmd))
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
