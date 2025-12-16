import json
import os
from collections import Counter
from datetime import datetime
import shutil

DATA_FILE = "xoso_data.json"

DAI_MAP = {
    "1": "TP.HCM",
    "2": "Vĩnh Long",
    "3": "An Giang"
}

# ============================
#  LOAD & SAVE DỮ LIỆU
# ============================

def _init_empty_data():
    return {
        "dai1": [],
        "dai2": [],
        "dai3": []
    }


def load_data():
    if not os.path.exists(DATA_FILE):
        save_data(_init_empty_data())
        return _init_empty_data()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _init_empty_data()

    # đảm bảo các key luôn tồn tại
    for k in ["dai1", "dai2", "dai3"]:
        if k not in data:
            data[k] = []

    return data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def backup_data():
    """Sao lưu file data mỗi ngày."""
    if not os.path.exists(DATA_FILE):
        return

    os.makedirs("backups", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d")
    backup_path = os.path.join("backups", f"xoso_backup_{ts}.json")
    shutil.copyfile(DATA_FILE, backup_path)


# ============================
#  HÀM DỰ ĐOÁN 12 SỐ (NÂNG CẤP)
# ============================

def predict_12_numbers(day_numbers):
    """
    Nâng cấp mạnh hơn nhưng vẫn giữ nguyên cấu trúc:
      - 5 số cuối
      - Ghép cặp (tăng lên 10 cặp)
      - Tần suất cao
      - Min – Max – Sum%100
      - Luôn đảm bảo đúng 12 số
    """

    if len(day_numbers) < 5:
        return ["Không đủ dữ liệu"]

    # ---------------------------------------
    # 1) 5 số cuối
    # ---------------------------------------
    hot = day_numbers[-5:]

    # ---------------------------------------
    # 2) Ghép cặp – nâng cấp tạo 10 số
    # ---------------------------------------
    pair_candidates = []
    for i in range(len(hot)):
        for j in range(i + 1, len(hot)):
            s = (int(hot[i]) + int(hot[j])) % 100
            pair_candidates.append(f"{s:02d}")

    pairs = pair_candidates[:10]  # tăng từ 6 → 10

    # ---------------------------------------
    # 3) Top 3 tần suất cao trong 18 lô
    # ---------------------------------------
    cnt = Counter(day_numbers)
    freq = [num for num, _ in cnt.most_common(3)]

    # ---------------------------------------
    # 4) 3 số đặc biệt: min – max – sum % 100
    # ---------------------------------------
    nums_int = [int(x) for x in day_numbers]
    mn = min(nums_int)
    mx = max(nums_int)
    special = [
        f"{mn:02d}",
        f"{mx:02d}",
        f"{(sum(nums_int) % 100):02d}",
    ]

    # ---------------------------------------
    # Gộp kết quả theo đúng logic cũ
    # ---------------------------------------
    raw = pairs + freq + special

    # Loại trùng – giữ thứ tự
    final = []
    seen = set()
    for x in raw:
        if x not in seen:
            final.append(x)
            seen.add(x)

    # ---------------------------------------
    # BỔ SUNG nếu < 12 số (fix lỗi trước đây)
    # ---------------------------------------
    if len(final) < 12:
        # lấy số ít xuất hiện nhất để tăng độ cân bằng
        all_nums = [f"{i:02d}" for i in range(100)]
        low_freq_sorted = sorted(all_nums, key=lambda n: cnt.get(n, 0))

        for x in low_freq_sorted:
            if x not in seen:
                final.append(x)
                seen.add(x)
            if len(final) == 12:
                break

    return final[:12]


# ============================
#  LƯU – DỰ ĐOÁN
# ============================

def save_today_numbers(dai: str, numbers):
    data = load_data()
    key = f"dai{dai}"

    today_str = datetime.now().strftime("%Y-%m-%d")

    data[key].append({
        "date": today_str,
        "numbers": numbers
    })

    save_data(data)


def get_latest_day(dai: str):
    data = load_data()
    key = f"dai{dai}"
    lst = data.get(key, [])
    return lst[-1] if lst else None


def get_prediction_for_dai(dai: str):
    data = load_data()
    key = f"dai{dai}"
    days = data.get(key, [])

    if not days:
        return ["Chưa có dữ liệu để dự đoán."]

    # 🔥 GỘP TOÀN BỘ SỐ (KHÔNG QUAN TÂM BAO NHIÊU NGÀY)
    all_numbers = []
    for day in days:
        all_numbers.extend(day["numbers"])

    # ❌ chưa đủ 18 số thì báo
    if len(all_numbers) < 18:
        return ["Chưa đủ dữ liệu"]

    # ✅ đủ là dự đoán NGAY
    return predict_12_numbers(all_numbers)

# ============================
#  LỊCH SỬ & THỐNG KÊ (GIỮ NGUYÊN)
# ============================

def get_last_n_history(dai: str, n: int = 7):
    data = load_data()
    key = f"dai{dai}"
    hist = data.get(key, [])
    return hist[-n:] if len(hist) > n else hist


def stats_for_dai(dai: str, days: int = 7):
    hist = get_last_n_history(dai, days)
    if not hist:
        return None

    flat = []
    for day in hist:
        flat.extend(day["numbers"])

    if not flat:
        return None

    cnt = Counter(flat)

    top10 = cnt.most_common(10)

    all_nums = [f"{i:02d}" for i in range(100)]
    lst = sorted([(x, cnt.get(x, 0)) for x in all_nums], key=lambda x: x[1])
    bottom10 = lst[:10]

    even = sum(1 for x in flat if int(x) % 2 == 0)
    odd = len(flat) - even

    hot = top10[0][0] if top10 else None

    last_seen = {num: -1 for num in all_nums}
    for idx, day in enumerate(hist):
        for x in day["numbers"]:
            last_seen[x] = idx

    cold = None
    cold_age = -1
    k = len(hist)
    for num, pos in last_seen.items():
        age = k - pos if pos >= 0 else k + 1
        if age > cold_age:
            cold = num
            cold_age = age

    return {
        "top10": top10,
        "bottom10": bottom10,
        "even": even,
        "odd": odd,
        "hot": hot,
        "cold": cold,
        "total_draws": len(flat),
        "days": k,
    }


# ============================
#  XÓA LỊCH SỬ
# ============================

def clear_history(dai: str):
    data = load_data()
    key = f"dai{dai}"
    if key not in data:
        return False
    data[key] = []
    save_data(data)
    return True

