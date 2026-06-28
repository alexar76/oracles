# Build from the monorepo root: docker build -f oracles/fourier/Dockerfile .
FROM python:3.11-slim
WORKDIR /app

COPY core /app/core
COPY oracles/fourier /app/fourier

RUN pip install --no-cache-dir -e /app/core -e /app/fourier

EXPOSE 9315
CMD ["python", "-m", "fourier.main"]
