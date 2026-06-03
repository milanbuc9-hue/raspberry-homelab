FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
# Beim Boot kann der Container schneller starten als DNS bereit ist → discord.com
# erst abwarten, sonst crasht der Bot mit ClientConnectorDNSError und zaehlt RestartCount hoch.
CMD ["sh", "-c", "until getent hosts discord.com >/dev/null 2>&1; do echo 'warte auf DNS...'; sleep 2; done; exec python -u bot.py"]
