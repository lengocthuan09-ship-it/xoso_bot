FROM python:3.10

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# CHẠY ĐÚNG FILE bot_tele_fix.py !!!
CMD ["python3", "bot_tele_fix.py"]
