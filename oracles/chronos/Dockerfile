# Build from the monorepo root: docker build -f oracles/chronos/Dockerfile .
FROM python:3.11-slim
WORKDIR /app

COPY core /app/core
COPY oracles/chronos /app/chronos

RUN pip install --no-cache-dir -e "/app/core[pqc]" -e /app/chronos

EXPOSE 9300
# Not root: a public oracle. uid 10001 owns only what it writes (/app/data).
RUN mkdir -p /app/data && chown -R 10001:10001 /app/data
ENV HOME=/tmp
USER 10001:10001

CMD ["python", "-m", "chronos.main"]
