FROM python:3.10

# Set working directory
WORKDIR /app

# Copy requirements before copying code (cache layer)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ source code vào /app
COPY . .

# Run bot
CMD ["python3", "bot_tele.py"]
