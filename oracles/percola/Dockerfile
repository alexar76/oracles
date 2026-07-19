# Build from the monorepo root: docker build -f oracles/percola/Dockerfile .
FROM python:3.11-slim
WORKDIR /app

COPY core /app/core
COPY oracles/percola /app/percola

RUN pip install --no-cache-dir -e /app/core -e /app/percola

EXPOSE 9306
CMD ["python", "-m", "percola.main"]
