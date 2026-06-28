# Oracles — matemática verificable para la economía de agentes (ES)

Diecisiete oráculos matemáticos en vivo sobre **`oracle-core`** compartido. Cada uno emite un **artefacto firmado y verificable** que los agentes descubren y pagan vía [AIMarket Protocol v2](https://github.com/alexar76/aimarket-protocol) en [modelmarket.dev](https://modelmarket.dev).

> **Landing:** [oracles.modelmarket.dev](https://oracles.modelmarket.dev) · **Ecosistema:** [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev) · **Repo:** [alexar76/oracles](https://github.com/alexar76/oracles)

---

## Cómo encaja en la economía

1. **Discover** — el agente busca en el hub por intent (`verifiable randomness`, `consensus`, …).
2. **Invoke** — canal de micropagos, pago por capability.
3. **Verify** — prueba firmada Ed25519 (+ ML-DSA híbrido); no hace falta confiar en el operador.
4. **Settle** — receipt firmado debita el canal; métricas reales de latencia/éxito en el manifest.

---

## Los diecisiete oráculos

| Oráculo | Habilidad | Capabilities de ejemplo |
|---------|-----------|-------------------------|
| **Platon** | Aleatoriedad verificable + oráculo dinámico | `platon.random@v1`, `platon.beacon@v1`, commit-reveal |
| **Chronos** | Retardo verificable (VDF) | `chronos.eval@v1`, `chronos.verify@v1` |
| **Lattice** | Secuencias quasi-aleatorias low-discrepancy | `lattice.sequence@v1` |
| **Murmuration** | Agregación robusta por consenso | `murmuration.aggregate@v1` |
| **Lumen** | Reputación / trust scores | `lumen.reputation@v1` |
| **Colony** | Optimización TSP + certificado de calidad | `colony.optimize@v1` |
| **Turing** | Muestreo blue-noise estructurado | `turing.bluenoise@v1` |
| **Percola** | Resiliencia de red / umbral de percolación | `percola.threshold@v1`, `percola.verify@v1` |
| **Fermat** | Enrutamiento least-time + certificado dual | `fermat.route@v1`, `fermat.verify@v1` |
| **Ablation** | Riesgo de cascada sistémica (cola SOC) | `ablation.cascade@v1`, `ablation.verify@v1` |
| **Landauer** | Auditoría termodinámica del cómputo | `landauer.audit@v1`, `landauer.verify@v1` |
| **Sortes** | Aleatoriedad verificable ECVRF, una sola salida válida verificable offline | `sortes.draw@v1`, `sortes.verify@v1` |
| **Gauss** | Regresión por procesos gaussianos: media + incertidumbre honesta + mejor punto a muestrear | `gauss.field@v1`, `gauss.suggest@v1`, `gauss.verify@v1` |
| **Aestus** | Puzzles time-lock RSW: sella datos hasta que pase el tiempo, sin poseedor de trapdoor | `aestus.seal@v1`, `aestus.open@v1`, `aestus.verify@v1` |
| **Betti** | Homología persistente: números de Betti b0/b1/b2 + alarma de deriva (forma de los datos) | `betti.homology@v1`, `betti.distance@v1` |
| **Kantor** | Transporte óptimo exacto (Wasserstein) con plan + certificado dual verificable | `kantor.transport@v1`, `kantor.verify@v1` |
| **Fourier** | Análisis espectral de grafos: espectro laplaciano, λ2 de Fiedler, corte y conductancia | `fourier.spectrum@v1`, `fourier.verify@v1` |

**Chronos × Platon** — envolver la salida de Platon en un VDF produce un beacon *imparcial*: el operador no puede manipular el resultado.

---

## En producción: Agent Lottery

**[Agent Lottery](https://github.com/alexar76/lottery)** ([demo en vivo](https://lottery.modelmarket.dev/)) es el consumidor real canónico: un actor económico autónomo que compone **tres oráculos** en un sorteo imparcial y verificable on-chain, pagando por llamada a través del Hub (`POST /ai-market/v2/invoke`, 1% de routing fee) o directamente a la oracle-family:

| Oráculo · capability | Para qué | Precio |
|----------------------|----------|--------|
| **Platon** `platon.random@v1` | entropía del sorteo, fijada al cerrar la ronda | $0.004 |
| **Chronos** `chronos.eval@v1` | VDF de Wesolowski, verificado on-chain (`onchainVdf`) | $0.01 |
| **Chronos** `chronos.verify@v1` | verificación off-chain de la prueba VDF | $0.001 |
| **Lumen** `lumen.reputation@v1` | scores EigenTrust → vales de reputación firmados (+0…50% de probabilidades) | $0.005 |
| **Platon** `platon.ask@v1` | Tesorero IA: asignación LLM del premio / UBI de máquinas (opcional) | $0.003 |

`platon.random@v1` siembra `chronos.eval@v1`, así que el boleto ganador queda fijado por tiempo secuencial forzado (el beacon **Chronos × Platon** de arriba) — ni el operador ni ningún agente pueden manipularlo; luego **Lumen** pondera el sorteo por reputación. Cada llamada es un receipt firmado con Ed25519 contabilizado como opex de la lotería, y el Hub devuelve sus routing fees como **UBI de máquinas** para los agentes.

---

## Platon: caverna UMBRAL (producto aparte)

Los diecisiete oráculos son **productos AIMarket completos**. El landing es el **portal**. UMBRAL en `/platon/umbral` es la **caverna** educativa del oráculo #1.

→ [EN](platon-preview.en.md) · [RU](platon-preview.ru.md)

---

## Visuales 3D cósmicos

Portal R3F local:

```bash
cd frontend && npm install && npm run dev
# http://localhost:5180/  — tarjetas con bucles de vídeo
# http://localhost:5180/?o=platon  — escena a pantalla completa
```

Bucles grabados: `frontend/public/media/*.webm` (también en el [README de GitHub](https://github.com/alexar76/oracles#gallery)).

---

## Desarrollo y tests

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e "core[dev,pqc]"
for o in chronos lattice murmuration lumen colony turing percola fermat ablation landauer sortes gauss aestus betti kantor fourier; do .venv/bin/pip install -e "oracles/$o"; done
.venv/bin/pip install -e "oracles/platon/backend[dev]"
PLATON_TESTING=1 .venv/bin/python -m pytest core/tests oracles/*/tests oracles/platon/backend/tests -q
```

**280+ tests** en verde en toda la familia.

---

## Documentación relacionada

- [AIMarket Hub](https://github.com/alexar76/aimarket-hub) — catálogo y enrutado
- [aimarket-agent](https://github.com/alexar76/aimarket-agent) — discover → invoke en Python
- [Mapa del ecosistema Protocol](https://github.com/alexar76/aimarket-protocol/blob/main/ecosystem.md)

**Otros idiomas:** [en.md](en.md) · [ru.md](ru.md)
