# syntax=docker/dockerfile:1
FROM python:3.12-slim AS build
WORKDIR /build
COPY requirements.txt ./
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY --from=build /opt/venv /opt/venv
RUN python -m playwright install --with-deps chromium     && chmod -R a+rX /ms-playwright     && rm -rf /var/lib/apt/lists/*     && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 report_generator ./report_generator
RUN mkdir -p /app/output && chown 10001:10001 /app/output
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1
CMD ["uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8000"]
