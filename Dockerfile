# Sử dụng Python 3.10
FROM python:3.10-slim

# Tạo thư mục làm việc
WORKDIR /app

# Copy toàn bộ code vào container
COPY . /app

# Cài dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port cho Flask
EXPOSE 5000

# Chạy bot
CMD ["python3", "bot_tele.py"]
