
# Stage 1: Builder
FROM python:3.13-slim-bookworm AS builder

WORKDIR /build

COPY requirements.txt .

RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# Stage 2: Runtime
FROM python:3.13-slim-bookworm AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=5000

COPY --from=builder /wheels /wheels
COPY requirements.txt .

RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY app.py .
COPY templates/ ./templates/
COPY static/ ./static/

EXPOSE 5000

CMD ["python", "app.py"]
