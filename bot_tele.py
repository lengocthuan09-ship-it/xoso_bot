import os
import json
import threading
import time
from datetime import datetime, timedelta, timezone
VN_TZ = timezone(timedelta(hours=7))
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
    backup_data,
    DAI_MAP,
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



# =============================
# BALANCE & LOG
# =============================
def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


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
    try:
        httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": AUTO_CHAT_ID, "text": text},
            timeout=30
        )
    except Exception as e:
        print("Auto send error:", e)


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
# KEYBOARD UI 
# =============================

def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Dự đoán", callback_data="pred_menu")],
        [InlineKeyboardButton("💳 Mua USDT", callback_data="buy_usdt")],
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
    user = update.message.from_user

    uid = user.id
    username = user.username or "không có"
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

    now_vn = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M:%S")

    # ===== GỬI CHO USER (KHÔNG DÙNG MARKDOWN) =====
    try:
        await update.message.reply_text(
            "👋 Chào mừng bạn đến với Bot Dự Đoán XSMN!\n\n"
            f"🆔 UID: {uid}\n"
            f"👤 Tên: {full_name}\n"
            f"🔖 Username: @{username}\n"
            f"🕒 Thời gian: {now_vn} (VN)\n\n"
            "================================\n"
            "📌 Lưu UID để nạp tiền / liên hệ admin @x117277.\n"
            "👉 Nhấn /menu để bắt đầu."
        )
    except Exception as e:
        print("Lỗi gửi start cho user:", e)

    # ===== THÔNG BÁO ADMIN =====
    admin_msg = (
        "🚨 USER START BOT\n\n"
        f"🆔 UID: {uid}\n"
        f"👤 Tên: {full_name}\n"
        f"🔖 Username: @{username}\n"
        f"🕒 Thời gian: {now_vn} (VN)"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_msg
            )
        except Exception as e:
            print("Lỗi gửi admin notify:", e)


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

    # ===== CỘNG TIỀN =====
    add_balance(target_uid, amount)
    log_tx(target_uid, amount, f"ADMIN_ADD by {from_user.id}")

    new_balance = get_balance(target_uid)

    # ===== BÁO ADMIN =====
    await update.message.reply_text(
        f"✅ CỘNG TIỀN THÀNH CÔNG\n\n"
        f"👤 User ID: {target_uid}\n"
        f"💰 +{amount} USDT\n"
        f"💳 Số dư mới: {new_balance} USDT"
    )

    # ===== THÔNG BÁO USER =====
    try:
        await context.bot.send_message(
            chat_id=target_uid,
            text=(
                "💰 BẠN ĐÃ ĐƯỢC CỘNG TIỀN\n\n"
                f"➕ Số tiền: {amount} USDT\n"
                f"💳 Số dư hiện tại: {new_balance} USDT\n\n"
                "👉 Vui lòng gõ /menu để sử dụng bot."
            )
        )
    except Exception as e:
        # Trường hợp user chưa từng chat với bot
        print(f"Không gửi được notify cho user {target_uid}: {e}")

async def numbers_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.message.from_user.id

    dai = context.user_data.get("waiting_dai")
    if not dai:
        return

    parts = text.split()

    if len(parts) != 18 or not all(p.isdigit() and len(p) == 2 for p in parts):
        context.user_data.pop("waiting_dai", None)
        await update.message.reply_text(
            "⚠ Dữ liệu không hợp lệ!\n\n"
            "📌 Vui lòng gửi đúng 18 số (2 chữ số)\n"
            "Ví dụ:\n"
            "00 11 22 33 ..."
        )
        return


    # ===== KIỂM TRA SỐ DƯ =====
    balance = get_balance(uid)
    if balance < ANALYZE_FEE:
        context.user_data.pop("waiting_dai", None)
        await update.message.reply_text(
            f"❌ Không đủ số dư để phân tích!\n\n"
            f"💰 Phí: {ANALYZE_FEE} USDT\n"
            f"💳 Số dư hiện tại: {balance} USDT\n\n"
            f"👉 Liên hệ admin @{ADMIN_USERNAME}",
            reply_markup=menu_keyboard()
        )
        return

    # ===== TRỪ TIỀN =====
    if not deduct_balance(uid, ANALYZE_FEE):
        context.user_data.pop("waiting_dai", None)
        await update.message.reply_text(
            "❌ Giao dịch thất bại, vui lòng thử lại.",
            reply_markup=menu_keyboard()
        )
        return

    log_tx(uid, -ANALYZE_FEE, f"ANALYZE_{dai}")

     

    # ===== LƯU DỮ LIỆU =====
    save_today_numbers(dai, parts)

    # ===== LẤY KẾT QUẢ =====
    preds = get_prediction_for_dai(dai)

    context.user_data.pop("waiting_dai", None)

    await update.message.reply_text(
        "💸 ĐÃ TRỪ PHÍ PHÂN TÍCH\n"
        f"➖ {ANALYZE_FEE} USDT\n"
        f"💳 Số dư còn lại: {get_balance(uid)} USDT\n\n"
        + format_prediction(dai, preds),
        reply_markup=menu_keyboard()
    )

# =============================
# MENU CALLBACK (ĐIỀU HƯỚNG UI)
# =============================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    data = q.data

    # ===== MENU CHÍNH =====
    if data == "menu_main":
        await q.edit_message_text(
            "📌 Chọn chức năng:",
            reply_markup=menu_keyboard()
        )
        return
    if data == "buy_usdt":
        await q.edit_message_text(
            "💳 NẠP / MUA USDT\n\n"
            "👉 Vui lòng liên hệ admin:\n"
            f"@{ADMIN_USERNAME}",
            reply_markup=menu_keyboard()
        )
        return



    # ===== CHỌN ĐÀI (MENU) =====
    if data.endswith("_menu"):
        prefix = data.split("_")[0]
        await q.edit_message_text(
            "📌 Chọn đài:",
            reply_markup=dai_select_keyboard(prefix)
        )
        return

    # ===== ACTION + DAI =====
    try:
        action, dai = data.split("_")
    except ValueError:
        return
    # ==================================================
    # 🎯 DỰ ĐOÁN → CHỈ YÊU CẦU NHẬP 18 CẶP
    # ==================================================
    if action == "pred":
        context.user_data["waiting_dai"] = dai

        await q.edit_message_text(
            f"✍️ Nhập 18 cặp số cho {DAI_MAP[dai]}\n\n"
            "📌 Mỗi số gồm 2 chữ số, cách nhau bằng khoảng trắng\n"
            "📌 Gửi đúng 18 số\n\n"
            "Ví dụ:\n"
            "00 11 22 33 44 55 66 77 88 99 01 02 03 04 05 06 07 08"
        )
        return


# =============================
# APP
# =============================

application = Application.builder().token(BOT_TOKEN).build()

# ===== COMMAND =====
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("menu", menu_cmd))
application.add_handler(CommandHandler("cong", addmoney_cmd))

# ===== NHẬN 18 SỐ USER GỬI =====
application.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, numbers_input_handler)
)

# ===== CALLBACK BUTTON =====
application.add_handler(CallbackQueryHandler(menu_callback))

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












