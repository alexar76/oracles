# AIMarket Oracle Family — one endpoint, all oracle_core oracles.
# Built via oracles/docker-compose.yml (context = the oracles/ dir):
#   docker build -f oracles/oracle-family/Dockerfile .   # from inside oracles/
FROM python:3.11-slim
WORKDIR /app

# oracle_core + every oracle_core oracle + the family aggregator
COPY core /app/core
COPY oracles/chronos /app/chronos
COPY oracles/lattice /app/lattice
COPY oracles/murmuration /app/murmuration
COPY oracles/lumen /app/lumen
COPY oracles/colony /app/colony
COPY oracles/turing /app/turing
COPY oracles/percola /app/percola
COPY oracles/fermat /app/fermat
COPY oracles/ablation /app/ablation
COPY oracles/landauer /app/landauer
COPY oracles/oracle-family /app/oracle-family

# numpy (lattice) + httpx (Platon federation proxy) — explicit runtime deps.
RUN pip install --no-cache-dir numpy httpx \
 && pip install --no-cache-dir \
      -e /app/core \
      -e /app/chronos -e /app/lattice -e /app/murmuration \
      -e /app/lumen -e /app/colony -e /app/turing \
      -e /app/percola -e /app/fermat -e /app/ablation -e /app/landauer \
      -e /app/oracle-family

EXPOSE 9400
CMD ["python", "-m", "oracle_family_app.main"]
