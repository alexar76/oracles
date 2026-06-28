# Build from the monorepo root: docker build -f oracles/chronos/Dockerfile .
FROM python:3.11-slim
WORKDIR /app

COPY core /app/core
COPY oracles/chronos /app/chronos

RUN pip install --no-cache-dir -e /app/core -e /app/chronos

EXPOSE 9300
CMD ["python", "-m", "chronos.main"]
