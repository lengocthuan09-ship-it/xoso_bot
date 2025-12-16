# ============================
#  XOSO CORE – PHÂN TÍCH TỨC THÌ
# ============================

from collections import Counter

# MAP ĐÀI (giữ để hiển thị UI)
DAI_MAP = {
    "1": "TP.HCM",
    "2": "Vĩnh Long",
    "3": "An Giang"
}

# ============================
#  ENGINE PHÂN TÍCH 18 SỐ → 12 SỐ
# ============================

def predict_12_numbers_from_18(numbers):
    """
    Input:
        numbers: list[str] – đúng 18 số (00–99)
    Output:
        list[str] – đúng 12 số dự đoán
    """

    if not numbers or len(numbers) != 18:
        return ["Chưa đủ dữ liệu"]

    nums_int = [int(x) for x in numbers]

    # --------------------------------
    # 1️⃣ 6 số cuối user nhập
    # --------------------------------
    last6 = numbers[-6:]

    # --------------------------------
    # 2️⃣ Ghép cặp tổng % 100
    # --------------------------------
    pair_nums = []
    for i in range(len(last6)):
        for j in range(i + 1, len(last6)):
            s = (int(last6[i]) + int(last6[j])) % 100
            pair_nums.append(f"{s:02d}")

    # --------------------------------
    # 3️⃣ Tần suất cao (top 4)
    # --------------------------------
    cnt = Counter(numbers)
    freq = [num for num, _ in cnt.most_common(4)]

    # --------------------------------
    # 4️⃣ Số đặc biệt: min / max / sum%100
    # --------------------------------
    special = [
        f"{min(nums_int):02d}",
        f"{max(nums_int):02d}",
        f"{sum(nums_int) % 100:02d}",
    ]

    # --------------------------------
    # 5️⃣ Gộp & loại trùng – giữ thứ tự
    # --------------------------------
    raw = last6 + pair_nums + freq + special

    final = []
    seen = set()
    for x in raw:
        if x not in seen:
            final.append(x)
            seen.add(x)
        if len(final) == 12:
            break

    # --------------------------------
    # 6️⃣ Bù nếu chưa đủ 12 số
    # --------------------------------
    if len(final) < 12:
        for i in range(100):
            x = f"{i:02d}"
            if x not in seen:
                final.append(x)
                seen.add(x)
            if len(final) == 12:
                break

    return final


# ============================
#  API BOT GỌI TRỰC TIẾP
# ============================

def get_prediction_from_user_input(numbers):
    """
    Bot gọi hàm này trực tiếp
    """
    return predict_12_numbers_from_18(numbers)


# ============================
#  COMPAT – GIỮ TÊN CŨ (NẾU BOT ĐANG IMPORT)
# ============================

def get_prediction_for_dai(dai: str):
    """
    Hàm giữ cho khỏi lỗi import nhầm.
    KHÔNG dùng trong flow mới.
    """
    return ["Vui lòng nhập 18 số để phân tích."]
