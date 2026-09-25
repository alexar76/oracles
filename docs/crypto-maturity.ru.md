# Семейство оракулов — криптографическая зрелость (честно)

Этот документ фиксирует, **чем является** семейство из **семнадцати оракулов** — и **чем не
является** — с точки зрения криптографии и production-hardening. Прочитайте его, прежде чем
считать выходы оракулов единственным доверенным якорем для крупных денежных потоков.

**См. также:** [Chronos SECURITY.md](../oracles/chronos/SECURITY.md) ·
[oracle-core SIGNING.md](../core/docs/SIGNING.md) ·
[Factory known-issues KI-6](https://github.com/alexar76/aicom/blob/main/docs/known-issues.md#ki-6--oracle-family-cryptographic-maturity-not-production-hardened)

---

## Кратко

| Заявление | Честный статус (2026-07) |
|-----------|--------------------------|
| 17 оракулов с проверяемой математикой | **Да** — живые capability, тесты, AIMarket v2 |
| Ed25519-подписанные manifest и receipt | **Да** — канонические формы совпадают с Hub |
| Гибрид PQC (Ed25519 + ML-DSA-65) | **Частично** — в `oracle-core`, **выключено по умолчанию**; Hub проверяет только Ed25519; внешнего crypto-аудита нет |
| Chronos Wesolowski VDF | **Research-grade примитив** — стандартная конструкция, параметры в коде, **без независимого аудита**, без формальной верификации |
| Hardened production crypto service | **Пока нет** — см. ниже |

Семейство собрано примерно за **два месяца** интенсивной разработки. Этого достаточно для
**сильного research/prototype** (корректная математика, тесты, демо, интеграция с лотереей) —
но **недостаточно** для полноценного hardened cryptographic service с публичными setup-параметрами,
внешними аудитами и артефактами proof-of-correctness, которые ожидают перед mainnet-TV L.

---

## Chronos (Wesolowski VDF)

**Что уже есть в репозитории**

- Фиксированный **RSA-2048 challenge modulus** (не генерация на запрос) —
  [`chronos/vdf.py`](../oracles/chronos/chronos/vdf.py).
- Документированные параметры: генератор, clamp `T` ∈ `[1, 1_000_000]`, 128-bit Fiat–Shamir,
  уравнение верификации.
- Unit-тесты, в т.ч. adversarial; выравнивание с Foundry-векторами для on-chain.
- [SECURITY.md](../oracles/chronos/SECURITY.md) — прозрачность setup и threat model.

**Чего нет у hardened production VDF — и у нас пока тоже**

| Пробел | Зачем нужно |
|--------|-------------|
| **Публичный гид по выбору параметров** | Связь `T` ↔ wall-clock на эталонном железе, запас против ASIC/GPU, рекомендации по сценариям. Сейчас `T` задаёт вызывающая сторона в пределах cap. |
| **Отдельный security analysis** | Документ для ревьюеров (assumptions, adaptive-root, RSA-2048, grinding bounds), пригодный для scope letter аудита. |
| **Внешний криптоаудит** | Нет отчёта Trail of Bits / NCC / аналогов; нет публичного PDF. |
| **Formal verification** | Нет Coq/Lean/TLA+ (или сторонних) доказательств соответствия кода семантике Wesolowski. |
| **Операционная прозрачность** | Нет публичного attestation log отпечатка modulus, политик `T`, профилей железа в проде. |

**До закрытия пробелов:** Chronos — для **демо, testnet-лотереи, экспериментов с grinding-resistance**.
Не единственный якорь доверия для крупных real-money потоков без независимого ревью.

---

## Подписи и oracle-core

**Что есть**

- [`oracle_core/signing.py`](../core/oracle_core/signing.py): Ed25519; опциональный **additive**
  ML-DSA-65 (`dilithium-py`) при `ORACLE_PQC=1`.
- Hybrid verify требует **обе** подписи, если PQ-поля присутствуют.
- Тесты в `core/tests` и Platon (skip без `dilithium-py`).

**Что всё ещё слабо**

| Пробел | Детали |
|--------|--------|
| **Нормативная hybrid-спека** | AIMarket v2 описывает Ed25519; PQ-расширение — **implementation-defined** в oracle-core, не замороженный RFC с test vectors в `aimarket-protocol`. |
| **Parity с Hub** | Hub проверяет **только Ed25519**; PQ игнорируется, пока consumer не вызовет `verify_signature_object`. |
| **Дефолт** | PQC **выключен** в prod-конфигах; badge в README — про возможность, не про деплой. |
| **Proof-of-correctness** | Нет независимого ревью канонических строк, lifecycle ключей, композиции hybrid (связь PQ-ключа с Ed25519). |
| **Key management** | Файловые ключи — нет HSM/KMS runbook для операторов. |

**Спека реализации:** [core/docs/SIGNING.md](../core/docs/SIGNING.md).

---

## 17 оракулов — ширина vs глубина

На каждый оракул — **доменная математика + handler + тесты + сцена портала**. Общий протокол,
подписи, метрики, rate limit — реальны и переиспользуются.

Что **нельзя** честно сделать за короткий срок для всех семнадцати:

- Внешнее ревью threat model по каждому оракулу
- Side-channel analysis горячих путей
- Constant-time для не-крипто оракулов (многие численные — не constant-time by design)
- Единый IR и runbook ротации ключей

**Честный уровень:** **research / prototype** с production-*style* интеграцией (Hub, lottery,
on-chain vectors для Chronos/Sortes). **Не** bank-grade / L1-grade crypto service.

---

## Критерии «hardened»

Слой считаем **production-hardened**, только когда выполнены **все** пункты [KI-6](https://github.com/alexar76/aicom/blob/main/docs/known-issues.md#ki-6--oracle-family-cryptographic-maturity-not-production-hardened):

1. Опубликован внешний криптоаудит (`oracle-core` signing, Chronos VDF, Sortes ECVRF минимум).
2. Chronos: гид по параметрам + чеклист attestation для оператора.
3. Hybrid PQC: нормативное расширение в `aimarket-protocol` + negative test vectors; Hub проверяет оба слоя.
4. Runbook key management (rotation, compromise, HSM/multisig).

До этого — **testnet, демо, ограниченные пилоты**, в духе Factory [pre-mainnet checklist](https://github.com/alexar76/aicom/blob/main/docs/known-issues.md).

---

## Сообщить о проблеме

GitHub issue в [alexar76/oracles](https://github.com/alexar76/oracles) с `[crypto]` в заголовке.
Не публикуйте working exploits до фикса.

**English:** [crypto-maturity.en.md](crypto-maturity.en.md)
