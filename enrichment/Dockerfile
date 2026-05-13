FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binaries.
# The playwright-crawler-worker service uses chromium only.
# Skip for services that don't need browsers by building a separate image stage
# or by accepting the extra image size (~300 MB for chromium).
ARG INSTALL_PLAYWRIGHT_BROWSERS=false
RUN if [ "$INSTALL_PLAYWRIGHT_BROWSERS" = "true" ]; then \
        playwright install chromium --with-deps; \
    fi

COPY . .

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8010/v1/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8010"]

