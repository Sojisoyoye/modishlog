FROM python:3.11-slim

WORKDIR /app

# libmagic1: the shared C library python-magic (requirements.txt) binds to
# for MIME-sniffing file uploads (S6). `pip install python-magic` only
# installs the Python wrapper -- without this system package, every call
# to magic.from_buffer() raises ImportError at the `import magic` line,
# which upload_product_image() and bulk_upload_products_endpoint() both
# convert to a RuntimeError, 500ing on every real upload. This was never
# caught by CI because no test actually imports the real `magic` module
# against a real libmagic (see test_security_fixes.py's magic-related
# test -- it only greps the source for the string "magic").
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

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
