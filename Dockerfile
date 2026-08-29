FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

RUN addgroup --system cropsage && adduser --system --ingroup cropsage cropsage

COPY --chown=cropsage:cropsage api ./api
COPY --chown=cropsage:cropsage agent ./agent
COPY --chown=cropsage:cropsage services ./services
COPY --chown=cropsage:cropsage scoring ./scoring
COPY --chown=cropsage:cropsage providers ./providers
COPY --chown=cropsage:cropsage data ./data

USER cropsage
EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
