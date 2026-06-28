# Oracles — верifiable math для агентной экономики (RU)

Семнадцать живых математических оракулов на общем **`oracle-core`**. Каждый выдаёт **подписанный, проверяемый артефакт**, который агенты находят и оплачивают через [AIMarket Protocol v2](https://github.com/alexar76/aimarket-protocol) на [modelmarket.dev](https://modelmarket.dev).

> **Лендинг:** [oracles.modelmarket.dev](https://oracles.modelmarket.dev) · **Экосистема:** [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev) · **Репозиторий:** [alexar76/oracles](https://github.com/alexar76/oracles)

---

## Как это работает в экономике

1. **Discover** — агент ищет на hub по intent (`verifiable randomness`, `consensus`, …).
2. **Invoke** — канал микроплатежей, оплата за вызов capability.
3. **Verify** — доказательство с подписью Ed25519 (+ гибрид ML-DSA); доверять оператору не нужно.
4. **Settle** — подписанный receipt списывает с канала; в manifest — реальные метрики latency/success.

---

## Семнадцать оракулов

| Оракул | Навык | Примеры capabilities |
|--------|-------|----------------------|
| **Platon** | Верifiable randomness + dynamical oracle | `platon.random@v1`, `platon.beacon@v1`, commit-reveal |
| **Chronos** | Verifiable delay (VDF) | `chronos.eval@v1`, `chronos.verify@v1` |
| **Lattice** | Квазислучайные low-discrepancy последовательности | `lattice.sequence@v1` |
| **Murmuration** | Robust consensus aggregation | `murmuration.aggregate@v1` |
| **Lumen** | Репутация / trust scores | `lumen.reputation@v1` |
| **Colony** | TSP-оптимизация + сертификат качества | `colony.optimize@v1` |
| **Turing** | Blue-noise sampling | `turing.bluenoise@v1` |
| **Percola** | Устойчивость сети / порог перколяции | `percola.threshold@v1`, `percola.verify@v1` |
| **Fermat** | Маршрутизация least-time + dual-сертификат | `fermat.route@v1`, `fermat.verify@v1` |
| **Ablation** | Системный каскадный риск (SOC-хвост) | `ablation.cascade@v1`, `ablation.verify@v1` |
| **Landauer** | Термодинамический аудит вычислений | `landauer.audit@v1`, `landauer.verify@v1` |
| **Sortes** | Неподкупная проверяемая случайность (истинный ECVRF, RFC 9381) | `sortes.draw@v1`, `sortes.verify@v1` |
| **Gauss** | Гауссова регрессия: калиброванный прогноз + честная неопределённость + лучшая точка для сэмплинга | `gauss.field@v1`, `gauss.suggest@v1`, `gauss.verify@v1` |
| **Aestus** | Time-lock головоломки RSW: запечатать данные до ~T последовательных возведений в квадрат | `aestus.seal@v1`, `aestus.open@v1`, `aestus.verify@v1` |
| **Betti** | Персистентная гомология (Vietoris-Rips): форма облака точек + alarm по дрейфу | `betti.homology@v1`, `betti.distance@v1` |
| **Kantor** | Точный оптимальный транспорт (Wasserstein) + дуальный сертификат | `kantor.transport@v1`, `kantor.verify@v1` |
| **Fourier** | Спектральный анализ графа: лапласиан, связность λ₂, спектральный разрез | `fourier.spectrum@v1`, `fourier.verify@v1` |

**Chronos × Platon** — обёртка выхода Platon в VDF даёт *неподкупный* beacon: оператор не может «перебрать» результат.

---

## В продакшене: Agent Lottery

**[Agent Lottery](https://github.com/alexar76/lottery)** ([живой показ](https://lottery.modelmarket.dev/)) — канонический реальный потребитель: автономный экономический актор, который складывает **три оракула** в один неподкупный, проверяемый on-chain розыгрыш, оплачивая каждый вызов через Hub (`POST /ai-market/v2/invoke`, 1% routing fee) или напрямую у oracle-family:

| Оракул · capability | Для чего | Цена |
|---------------------|----------|------|
| **Platon** `platon.random@v1` | энтропия розыгрыша, фиксируется при закрытии раунда | $0.004 |
| **Chronos** `chronos.eval@v1` | Wesolowski VDF, проверяется on-chain (`onchainVdf`) | $0.01 |
| **Chronos** `chronos.verify@v1` | off-chain проверка VDF-доказательства | $0.001 |
| **Lumen** `lumen.reputation@v1` | EigenTrust-оценки → подписанные ваучеры репутации (+0…50% к шансам) | $0.005 |
| **Platon** `platon.ask@v1` | AI-казначей: LLM-распределение приза / machine-UBI (опционально) | $0.003 |

`platon.random@v1` сидирует `chronos.eval@v1`, поэтому выигрышный билет зафиксирован навязанным последовательным временем (тот самый **Chronos × Platon** beacon выше) — ни оператор, ни агент не могут его «перебрать»; затем **Lumen** взвешивает розыгрыш по репутации. Каждый вызов — Ed25519-подписанный receipt, проводимый как opex лотереи, а Hub возвращает свои routing-комиссии как **machine UBI** для агентов.

---

## Пещера Platon UMBRAL (отдельный продукт)

Все семнадцать оракулов — **полноценные AIMarket-продукты**. Лендинг семейства — **портал** (экономика + 3D-витрина). **Platon UMBRAL** на `/platon/umbral` — **отдельная «пещера»**, которая в образовательном смысле показывает оракула #1 с живым бэкендом и панелью.

→ **[Семнадцать оракулов и пещера Platon (RU)](platon-preview.ru.md)** · [EN](platon-preview.en.md)

---

## 3D cosmic visuals

Локальный R3F-портал:

```bash
cd frontend && npm install && npm run dev
# http://localhost:5180/  — карточки с video loops
# http://localhost:5180/?o=platon  — образовательное превью Platon (только браузер; не UMBRAL)
# UMBRAL cockpit (отдельное приложение): http://localhost:5174/umbral  или  /platon/umbral в prod
```

Записанные loops: `frontend/public/media/*.webm` (также в [README на GitHub](https://github.com/alexar76/oracles#gallery)).

---

## Разработка и тесты

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e "core[dev,pqc]"
for o in chronos lattice murmuration lumen colony turing percola fermat ablation landauer sortes gauss aestus betti kantor fourier; do .venv/bin/pip install -e "oracles/$o"; done
.venv/bin/pip install -e "oracles/platon/backend[dev]"
PLATON_TESTING=1 .venv/bin/python -m pytest core/tests oracles/*/tests oracles/platon/backend/tests -q
```

**280+ тестов** зелёных по всей семье.

---

## Связанная документация

- [AIMarket Hub](https://github.com/alexar76/aimarket-hub) — каталог и маршрутизация
- [aimarket-agent](https://github.com/alexar76/aimarket-agent) — discover → invoke из Python
- [Карта экосистемы Protocol](https://github.com/alexar76/aimarket-protocol/blob/main/ecosystem.md)

**Другие языки:** [en.md](en.md) · [es.md](es.md)
