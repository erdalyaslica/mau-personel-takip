FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY mau_rehber.py telegram_bot.py telegram_service.py ./
CMD ["python", "-u", "telegram_service.py"]
