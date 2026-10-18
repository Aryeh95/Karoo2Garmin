FROM python:3.11-slim

ARG VERSION=1.0.2
ARG REVISION=unknown
ARG CREATED=""

LABEL maintainer="erwinvol" \
      org.opencontainers.image.title="Karoo2Garmin" \
      org.opencontainers.image.description="Automatic sync service between Hammerhead Karoo and Garmin Connect with FIT device spoofing" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.created="${CREATED}" \
      org.opencontainers.image.source="https://github.com/erwinvol/Karoo2Garmin" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    GARMIN_TOKEN_DIR=/data/garmin_tokens \
    SYNC_INTERVAL_MINUTES=60

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create data directory
RUN mkdir -p /data/garmin_tokens

# Copy application source
COPY src/ /app/src/

VOLUME ["/data"]

ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--daemon"]
