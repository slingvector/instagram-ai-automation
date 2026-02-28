FROM python:3.11-slim

# Install FFmpeg and required system dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Add a stylish font for the burn-in text
# We use Impact as a widely supported, meme-friendly fallback, 
# but downloading a specific TTF is recommended for production.
RUN apt-get update && apt-get install -y fonts-liberation

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run requirement: Listen on $PORT
ENV PORT=8080

# Run the web service on container startup.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
