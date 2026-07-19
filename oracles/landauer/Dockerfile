# Build from the monorepo root: docker build -f oracles/landauer/Dockerfile .
FROM python:3.11-slim
WORKDIR /app

COPY core /app/core
COPY oracles/landauer /app/landauer

RUN pip install --no-cache-dir -e /app/core -e /app/landauer

EXPOSE 9309
CMD ["python", "-m", "landauer.main"]
