import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from datetime import datetime, timedelta
import threading
import time
import requests

# GIẢ SỬ xoso_core.py ĐÃ ĐƯỢC CẬP NHẬT ĐỂ XỬ LÝ 18 LÔ (KHÔNG CHỈNH SỬA Ở ĐÂY)
from xoso_core import (
    save_today_numbers,
    get_prediction_for_dai,
    get_last_n_history,
    stats_for_dai,
    backup_data,
    DAI_MAP,
    clear_history
)

# ============================
# CONFIG
# ============================

BOT_TOKEN = "8502101079:AAF7Ba9k6Z4sA4TWdWhOydpmOH6SgL9WVAA"
AUTO_CHAT_ID = 0

WAITING_INPUT = {}
LAST_SELECTED_DAI = {}   # đài user thao tác gần nhất


# ============================
# FORMAT PREDICTION
# SỬA: Hướng dẫn nhập từ 27 số sang 18 số (XSMN)
# ============================
def format_prediction(dai, preds):
    name = DAI_MAP.get(dai, "?")

    if not preds or (len(preds) == 1 and "Chưa có dữ liệu" in preds[0]):
        return (
            f"🎯 {name}:\n"
            f"⚠ Chưa đủ dữ liệu để dự đoán!\n\n"
            f"👉 Bạn cần nhập ít nhất 3 ngày gần nhất.\n"
            f"📌 Nhấn Nhập và gửi 18 số dạng:\n"
            f"`00 11 22 ...`" # SỬA: Hướng dẫn nhập 18 số
        )

    # Vẫn giữ dàn 12 số dự đoán, có thể đổi tùy logic 'xoso_core'
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


# ============================
# AUTO DAILY AT 16:35
# ============================
def send_auto(text):
    if not AUTO_CHAT_ID:
        print("AUTO_CHAT_ID chưa cấu hình.")
        return

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": AUTO_CHAT_ID, "text": text},
    )


def auto_scheduler():
    while True:
        now = datetime.now()
        # XSMN quay lúc 16:15, 16:35 là thời gian hợp lý để auto dự đoán
        run = now.replace(hour=16, minute=35, second=0, microsecond=0) 
        if now >= run:
            run += timedelta(days=1)
        wait = (run - now).total_seconds()

        print(f"⏳ Chờ đến {run} để auto...")
        time.sleep(wait)

        msg = "📅 Auto dự đoán:\n\n"
        for dai in ["1", "2", "3"]:
            preds = get_prediction_for_dai(dai)
            msg += format_prediction(dai, preds) + "\n\n"

        send_auto(msg)
        backup_data()
        print("✔ Auto xong 1 lượt.")


# ============================
# KEYBOARD UI
# ============================
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


# ============================
# COMMANDS
# ============================
async def start(update: Update, context):
    await update.message.reply_text(
        "🤖 Bot đã sẵn sàng!\n👉 Nhấn /menu để mở giao diện.",
    )


async def menu_cmd(update: Update, context):
    await update.message.reply_text(
        "📌 Chọn chức năng:",
        reply_markup=menu_keyboard()
    )


# ============================
# MENU CALLBACK
# ============================
async def menu_callback(update: Update, context):
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

    if dai not in ("1", "2", "3"):
        await q.edit_message_text("❌ Lỗi đài!", reply_markup=menu_keyboard())
        return

    LAST_SELECTED_DAI[q.from_user.id] = dai  # lưu đài user vừa chọn

    if action == "pred":
        preds = get_prediction_for_dai(dai)
        await q.edit_message_text(format_prediction(dai, preds), reply_markup=menu_keyboard())
        return

    if action == "hist":
        hist = get_last_n_history(dai, 7)
        if not hist:
            await q.edit_message_text("📭 Chưa có lịch sử!", reply_markup=menu_keyboard())
            return

        msg = f"📜 Lịch sử – {DAI_MAP[dai]}:\n"
        for h in hist:
            msg += f"- {h['date']}: {' '.join(h['numbers'])}\n"

        await q.edit_message_text(msg, reply_markup=menu_keyboard())
        return

    if action == "stat":
        st = stats_for_dai(dai, 7)
        if not st:
            await q.edit_message_text("📭 Chưa đủ dữ liệu để thống kê!", reply_markup=menu_keyboard())
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
            reply_markup=menu_keyboard()
        )
        return

    # ============================
    # INPUT MODE 
    # SỬA: Hướng dẫn nhập từ 27 số sang 18 số
    # ============================
    if action == "input":
        uid = q.from_user.id

        # ⭐ Nếu user đã chọn đài trước đó → nhập đúng đài đó, không hỏi lại
        if uid in LAST_SELECTED_DAI:
            dai = LAST_SELECTED_DAI[uid]
            WAITING_INPUT[uid] = dai
            await q.edit_message_text(
                f"📝 Bạn đang nhập số cho {DAI_MAP[dai]}.\n"
                f"👉 Gửi 18 số (cách nhau bởi khoảng trắng):" # SỬA: Hướng dẫn nhập 18 số
            )
            return

        # ⭐ Nếu là lần đầu → hỏi chọn đài
        await q.edit_message_text(
            "📌 Chọn đài muốn nhập số:",
            reply_markup=dai_select_keyboard("input")
        )
        return


# ============================
# HANDLE 18-NUMBER INPUT
# SỬA: Thay đổi kiểm tra số lượng từ 27 sang 18
# ============================
async def handle_input(update: Update, context):
    uid = update.message.from_user.id

    if uid not in WAITING_INPUT:
        return

    dai = WAITING_INPUT.pop(uid)
    LAST_SELECTED_DAI[uid] = dai

    parts = update.message.text.strip().split()
    
    # 💥 THAY ĐỔI LỚN NHẤT: Kiểm tra 18 số (lô)
    if len(parts) != 18:
        WAITING_INPUT[uid] = dai
        await update.message.reply_text(
            "❌ Bạn phải nhập đúng 18 số (18 lô XSMN)!\nGõ lại theo dạng:\n`00 11 22 ...`" # SỬA: Thông báo lỗi 18 số
        )
        return

    nums = []
    for x in parts:
        if not x.isdigit():
            await update.message.reply_text("❌ Sai định dạng số!")
            return
        # Định dạng luôn là 2 chữ số (vd: 09, 10, 99)
        nums.append(f"{int(x):02d}") 

    today = datetime.now().strftime("%Y-%m-%d")
    last_hist = get_last_n_history(dai, 1)
    is_new_day = last_hist and last_hist[0]["date"] != today

    save_today_numbers(dai, nums)

    header = (
        f"📅 Ngày mới: {today}\n"
        f"📝 Đã lưu bộ số cho {DAI_MAP[dai]}!\n\n"
        if is_new_day else
        f"📝 Đã cập nhật bộ số cho {DAI_MAP[dai]}!\n\n"
    )

    preds = get_prediction_for_dai(dai)

    await update.message.reply_text(
        header +
        f"🎯 Bộ số hôm nay:\n{' '.join(nums)}\n\n" +
        format_prediction(dai, preds),
        reply_markup=menu_keyboard()
    )


# ============================
# MAIN APP
# ============================
def main():
    threading.Thread(target=auto_scheduler, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))

    print("Bot đang chạy…")
    app.run_polling()


if __name__ == "__main__":

    main()
