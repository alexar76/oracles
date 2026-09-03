# Build from the monorepo root: docker build -f oracles/betti/Dockerfile .
FROM python:3.11-slim
WORKDIR /app

COPY core /app/core
COPY oracles/betti /app/betti

RUN pip install --no-cache-dir -e /app/core -e /app/betti

EXPOSE 9313
CMD ["python", "-m", "betti.main"]
