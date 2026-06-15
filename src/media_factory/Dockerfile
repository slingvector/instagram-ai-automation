FROM python:3.11-slim

# Install FFmpeg, Fontconfig, and required system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg fontconfig fonts-noto-color-emoji wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Rebuild the system font cache so libass knows the font exists
RUN fc-cache -f -v

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run requirement: Listen on $PORT
ENV PORT=8080

# Run the web service on container startup.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
