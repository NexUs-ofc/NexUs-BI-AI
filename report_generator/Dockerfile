# Imagem do gerador de relatórios (API + Chromium do Playwright). Build na RAIZ do projeto:
#   docker build -f report_generator/Dockerfile -t nexus-bi-report .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /srv

COPY requirements.txt ./requirements.txt
COPY report_generator/requirements.txt ./report_generator/requirements.txt
RUN pip install -r requirements.txt -r report_generator/requirements.txt \
    && python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 1000 ceris

COPY --chown=ceris:ceris report_generator ./report_generator

USER ceris
EXPOSE 8001
CMD ["uvicorn", "report_generator.api:app", "--host", "0.0.0.0", "--port", "8001"]
