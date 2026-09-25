# Percola — Oráculo de resiliencia de red (umbral de percolación)

> **Percola vende el punto de inflexión.** No le dice al agente *en quién* confiar, sino *cuándo la red en su conjunto se desmorona* — la fracción exacta de fallos bien elegidos que colapsa la conectividad. La misma física que decide si un incendio salta el cortafuegos o un brote se vuelve pandemia.

Percola es un oráculo en vivo sobre **`oracle-core`**, descubrible en **AIMarket Protocol v2**. Donde [Lumen](../../lumen) clasifica *quién* es reputable, Percola mide *cuánto daño absorbe la red entera antes de fragmentarse* — una propiedad topológica global que ninguna puntuación por nodo expresa.

---

## 1. El problema que resuelve Percola

Un agente que enruta una tarea de pago multi-paso a través de una cadena de sub-agentes y servicios MCP apuesta implícitamente a que la red de dependencias siga conectada. Pero la conectividad no se pierde de forma gradual — tiene un **punto de inflexión**:

> *«¿Cuántos de los nodos de mayor apalancamiento pueden fallar antes de fragmentar la red — y cuáles son?»*

La reputación por nodo (centralidad, EigenTrust) responde *quién importa en promedio*. No responde *cuándo muere el sistema entero*, porque el colapso es una **transición de fase colectiva**, no la suma de importancias individuales. Percola calcula ese umbral directamente.

---

## 2. La física

### 2.1 Percolación y la transición de conectividad

Tratamos el grafo como un sistema de percolación. Sea `f` la fracción de nodos eliminados. El **parámetro de orden** es el tamaño de la componente conexa gigante como fracción de la red:

```
P_inf(f) = |componente mayor tras eliminar f·n nodos| / n.
```

Por debajo de una **fracción crítica `f_c`** la red conserva una componente gigante (`P_inf` alto); en `f_c` colapsa a una lluvia de clústeres pequeños (`P_inf` cae por un precipicio). Es una genuina **transición de fase de segundo orden** en conectividad — la misma clase de universalidad que la percolación bond/site en una red.

### 2.2 El testigo: la susceptibilidad

El observable de libro que *atestigua* la transición es el **segundo clúster mayor** `S2(f)`. Lejos de `f_c` hay una componente dominante y `S2` es diminuto. Justo en `f_c` la componente gigante se rompe en piezas comparables, así que `S2` **alcanza un pico**. Percola lee `f_c` en el pico de susceptibilidad:

```
f_c = argmax_f  S2(f).
```

### 2.3 Ataque dirigido vs aleatorio

Dos órdenes de eliminación acotan el destino de la red:

- **Dirigido** — orden voraz determinista que elimina el nodo de mayor grado actual en cada paso (empates → menor índice). Es el adversario que conoce la topología; da el `f_c` *más pequeño* (peor caso).
- **Aleatorio** — permutación con semilla (`semilla = H(graph_commitment ‖ nonce)`, comprometida *antes* de evaluar). Es el desgaste genérico; da un `f_c` de referencia *mayor*.

La brecha entre ambas curvas mide cuánto depende la resiliencia de proteger unos pocos nodos clave.

### 2.4 Cómo se calcula — union–find

Para cada `f` muestreado, Percola reconstruye la conectividad del subgrafo superviviente con una estructura **disjoint-set (union–find)** y registra `P_inf` y `S2`. También devuelve un escalar **robustness** — el área bajo la curva dirigida `P_inf(f)` (0 = colapso inmediato, 1 = indestructible) — y el **conjunto keystone**: los nodos cuya eliminación (hasta `f_c`) impulsa el colapso.

---

## 3. Capacidades

| ID | Descripción | Entrada | Salida | Precio | p50 |
|----|-------------|---------|--------|--------|-----|
| `percola.threshold@v1` | Análisis de resiliencia: fracción crítica `f_c`, curvas de colapso, escalar robustness, conjunto keystone, para ataque dirigido + aleatorio. | `edges`, `nodes?`, `samples?`, `attack?`, `nonce?` | `n, m, graph_commitment, robustness, targeted{...}, random{...}` | $0.01 | ~60 ms |
| `percola.verify@v1` | Re-ejecución sin confianza: recomputar orden + barrido, verificar el `f_c` declarado. | `edges`, `f_c`, `attack?`, `seed?/nonce?` | `valid, recomputed_f_c, graph_commitment, order_hash` | $0.001 | ~20 ms |

Ambas corren sobre `oracle-core`: cada invoke se envuelve en un sobre firmado AIMarket v2 con un recibo de 7 campos y un `input_hash` `sha256`.

---

## 4. Casos de uso (economía de agentes)

### UC-1 — Compuerta de radio de impacto pre-vuelo (ARGUS-3)
Antes de que ARGUS-3 comprometa fondos en una ruta multi-salto, llama a `percola.threshold@v1` sobre el subgrafo de dependencias. Un `f_c` bajo (un par de nodos keystone fragmentan todo) → rechaza la ruta o exige escrow en los keystones. Convierte «confiar en que la red está bien» en «conocer el umbral exacto de fallo de cada ruta que pagas» — una compuerta cuantitativa que WARDEN puede imponer.

### UC-2 — Refuerzo de keystones (optimización)
El conjunto `keystones` es accionable: es el **conjunto de mínimo esfuerzo a endurecer**. Añadir redundancia/escrow solo a esos nodos eleva `f_c` lo máximo por unidad de coste — una optimización del gasto en resiliencia. Re-ejecutar tras el refuerzo confirma el desplazamiento de `f_c`.

### UC-3 — Monitoreo de riesgo sistémico
Seguir `f_c` y el escalar robustness del grafo de confianza en el tiempo. Un `f_c` decreciente es una alerta temprana de que la economía se concentra en pocos nodos portantes.

### UC-4 — Chequeo de diversificación de contrapartes
Una capa de liquidación consulta a Percola sobre su grafo de contrapartes: si el `f_c` aleatorio es sano pero el dirigido es diminuto, la red es robusta a la mala suerte pero frágil ante un adversario inteligente.

---

## 5. Invocar (curl)

```bash
curl -s http://localhost:9306/ai-market/v2/manifest | jq '.tools[].capability_id'

curl -s -X POST http://localhost:9306/ai-market/v2/invoke \
  -H "Content-Type: application/json" \
  -d '{"capability_id":"percola.threshold@v1","input":{"edges":[[0,1],[0,2],[1,2],[3,4],[3,5],[4,5],[2,6],[6,3]],"samples":7}}'
```

---

## 6. Verificabilidad y seguridad

- **Determinista por construcción.** El análisis es una función pura del grafo canónico. El orden dirigido usa un desempate fijo (menor índice), así que un verificador recomputa la misma secuencia desde el grafo solo.
- **Sin aleatoriedad controlada por el oráculo.** La única aleatoriedad es la referencia de ataque aleatorio, cuya semilla se compromete como `H(graph_commitment ‖ nonce)` **antes** de evaluar.
- **Umbral re-ejecutable.** `percola.verify@v1` re-ejecuta el union–find sobre el orden comprometido y reproduce `P_inf(f)` y `f_c`. El umbral se *prueba por recómputo*, no se afirma.
- **Cómputo acotado.** Las entradas están limitadas (`MAX_NODES`, `MAX_EDGES`) y el handler costoso corre en un hilo worker (oracle-core).

**Percola — la fracción exacta de fallos que tu red sobrevive, probada por re-ejecución.**
