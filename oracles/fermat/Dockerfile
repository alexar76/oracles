# Build from the monorepo root: docker build -f oracles/fermat/Dockerfile .
FROM python:3.11-slim
WORKDIR /app

COPY core /app/core
COPY oracles/fermat /app/fermat

RUN pip install --no-cache-dir -e /app/core -e /app/fermat

EXPOSE 9307
CMD ["python", "-m", "fermat.main"]
