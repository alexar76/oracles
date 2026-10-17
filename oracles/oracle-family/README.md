# aimarket-oracle-family

One AIMarket v2 endpoint that serves every `oracle_core` oracle of the
[oracles](https://github.com/alexar76/oracles) family — Chronos, Lattice, Murmuration, Lumen,
Colony, Turing, Percola, Fermat, Ablation, Landauer, Sortes, Gauss, Aestus, Betti, Kantor and
Fourier — behind a single manifest. Each capability keeps its own `product_id`, so receipts stay
attributed to the oracle that produced them; the family signs them with one Ed25519 key. Platon
runs as its own app and is reached through a proxy.

Live: [oracles.modelmarket.dev/family](https://oracles.modelmarket.dev/family).

## What this package is — and is not

This package is the **aggregator only**. It imports `<oracle>.capabilities.SPEC` from each oracle
package it finds installed and skips, loudly, any that is missing. Today only
[`aimarket-oracle-sortes`](https://pypi.org/project/aimarket-oracle-sortes/) is on PyPI, so
`pip install aimarket-oracle-family` on its own gives an endpoint with almost nothing behind it.

The supported way to run the whole family is the container from the oracles repository, which
installs every oracle from source:

```bash
git clone https://github.com/alexar76/oracles.git && cd oracles
docker compose up -d oracle-family      # see docker-compose.yml
```

Or, from a checkout, install core, the oracles you want and this package, then run it:

```bash
pip install -e "core[pqc]" -e oracles/chronos -e oracles/sortes -e oracles/oracle-family
python -m oracle_family_app.main        # listens on :9400
```

## Configuration

| Variable | Meaning | Default |
|---|---|---|
| `ORACLE_FAMILY_PORT`, `ORACLE_FAMILY_HOST` | Where it listens | `9400`, `0.0.0.0` |
| `ORACLE_FAMILY_PUBLIC_URL` | The base URL the manifest advertises | `https://oracles.modelmarket.dev/family` |
| `ORACLE_FAMILY_SIGNING_KEY` | Path of the family's Ed25519 signing key (created on first start) | `data/oracle_family_signing_key` |
| `ORACLE_FAMILY_PLATON_URL` | Where the Platon app answers, for the proxied capabilities | `http://127.0.0.1:9200` |
| `ORACLE_FAMILY_CORS_ORIGINS` | Allowed browser origins | `*` |

Everything `oracle-core` reads applies too: the price gate (`ORACLE_TRUSTED_HUBS`,
`ORACLE_PRICE_GATE`), the paid tier and the call log (`ORACLE_CALLS`, `ORACLE_OPS_TOKEN`). See
[`core/README.md`](https://github.com/alexar76/oracles/blob/main/core/README.md).

Keep the signing key out of version control and out of any archive: whoever holds it can sign
receipts as the family.

## License

Apache-2.0.
