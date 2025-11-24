import os
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
    raise RuntimeError("Thiếu BOT_TOKEN trong Environment variables của Render!")

# Nếu muốn auto gửi mỗi ngày thì set AUTO_CHAT_ID trong Environment
AUTO_CHAT_ID = int(os.getenv("AUTO_CHAT_ID", "0"))

WAITING_INPUT: dict[int, str] = {}
LAST_SELECTED_DAI: dict[int, str] = {}

# Render sẽ set biến PORT. Nếu không có thì dùng 10000 (local)
PORT = int(os.environ.get("PORT", "10000"))

# URL public của service trên Render
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://xoso-bot.onrender.com")
WEBHOOK_PATH = f"/{BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# =============================
# FORMAT PREDICTION
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
        f"👉 Nhấn Dự đoán để cập nhật lại."
    )

# =============================
# AUTO DAILY AT 16:35 (dùng httpx, không ảnh hưởng event loop)
# =============================

def send_auto(text: str) -> None:
    if not AUTO_CHAT_ID:
        # không cấu hình AUTO_CHAT_ID thì bỏ qua, tránh lỗi
        print("AUTO_CHAT_ID chưa cấu hình, bỏ qua auto gửi.")
        return

    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": AUTO_CHAT_ID, "text": text},
            timeout=30.0,
        )
        print("Auto send status:", resp.status_code, resp.text[:200])
    except Exception as e:
        print("Lỗi khi auto send:", e)

def auto_scheduler() -> None:
    while True:
        now = datetime.now()
        # 16:35 hằng ngày
        run = now.replace(hour=16, minute=35, second=0, microsecond=0)
        if now >= run:
            run += timedelta(days=1)

        wait = (run - now).total_seconds()
        print(f"⏳ Scheduler: chờ đến {run} để auto dự đoán…")
        time.sleep(max(wait, 1))

        msg = "📅 Auto dự đoán:\n\n"
        for dai in ["1", "2", "3"]:
            preds = get_prediction_for_dai(dai)
            msg += format_prediction(dai, preds) + "\n\n"

        send_auto(msg)
        backup_data()
        print("✔ Auto xong 1 lượt.")

# =============================
# KEYBOARD UI
# =============================

def menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎯 Dự đoán", callback_data="pred_menu")],
            [
                InlineKeyboardButton("📜 Lịch sử", callback_data="hist_menu"),
                InlineKeyboardButton("📊 Thống kê", callback_data="stat_menu"),
            ],
            [
                InlineKeyboardButton("🗑 Xóa", callback_data="del_menu"),
                InlineKeyboardButton("📝 Nhập", callback_data="input_menu"),
            ],
        ]
    )

def dai_select_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Đài 1 (TP.HCM)", callback_data=f"{prefix}_1"),
                InlineKeyboardButton("Đài 2 (Vĩnh Long)", callback_data=f"{prefix}_2"),
                InlineKeyboardButton("Đài 3 (An Giang)", callback_data=f"{prefix}_3"),
            ],
            [InlineKeyboardButton("⬅ Quay lại", callback_data="menu_main")],
        ]
    )

# =============================
# COMMANDS
# =============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 Bot đã sẵn sàng!\n"
        "👉 Nhấn /menu để mở giao diện.",
    )

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📌 Chọn chức năng:",
        reply_markup=menu_keyboard(),
    )

# =============================
# MENU CALLBACK
# =============================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "menu_main":
        await q.edit_message_text("📌 Chọn chức năng:", reply_markup=menu_keyboard())
        return

    if data.endswith("_menu"):
        prefix = data.split("_")[0]
        await q.edit_message_text(
            "📌 Chọn đài:",
            reply_markup=dai_select_keyboard(prefix),
        )
        return

    action, dai = data.split("_")

    if dai not in ("1", "2", "3"):
        await q.edit_message_text("❌ Lỗi đài!", reply_markup=menu_keyboard())
        return

    LAST_SELECTED_DAI[q.from_user.id] = dai

    if action == "pred":
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
                f"📊 {DAI_MAP[dai]}: chưa đủ dữ liệu thống kê!",
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
        uid = q.from_user.id
        WAITING_INPUT[uid] = dai
        await q.edit_message_text(
            f"📝 Nhập 18 số cho {DAI_MAP[dai]} theo dạng:\n"
            f"00 11 22 ...",
        )
        return

# =============================
# HANDLE 18-NUMBER INPUT
# =============================

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.message.from_user.id

    if uid not in WAITING_INPUT:
        # tin nhắn thường, bỏ qua
        return

    dai = WAITING_INPUT.pop(uid)
    LAST_SELECTED_DAI[uid] = dai

    parts = update.message.text.strip().split()
    if len(parts) != 18:
        WAITING_INPUT[uid] = dai
        await update.message.reply_text(
            "❌ Bạn phải nhập đúng 18 số (18 lô XSMN)!\n"
            "Ví dụ: 00 11 22 ..."
        )
        return

    nums: list[str] = []
    for x in parts:
        if not x.isdigit():
            await update.message.reply_text("❌ Sai định dạng số, chỉ nhập số 0-99!")
            return
        nums.append(f"{int(x):02d}")

    today = datetime.now().strftime("%Y-%m-%d")
    save_today_numbers(dai, nums)

    preds = get_prediction_for_dai(dai)

    await update.message.reply_text(
        f"📅 Đã lưu bộ số cho {DAI_MAP[dai]} ngày {today}!\n\n"
        f"🎯 Bộ số hôm nay:\n{' '.join(nums)}\n\n"
        + format_prediction(dai, preds),
        reply_markup=menu_keyboard(),
    )

# =============================
# TẠO APPLICATION & ĐĂNG KÝ HANDLER
# =============================

application = Application.builder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("menu", menu_cmd))
application.add_handler(CallbackQueryHandler(menu_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))

# =============================
# MAIN
# =============================

def main() -> None:
    # chạy auto scheduler ở thread riêng (nếu cấu hình AUTO_CHAT_ID)
    if AUTO_CHAT_ID:
        threading.Thread(target=auto_scheduler, daemon=True).start()
    else:
        print("Không cấu hình AUTO_CHAT_ID, auto scheduler sẽ không gửi tin.")

    print("Starting bot with webhook...")
    print("Webhook URL:", WEBHOOK_URL)
    # run_webhook sẽ:
    #  - mở web server trên PORT (Render yêu cầu)
    #  - setWebhook tới WEBHOOK_URL
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,   # đường dẫn /<BOT_TOKEN>
        webhook_url=WEBHOOK_URL,
    )

if __name__ == "__main__":
    main()
