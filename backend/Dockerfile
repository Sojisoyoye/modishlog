FROM python:3.11-slim

WORKDIR /app

# Install dependencies as root, then drop to non-root user
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python -c "import cmdstanpy; cmdstanpy.install_cmdstan(dir='/usr/local/lib/python3.11/site-packages/prophet/stan_model/', overwrite=True)"

COPY . .

# Non-root user for security
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
