import os
import json
import threading
import time
from datetime import datetime, timedelta

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
# CONFIG
# =============================

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Thiếu BOT_TOKEN")

AUTO_CHAT_ID = int(os.getenv("AUTO_CHAT_ID", "0"))

PORT = int(os.environ.get("PORT", "10000"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = f"/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

ADMIN_USERNAME = "x117277"
ADMIN_IDS = {5546717219}   # 🔴 TELEGRAM ID ADMIN

ANALYZE_FEE = 3.0

BALANCE_FILE = "balances.json"
TX_LOG_FILE = "tx_logs.json"

WAITING_INPUT: dict[int, str] = {}
LAST_SELECTED_DAI: dict[int, str] = {}

# =============================
# BALANCE & LOG
# =============================

def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_balance(uid: int) -> float:
    return _load_json(BALANCE_FILE).get(str(uid), 0.0)

def add_balance(uid: int, amount: float):
    data = _load_json(BALANCE_FILE)
    k = str(uid)
    data[k] = round(data.get(k, 0.0) + amount, 2)
    _save_json(BALANCE_FILE, data)

def deduct_balance(uid: int, amount: float) -> bool:
    data = _load_json(BALANCE_FILE)
    k = str(uid)
    if data.get(k, 0.0) < amount:
        return False
    data[k] = round(data[k] - amount, 2)
    _save_json(BALANCE_FILE, data)
    return True

def log_tx(uid: int, amount: float, note: str):
    logs = _load_json(TX_LOG_FILE)
    logs[str(time.time())] = {
        "user_id": uid,
        "amount": amount,
        "note": note,
        "time": datetime.now().isoformat()
    }
    _save_json(TX_LOG_FILE, logs)

# =============================
# FORMAT PREDICTION (GIỮ NGUYÊN)
# =============================

def format_prediction(dai: str, preds: list[str]) -> str:
    name = DAI_MAP.get(dai, "?")

    if not preds or (len(preds) == 1 and "Chưa có dữ liệu" in preds[0]):
        return (
            f"🎯 {name}:\n"
            f"⚠ Chưa đủ dữ liệu để dự đoán!\n\n"
            f"👉 Bạn cần nhập ít nhất 3 ngày gần nhất.\n"
            f"📌 Gửi 18 số (2 chữ số, cách nhau bởi khoảng trắng):\n"
            f"vd: 00 11 22 ..."
        )

    line1 = " – ".join(preds[:6])
    line2 = " – ".join(preds[6:12])
    all_nums = " ".join(preds)

    return (
        f"🎯 Dự đoán 12 lô – {name}\n\n"
        f"📌 Bộ số dễ về nhất:\n"
        f"➡️ {line1}\n"
        f"➡️ {line2}\n\n"
        f"🎯 Dàn 12 số đầy đủ:\n"
        f"{all_nums}\n\n"
        f"💸 Phí phân tích: {ANALYZE_FEE} USDT"
    )

# =============================
# AUTO DAILY 16:35
# =============================

def send_auto(text: str):
    if not AUTO_CHAT_ID:
        return
    httpx.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": AUTO_CHAT_ID, "text": text},
        timeout=30
    )

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

        send_auto(msg)
        backup_data()

# =============================
# KEYBOARD UI (THÊM 💳 SỐ DƯ)
# =============================

def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Dự đoán", callback_data="pred_menu")],
        [
            InlineKeyboardButton("💳 Số dư", callback_data="balance"),
            InlineKeyboardButton("📜 Lịch sử", callback_data="hist_menu"),
        ],
        [
            InlineKeyboardButton("📊 Thống kê", callback_data="stat_menu"),
            InlineKeyboardButton("📝 Nhập", callback_data="input_menu"),
        ],
        [InlineKeyboardButton("🗑 Xóa", callback_data="del_menu")],
    ])

def dai_select_keyboard(prefix: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Đài 1 (TP.HCM)", callback_data=f"{prefix}_1"),
            InlineKeyboardButton("Đài 2 (Vĩnh Long)", callback_data=f"{prefix}_2"),
            InlineKeyboardButton("Đài 3 (An Giang)", callback_data=f"{prefix}_3"),
        ],
        [InlineKeyboardButton("⬅ Quay lại", callback_data="menu_main")],
    ])

# =============================
# COMMANDS
# =============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot đã sẵn sàng!\n👉 Nhấn /menu để mở."
    )

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Chọn chức năng:",
        reply_markup=menu_keyboard(),
    )

