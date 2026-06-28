# Build from the monorepo root: docker build -f oracles/kantor/Dockerfile .
FROM python:3.11-slim
WORKDIR /app

COPY core /app/core
COPY oracles/kantor /app/kantor

RUN pip install --no-cache-dir -e /app/core -e /app/kantor

EXPOSE 9314
CMD ["python", "-m", "kantor.main"]
