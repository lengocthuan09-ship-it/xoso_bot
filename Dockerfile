FROM python:3.10-slim

WORKDIR /app

# Copy file requirements trước để cache
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ project
COPY . .

# Hiển thị file để debug
RUN ls -la /app

# Chạy bot
CMD ["python3", "bot_tele.py"]
