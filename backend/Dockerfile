# syntax=docker/dockerfile:1

# ---- Build stage ----
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.12-slim

LABEL maintainer="chatbot-backend"

RUN addgroup --system app && adduser --system --ingroup app app
RUN mkdir -p /data && chown app:app /data

COPY --from=builder /install /usr/local
WORKDIR /app
COPY . .

USER app

EXPOSE 8000

ENV DATABASE_URL="sqlite:////data/app.db" \
    ALLOWED_ORIGINS="*" \
    ENABLE_FAILURE_SIMULATION="false" \
    LLM_MODEL="gemini/gemini-2.0-flash"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
