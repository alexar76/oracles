# Build from the monorepo root: docker build -f oracles/aestus/Dockerfile .
FROM python:3.11-slim
WORKDIR /app

COPY core /app/core
COPY oracles/aestus /app/aestus

RUN pip install --no-cache-dir -e /app/core -e /app/aestus

EXPOSE 9312
CMD ["python", "-m", "aestus.main"]
