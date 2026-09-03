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
# These six are in ORACLE_MODULES but were never copied or installed, so load_specs()
# skipped each one with "No module named 'betti'" at every boot and the family served 22
# capabilities instead of 36. They need nothing beyond the numpy already installed below.
COPY oracles/sortes /app/sortes
COPY oracles/gauss /app/gauss
COPY oracles/aestus /app/aestus
COPY oracles/betti /app/betti
COPY oracles/kantor /app/kantor
COPY oracles/fourier /app/fourier
COPY oracles/oracle-family /app/oracle-family

# Refresh the installer itself before it installs anything. pip 24.0/25.0.1 and
# setuptools 79.0.1 shipped in the base image carry known advisories (6 and 1
# respectively as of 2026-07-28) — they never touch a request, but they are what a
# scan of the running container reports, and there is no reason to carry them.
RUN pip install --no-cache-dir --upgrade pip setuptools

# numpy (lattice) + httpx (Platon federation proxy) — explicit runtime deps.
RUN pip install --no-cache-dir numpy httpx \
 && pip install --no-cache-dir \
      -e /app/core \
      -e /app/chronos -e /app/lattice -e /app/murmuration \
      -e /app/lumen -e /app/colony -e /app/turing \
      -e /app/percola -e /app/fermat -e /app/ablation -e /app/landauer \
      -e /app/sortes -e /app/gauss -e /app/aestus \
      -e /app/betti -e /app/kantor -e /app/fourier \
      -e /app/oracle-family

EXPOSE 9400
CMD ["python", "-m", "oracle_family_app.main"]
