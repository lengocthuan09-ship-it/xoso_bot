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
        save_data(_init_empty_data())
        return _init_empty_data()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
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
#  AI – XÁC SUẤT
# ============================

def _compute_gan_metrics(hist: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    k = len(hist)
    all_nums = [f"{i:02d}" for i in range(100)]

    metrics = {
        num: {
            "current_age": k,
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
            if num in day["numbers"]:
                if prev_idx is None:
                    gap = day_idx + 1
                else:
                    gap = day_idx - prev_idx
                last_gap = gap
                max_gap = max(max_gap, gap)
                prev_idx = day_idx
                last_idx = day_idx

        if last_idx == -1:
            current_age = k
        else:
            current_age = (k - 1) - last_idx

        metrics[num]["current_age"] = current_age
        metrics[num]["max_gap"] = max_gap
        metrics[num]["last_gap"] = last_gap
        metrics[num]["last_idx"] = last_idx

    return metrics


def _build_ai_scores(hist):
    k = len(hist)
    all_nums = [f"{i:02d}" for i in range(100)]

    freq_weighted = {num: 0.0 for num in all_nums}
    for day_idx, day in enumerate(hist):
        weight = day_idx + 1
        for x in day["numbers"]:
            freq_weighted[x] += weight

    max_freq = max(freq_weighted.values()) or 1

    metrics = _compute_gan_metrics(hist)
    max_age = max(m["current_age"] for m in metrics.values()) or 1
    max_gap = max(m["max_gap"] for m in metrics.values()) or 1

    today_last5 = set(hist[-1]["numbers"][-5:])

    scores = {}
    for num in all_nums:
        freq_norm = freq_weighted[num] / max_freq
        age_norm = metrics[num]["current_age"] / max_age
        gap_norm = metrics[num]["max_gap"] / max_gap
        today_boost = 0.1 if num in today_last5 else 0.0

        score = (
            0.6 * freq_norm +
            0.2 * age_norm +
            0.2 * gap_norm +
            today_boost
        )
        scores[num] = score

    sorted_nums = sorted(all_nums, key=lambda n: scores[n], reverse=True)
    return sorted_nums[:12]


def predict_12_numbers_ai_from_history(hist):
    if not hist or len(hist[-1]["numbers"]) < 10:
        return ["Không đủ dữ liệu"]
    return _build_ai_scores(hist)


# Compatibility
def predict_12_numbers(numbers):
    fake_hist = [{"date": "N/A", "numbers": numbers}]
    return predict_12_numbers_ai_from_history(fake_hist)


# ============================
#  LƯU – LỊCH SỬ
# ============================

def save_today_numbers(dai, numbers):
    data = load_data()
    key = f"dai{dai}"
    today = datetime.now().strftime("%Y-%m-%d")

    data[key].append({"date": today, "numbers": numbers})
    save_data(data)


def get_last_n_history(dai, n=DEFAULT_HISTORY_DAYS):
    data = load_data()
    key = f"dai{dai}"
    hist = data.get(key, [])
    return hist[-n:] if len(hist) > n else hist


# ============================
#  API CHÍNH CHO RENDER
# ============================

app = FastAPI()


@app.get("/")
def home():
    return {"status": "ok", "message": "XoSo AI API running on Render"}


@app.get("/api/predict/{dai}")
def api_predict(dai: int, days: int = DEFAULT_HISTORY_DAYS):
    hist = get_last_n_history(str(dai), days)
    prediction = predict_12_numbers_ai_from_history(hist)
    return {
        "dai": dai,
        "dai_name": DAI_MAP.get(str(dai), "Không rõ"),
        "days_used": days,
        "prediction": prediction
    }


@app.get("/api/stats/{dai}")
def api_stats(dai: int, days: int = DEFAULT_HISTORY_DAYS):
    hist = get_last_n_history(str(dai), days)
    if not hist:
        return {"error": "Chưa có dữ liệu"}

    flat = [x for h in hist for x in h["numbers"]]
    cnt = Counter(flat)

    metrics = _compute_gan_metrics(hist)

    current_gan = sorted(
        [(n, m["current_age"]) for n, m in metrics.items()],
        key=lambda x: x[1],
        reverse=True
    )[:10]

    max_gan = sorted(
        [(n, m["max_gap"]) for n, m in metrics.items()],
        key=lambda x: x[1],
        reverse=True
    )[:10]

    return {
        "dai": dai,
        "current_gan_top10": current_gan,
        "max_gan_top10": max_gan,
        "top10": cnt.most_common(10),
    }


@app.get("/api/history/{dai}")
def api_history(dai: int, days: int = DEFAULT_HISTORY_DAYS):
    hist = get_last_n_history(str(dai), days)
    return {"history": hist}
