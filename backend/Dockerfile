FROM python:3.11-slim

WORKDIR /app

# Install dependencies as root, then drop to non-root user
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user for security. /uploads is pre-created (with appuser
# ownership) here, not left for a volume mount to create on first use --
# Docker copies a fresh named volume's initial content/ownership from
# whatever already exists at the mount path in the image, so this is what
# makes docker-compose.yml's uploads_data:/uploads volume writable by
# appuser instead of defaulting to root ownership (production mounts its
# own volume at /app/uploads instead and isn't affected either way).
RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /uploads \
    && chown -R appuser /app /uploads
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
