import os, json, threading, time
from datetime import datetime, timedelta

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
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
# CONFIG
# =============================

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Thiếu BOT_TOKEN")

ADMIN_USERNAME = "x117277"
ADMIN_IDS = {5546717219}

ANALYZE_FEE = 3.0

BALANCE_FILE = "balances.json"
TX_LOG_FILE = "tx_logs.json"

AUTO_CHAT_ID = int(os.getenv("AUTO_CHAT_ID", "0"))

PORT = int(os.environ.get("PORT", "10000"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_URL = f"{RENDER_URL}/{BOT_TOKEN}"

WAITING_INPUT = {}
LAST_SELECTED_DAI = {}

# =============================
# BALANCE & LOG
# =============================

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_balance(uid: int) -> float:
    return load_json(BALANCE_FILE).get(str(uid), 0.0)

def add_balance(uid: int, amount: float):
    data = load_json(BALANCE_FILE)
    k = str(uid)
    data[k] = round(data.get(k, 0.0) + amount, 2)
    save_json(BALANCE_FILE, data)

def deduct_balance(uid: int, amount: float) -> bool:
    data = load_json(BALANCE_FILE)
    k = str(uid)
    if data.get(k, 0.0) < amount:
        return False
    data[k] = round(data[k] - amount, 2)
    save_json(BALANCE_FILE, data)
    return True

def log_tx(uid: int, amount: float, note: str):
    logs = load_json(TX_LOG_FILE)
    logs[str(time.time())] = {
        "user_id": uid,
        "amount": amount,
        "note": note,
        "time": datetime.now().isoformat()
    }
    save_json(TX_LOG_FILE, logs)

# =============================
# FORMAT
# =============================

def format_prediction(dai, preds):
    name = DAI_MAP[dai]
    if not preds:
        return "⚠ Chưa đủ dữ liệu."
    return (
        f"🎯 Dự đoán – {name}\n\n"
        f"{' '.join(preds[:6])}\n"
        f"{' '.join(preds[6:12])}"
    )

# =============================
# KEYBOARD
# =============================

def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Dự đoán", callback_data="pred_menu")],
        [
            InlineKeyboardButton("💳 Số dư", callback_data="balance"),
            InlineKeyboardButton("📜 Lịch sử", callback_data="hist_menu")
        ],
        [
            InlineKeyboardButton("📊 Thống kê", callback_data="stat_menu"),
            InlineKeyboardButton("📝 Nhập", callback_data="input_menu")
        ],
        [InlineKeyboardButton("🗑 Xóa", callback_data="del_menu")]
    ])

def dai_keyboard(prefix):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Đài 1", callback_data=f"{prefix}_1"),
            InlineKeyboardButton("Đài 2", callback_data=f"{prefix}_2"),
            InlineKeyboardButton("Đài 3", callback_data=f"{prefix}_3"),
        ],
        [InlineKeyboardButton("⬅ Menu", callback_data="menu")]
    ])

# =============================
# COMMANDS
# =============================

async def start(update: Update, ctx):
    await update.message.reply_text("🤖 Bot sẵn sàng\n/menu để mở")

async def menu(update: Update, ctx):
    await update.message.reply_text("📌 Chọn chức năng", reply_markup=menu_keyboard())

async def balance_cmd(update: Update, ctx):
    bal = get_balance(update.message.from_user.id)
    await update.message.reply_text(f"💳 Số dư: {bal} USDT")

async def addmoney(update: Update, ctx):
    if update.message.from_user.id not in ADMIN_IDS:
        return
    try:
        uid = int(ctx.args[0])
        amount = float(ctx.args[1])
    except:
        await update.message.reply_text("/addmoney user_id amount")
        return

    add_balance(uid, amount)
    log_tx(uid, amount, "ADMIN ADD")
    await update.message.reply_text(
        f"✅ Đã cộng {amount} USDT\nSố dư: {get_balance(uid)}"
    )

# =============================
# CALLBACK
# =============================

async def callback(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data == "menu":
        await q.edit_message_text("📌 Menu", reply_markup=menu_keyboard())
        return

    if data == "balance":
        await q.edit_message_text(
            f"💳 Số dư hiện tại: {get_balance(uid)} USDT",
            reply_markup=menu_keyboard()
        )
        return

    if data.endswith("_menu"):
        await q.edit_message_text("📌 Chọn đài", reply_markup=dai_keyboard(data.split("_")[0]))
        return

    action, dai = data.split("_")

    if action == "pred":
        if get_balance(uid) < ANALYZE_FEE:
            await q.edit_message_text(
                f"❌ Không đủ số dư\n"
                f"Phí: {ANALYZE_FEE} USDT\n"
                f"👉 @{ADMIN_USERNAME}"
            )
            return

        deduct_balance(uid, ANALYZE_FEE)
        log_tx(uid, -ANALYZE_FEE, "ANALYZE")

        preds = get_prediction_for_dai(dai)
        await q.edit_message_text(
            format_prediction(dai, preds),
            reply_markup=menu_keyboard()
        )

# =============================
# INPUT 18 NUMBERS
# =============================

async def handle_input(update: Update, ctx):
    uid = update.message.from_user.id
    if uid not in WAITING_INPUT:
        return

    dai = WAITING_INPUT.pop(uid)
    nums = update.message.text.split()
    if len(nums) != 18:
        await update.message.reply_text("❌ Phải nhập 18 số")
        return

    save_today_numbers(dai, nums)
    await update.message.reply_text("✅ Đã lưu", reply_markup=menu_keyboard())

# =============================
# AUTO
# =============================

def auto_scheduler():
    while True:
        now = datetime.now()
        run = now.replace(hour=16, minute=35, second=0)
        if now >= run:
            run += timedelta(days=1)
        time.sleep((run - now).total_seconds())

        if AUTO_CHAT_ID:
            msg = "📅 Auto dự đoán\n\n"
            for d in ["1", "2", "3"]:
                msg += format_prediction(d, get_prediction_for_dai(d)) + "\n\n"

            httpx.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": AUTO_CHAT_ID, "text": msg}
            )
        backup_data()

# =============================
# MAIN
# =============================

app = Application.builder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(CommandHandler("balance", balance_cmd))
app.add_handler(CommandHandler("addmoney", addmoney))
app.add_handler(CallbackQueryHandler(callback))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))

def main():
    if AUTO_CHAT_ID:
        threading.Thread(target=auto_scheduler, daemon=True).start()

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    main()
