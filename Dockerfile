# Builds an image for run_server.py (the WhatsApp webhook) only.
# run_voice.py is deliberately NOT containerized — see docker-compose.yml
# for why desktop automation and mic/speaker access don't containerize
# cleanly across platforms.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "run_server.py"]