async def addmoney_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from_user = update.message.from_user

    # Không phải admin → báo rõ
    if from_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Bạn không có quyền admin.")
        return

    # Sai cú pháp → hướng dẫn rõ
    if len(context.args) != 2:
        await update.message.reply_text(
            "⚠ Cú pháp đúng:\n"
            "/addmoney <user_id> <amount>\n\n"
            "Ví dụ:\n"
            "/addmoney 123456789 10"
        )
        return

    try:
        target_uid = int(context.args[0])
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ user_id hoặc amount không hợp lệ.")
        return

    if amount <= 0:
        await update.message.reply_text("❌ Số tiền phải > 0.")
        return

    add_balance(target_uid, amount)
    log_tx(target_uid, amount, f"ADMIN_ADD by {from_user.id}")

    await update.message.reply_text(
        f"✅ CỘNG TIỀN THÀNH CÔNG\n\n"
        f"👤 User ID: {target_uid}\n"
        f"💰 +{amount} USDT\n"
        f"💳 Số dư mới: {get_balance(target_uid)} USDT"
    )


# =============================
# MENU CALLBACK (TRỪ PHÍ Ở ĐÂY)
# =============================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = q.from_user.id

    if data == "menu_main":
        await q.edit_message_text("📌 Chọn chức năng:", reply_markup=menu_keyboard())
        return

    if data == "balance":
        await q.edit_message_text(
            f"💳 Số dư hiện tại: {get_balance(uid)} USDT",
            reply_markup=menu_keyboard()
        )
        return

    if data.endswith("_menu"):
        prefix = data.split("_")[0]
        await q.edit_message_text(
            "📌 Chọn đài:",
            reply_markup=dai_select_keyboard(prefix),
        )
        return

    action, dai = data.split("_")
    LAST_SELECTED_DAI[uid] = dai

    if action == "pred":
        if get_balance(uid) < ANALYZE_FEE:
            await q.edit_message_text(
                f"❌ Không đủ số dư để phân tích!\n\n"
                f"💰 Phí: {ANALYZE_FEE} USDT\n"
                f"👉 Liên hệ admin @{ADMIN_USERNAME}"
            )
            return

        deduct_balance(uid, ANALYZE_FEE)
        log_tx(uid, -ANALYZE_FEE, "ANALYZE")

        preds = get_prediction_for_dai(dai)
        await q.edit_message_text(
            format_prediction(dai, preds),
            reply_markup=menu_keyboard(),
        )
        return

    if action == "hist":
        hist = get_last_n_history(dai, 7)
        if not hist:
            await q.edit_message_text(
                f"📜 {DAI_MAP[dai]}: chưa có lịch sử!",
                reply_markup=menu_keyboard(),
            )
            return

        msg = f"📜 Lịch sử – {DAI_MAP[dai]}:\n"
        for h in hist:
            msg += f"- {h['date']}: {' '.join(h['numbers'])}\n"

        await q.edit_message_text(msg, reply_markup=menu_keyboard())
        return

    if action == "stat":
        st = stats_for_dai(dai, 7)
        if not st:
            await q.edit_message_text(
                f"📊 {DAI_MAP[dai]}: chưa đủ dữ liệu!",
                reply_markup=menu_keyboard(),
            )
            return

        msg = (
            f"📊 Thống kê – {DAI_MAP[dai]}\n"
            f"- Tổng lượt về: {st['total_draws']}\n"
            f"- Chẵn: {st['even']} | Lẻ: {st['odd']}\n"
            f"- Lô nóng nhất: {st['hot']}\n"
            f"- Lô gan nhất: {st['cold']}\n"
        )

        await q.edit_message_text(msg, reply_markup=menu_keyboard())
        return

    if action == "del":
        clear_history(dai)
        await q.edit_message_text(
            f"🗑 Đã xóa lịch sử {DAI_MAP[dai]}!",
            reply_markup=menu_keyboard(),
        )
        return

    if action == "input":
        WAITING_INPUT[uid] = dai
        await q.edit_message_text(
            f"📝 Nhập 18 số cho {DAI_MAP[dai]}:\n"
            f"00 11 22 ..."
        )
        return

# =============================
# HANDLE INPUT 18 SỐ
# =============================

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    if uid not in WAITING_INPUT:
        return

    dai = WAITING_INPUT.pop(uid)

    parts = update.message.text.strip().split()
    if len(parts) != 18:
        WAITING_INPUT[uid] = dai
        await update.message.reply_text("❌ Phải nhập đúng 18 số!")
        return

    nums = []
    for x in parts:
        if not x.isdigit():
            await update.message.reply_text("❌ Sai định dạng số!")
            return
        nums.append(f"{int(x):02d}")

    save_today_numbers(dai, nums)
    preds = get_prediction_for_dai(dai)

    await update.message.reply_text(
        f"📅 Đã lưu bộ số cho {DAI_MAP[dai]}!\n\n"
        + format_prediction(dai, preds),
        reply_markup=menu_keyboard(),
    )

# =============================
# APP
# =============================

application = Application.builder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("menu", menu_cmd))
application.add_handler(CommandHandler("addmoney", addmoney_cmd))
application.add_handler(CallbackQueryHandler(menu_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))

def main():
    if AUTO_CHAT_ID:
        threading.Thread(target=auto_scheduler, daemon=True).start()

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=WEBHOOK_URL,
    )

if __name__ == "__main__":
    main()

