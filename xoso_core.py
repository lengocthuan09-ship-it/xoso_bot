import json
import os
import shutil
from collections import Counter
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI

DATA_FILE = "xoso_data.json"

DAI_MAP = {
    "1": "TP.HCM",
    "2": "Vĩnh Long",
    "3": "An Giang"
}

DEFAULT_HISTORY_DAYS = 30

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
        return _init_empty_data()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _init_empty_data()

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
#  HÀM DỰ ĐOÁN 12 SỐ – “AI XÁC SUẤT”
#  DÙNG LỊCH SỬ TỚI 30 NGÀY
# ============================

def _compute_gan_metrics(hist: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """
    Tính:
      - current_age: số ngày chưa ra (gan hiện tại)
      - max_gap: khoảng cách lớn nhất giữa 2 lần ra (gan sâu)
      - last_gap: khoảng cách ngay trước lần xuất hiện gần nhất (dùng tìm gan nổ)
      - last_idx: index ngày gần nhất xuất hiện
    """
    k = len(hist)
    all_nums = [f"{i:02d}" for i in range(100)]

    metrics = {
        num: {
            "current_age": k,     # nếu chưa bao giờ ra trong N ngày thì tuổi gan = N
            "max_gap": 0,
            "last_gap": 0,
            "last_idx": -1,
        }
        for num in all_nums
    }

    for num in all_nums:
        prev_idx = None
        max_gap = 0
        last_gap = 0
        last_idx = -1

        for day_idx, day in enumerate(hist):
            day_nums = set(day["numbers"])
            if num in day_nums:
                if prev_idx is None:
                    # gap từ trước khoảng lịch sử đến ngày đầu tiên thấy
                    gap = day_idx + 1
                else:
                    gap = day_idx - prev_idx
                last_gap = gap
                if gap > max_gap:
                    max_gap = gap
                prev_idx = day_idx
                last_idx = day_idx

        # current_age
        if last_idx == -1:
            current_age = k
        else:
            current_age = (k - 1) - last_idx

        metrics[num]["current_age"] = current_age
        metrics[num]["max_gap"] = max_gap
        metrics[num]["last_gap"] = last_gap
        metrics[num]["last_idx"] = last_idx

    return metrics


def _build_ai_scores(hist: List[Dict[str, Any]]) -> List[str]:
    """
    Thuật toán “AI xác suất”:

    - Dùng lịch sử tối đa N ngày (mặc định 30)
    - Trọng số theo độ mới: ngày mới hơn điểm cao hơn
    - Score mỗi số = freq_score * 0.6 + gan_score * 0.3 + today_boost * 0.1
    - Lấy top 12 số có score cao nhất
    """

    k = len(hist)
    if k == 0:
        return ["Chưa có dữ liệu đủ để dự đoán."]

    all_nums = [f"{i:02d}" for i in range(100)]

    # 1) Tần suất có trọng số theo ngày (mới > cũ)
    freq_weighted = {num: 0.0 for num in all_nums}
    for day_idx, day in enumerate(hist):
        # ngày càng mới weight càng lớn
        weight = (day_idx + 1)
        for x in day["numbers"]:
            if x in freq_weighted:
                freq_weighted[x] += weight

    max_freq = max(freq_weighted.values()) if freq_weighted else 1.0
    if max_freq == 0:
        max_freq = 1.0

    # 2) Gan (tuổi) + gan sâu
    metrics = _compute_gan_metrics(hist)
    max_age = max(m["current_age"] for m in metrics.values()) or 1
    max_gap = max(m["max_gap"] for m in metrics.values()) or 1

    # 3) Ưu tiên các số vừa xuất hiện hôm nay & 5 lô cuối
    today_numbers = hist[-1]["numbers"] if hist[-1]["numbers"] else []
    last5_today = set(today_numbers[-5:])

    scores = {}
    for num in all_nums:
        freq_norm = freq_weighted[num] / max_freq
        age_norm = metrics[num]["current_age"] / max_age
        gap_norm = metrics[num]["max_gap"] / max_gap

        # Ưu tiên số hay ra (freq_norm) + số đang gan lớn (age_norm)
        base_score = 0.6 * freq_norm + 0.2 * age_norm + 0.2 * gap_norm

        # today boost
        today_boost = 0.1 if num in last5_today else 0.0

        scores[num] = base_score + today_boost

    # lấy top 12 theo score
    sorted_nums = sorted(all_nums, key=lambda n: scores[n], reverse=True)
    return sorted_nums[:12]


def predict_12_numbers_ai_from_history(hist: List[Dict[str, Any]]) -> List[str]:
    """
    Dự đoán 12 số dựa trên toàn bộ history (danh sách ngày).
    """
    if not hist or len(hist[-1]["numbers"]) < 10:
        return ["Không đủ dữ liệu"]
    return _build_ai_scores(hist)


# Giữ hàm cũ để tương thích, nhưng bên trong dùng AI:
def predict_12_numbers(day_numbers: List[str]) -> List[str]:
    """
    Backward-compatible: nếu chỗ khác vẫn gọi predict_12_numbers(numbers)
    thì giả lập lịch sử 1 ngày.
    """
    fake_hist = [{"date": "N/A", "numbers": day_numbers}]
    return predict_12_numbers_ai_from_history(fake_hist)


# ============================
#  LƯU – DỰ ĐOÁN
# ============================

def save_today_numbers(dai: str, numbers: List[str]):
    data = load_data()
    key = f"dai{dai}"

    today_str = datetime.now().strftime("%Y-%m-%d")

    data[key].append({
        "date": today_str,
        "numbers": numbers
    })

    save_data(data)


def get_latest_day(dai: str) -> Optional[Dict[str, Any]]:
    data = load_data()
    key = f"dai{dai}"
    lst = data.get(key, [])
    return lst[-1] if lst else None


def get_last_n_history(dai: str, n: int = DEFAULT_HISTORY_DAYS) -> List[Dict[str, Any]]:
    data = load_data()
    key = f"dai{dai}"
    hist = data.get(key, [])
    return hist[-n:] if len(hist) > n else hist


def get_prediction_for_dai(dai: str, days: int = DEFAULT_HISTORY_DAYS) -> List[str]:
    """
    Hàm chính để bot Telegram gọi:
    - Mặc định dùng lịch sử 30 ngày
    - Trả về 12 số dự đoán kiểu AI xác suất
    """
    hist = get_last_n_history(dai, days)
    if not hist:
        return ["Chưa có dữ liệu để dự đoán."]
    return predict_12_numbers_ai_from_history(hist)


# ============================
#  THỐNG KÊ MẠNH – GAN SÂU, GAN NỔ, TẦN SUẤT
# ============================

def stats_for_dai(dai: str, days: int = DEFAULT_HISTORY_DAYS) -> Optional[Dict[str, Any]]:
    hist = get_last_n_history(dai, days)
    if not hist:
        return None

    # gom tất cả số của N ngày
    flat = []
    for day in hist:
        flat.extend(day["numbers"])

    if not flat:
        return None

    cnt = Counter(flat)

    # top10 (số ra nhiều nhất)
    top10 = cnt.most_common(10)

    # bottom10 (số ra ít nhất trong 00–99)
    all_nums = [f"{i:02d}" for i in range(100)]
    lst = sorted([(x, cnt.get(x, 0)) for x in all_nums], key=lambda x: x[1])
    bottom10 = lst[:10]

    even = sum(1 for x in flat if int(x) % 2 == 0)
    odd = len(flat) - even

    hot = top10[0][0] if top10 else None

    # Tính gan sâu / gan nổ
    metrics = _compute_gan_metrics(hist)
    k = len(hist)

    # top 10 gan hiện tại (số lâu chưa ra nhất)
    current_gan_top10 = sorted(
        [(num, m["current_age"]) for num, m in metrics.items()],
        key=lambda x: x[1],
        reverse=True
    )[:10]

    # top 10 gan sâu (max_gap lớn nhất)
    max_gan_top10 = sorted(
        [(num, m["max_gap"]) for num, m in metrics.items()],
        key=lambda x: x[1],
        reverse=True
    )[:10]

    # gan nổ: số vừa ra gần đây (ngày cuối) nhưng trước đó có khoảng cách lớn
    gan_no_candidates = []
    for num, m in metrics.items():
        if m["last_idx"] == k - 1 and m["last_gap"] >= 5:
            gan_no_candidates.append((num, m["last_gap"]))
    gan_no = sorted(gan_no_candidates, key=lambda x: x[1], reverse=True)[:10]

    # “đồ thị tần suất” – dữ liệu thô để vẽ hoặc in bar chart
    frequency_chart = sorted(
        [(num, cnt.get(num, 0)) for num in all_nums],
        key=lambda x: x[1],
        reverse=True
    )

    return {
        "top10": top10,
        "bottom10": bottom10,
        "even": even,
        "odd": odd,
        "hot": hot,
        "total_draws": len(flat),
        "days": k,

        # thống kê nâng cao:
        "current_gan_top10": current_gan_top10,  # (số, số ngày chưa ra)
        "max_gan_top10": max_gan_top10,          # (số, gap lớn nhất từng có)
        "gan_no": gan_no,                        # (số, gap trước khi nổ)
        "frequency_chart": frequency_chart,      # dữ liệu để vẽ đồ thị tần suất
    }


# ============================
#  XÓA LỊCH SỬ
# ============================

def clear_history(dai: str) -> bool:
    data = load_data()
    key = f"dai{dai}"
    if key not in data:
        return False
    data[key] = []
    save_data(data)
    return True


# ============================
#  API CHO BOT TELEGRAM (FastAPI)
# ============================

app = FastAPI()


@app.get("/api/predict/{dai}")
def api_predict(dai: int, days: int = DEFAULT_HISTORY_DAYS):
    """
    GET /api/predict/1?days=30
    → trả về 12 số dự đoán cho đài 1 với lịch sử 30 ngày.
    """
    prediction = get_prediction_for_dai(str(dai), days)
    return {
        "dai": dai,
        "dai_name": DAI_MAP.get(str(dai), "Không rõ"),
        "days_used": days,
        "prediction": prediction,
    }


@app.get("/api/stats/{dai}")
def api_stats(dai: int, days: int = DEFAULT_HISTORY_DAYS):
    """
    GET /api/stats/1?days=30
    → trả về thống kê mạnh cho bot sử dụng.
    """
    stats = stats_for_dai(str(dai), days)
    if stats is None:
        return {
            "dai": dai,
            "dai_name": DAI_MAP.get(str(dai), "Không rõ"),
            "error": "Chưa có dữ liệu."
        }
    return {
        "dai": dai,
        "dai_name": DAI_MAP.get(str(dai), "Không rõ"),
        "days_used": days,
        "stats": stats,
    }


@app.get("/api/history/{dai}")
def api_history(dai: int, days: int = DEFAULT_HISTORY_DAYS):
    """
    GET /api/history/1?days=30
    → trả về lịch sử N ngày (để debug / kiểm tra).
    """
    hist = get_last_n_history(str(dai), days)
    return {
        "dai": dai,
        "dai_name": DAI_MAP.get(str(dai), "Không rõ"),
        "history": hist,
    }
