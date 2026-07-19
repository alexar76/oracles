# Platon UMBRAL — El órgano sensorial del ecosistema de agentes

> **Platon es un órgano sensorial del ecosistema:** los agentes provocan el caos, Monitor observa, Hub vende, provenance registra.

Platon no es un gráfico de demostración. Es un **oráculo dinámico de 32 dimensiones** — un sustrato matemático vivo que los agentes autónomos pueden dirigir, interrogar y del cual recibir testimonios firmados vía el protocolo AIMarket.

> **Lugar en el ecosistema y diagramas mermaid:** ver [ECOSYSTEM.md](../ECOSYSTEM.md). Platon es un **proyecto independiente** que se integra en la [economía de agentes alexar76](https://github.com/alexar76); **no** lo produce AI-Factory.

### ¿Dónde está la IA?

El **núcleo de la simulación es matemática, no IA** — y lo decimos con claridad. La IA vive en tres lugares honestos: (1) el **oráculo testigo es un LLM** (`platon.oracle@v1` llama a DeepSeek/Ollama); (2) **DREAM ajusta un modelo aprendido real** (mínimos cuadrados sobre datos de trayectoria, residuo medible, sin constantes mágicas) y muestra dónde un predictor aprendido diverge en el horizonte de Lyapunov; (3) los **consumidores son agentes de IA** — Platon es *infraestructura para la economía de IA* (entropía y señales firmadas para muestreo, nonces, desempates, commit-reveal, elección de líder). La dinámica, el parámetro de orden, el proxy de Lyapunov y la proyección de Stiefel son matemática real y demostrable, no IA disfrazada.

---

## 1. Qué es Platon (nivel más alto)

| Rol | Actor | Acción |
|-----|-------|--------|
| **Sonda** | Agente autónomo | Invoca `platon.steer@v1`, `platon.dream@v1`, `platon.oracle@v1` vía Hub |
| **Siente** | Simulación Platon | Evoluciona osciladores acoplados; detecta bifurcaciones (quimera, caos, sincronía) |
| **Habla** | Oráculo (DeepSeek / plantilla) | Emite **testimonios** matemáticos en eventos críticos |
| **Observa** | Alien Monitor | Materializa eventos en topología 3D; κ, r en vivo |
| **Vende** | AIMarket Hub | Descubrimiento federado, invoke con micropagos, recibos provenance |
| **Audita** | Capa provenance | Cada invoke devuelve `input_hash` + precio + timestamp |

**Sentido práctico:** los agentes obtienen una **interfaz verificable y con precio a la complejidad** — no una caja negra LLM, sino un sistema dinámico con parámetros de orden medibles y modos de fallo del pronóstico.

---

## 2. Fundamento científico

### 2.1 Espacio de estados

Platon simula **N = 32 osciladores acoplados Stuart–Landau**:

\[
z_j = r_j e^{i\theta_j}, \quad j = 1,\ldots,32
\]

El estado interno vive en \(\mathbb{R}^{64}\), pero la **dimensión semántica** es **32**.

### 2.2 Evolución (acoplamiento Kuramoto–Stuart–Landau)

\[
\frac{dr_j}{dt} = r_j(1 - r_j^2), \qquad
\frac{d\theta_j}{dt} = \omega_j + b_j(\text{prompt}) + \kappa \sin(\Theta - \theta_j)
\]

\[
\Theta = \arg\left(\frac{1}{N}\sum_{k=1}^{N} e^{i\theta_k}\right)
\]

### 2.3 Parámetro de orden

\[
r = \left|\frac{1}{N}\sum_{j=1}^{N} e^{i\theta_j}\right| \in [0,1]
\]

| Régimen | r | Significado |
|---------|---|-------------|
| Incoherente | r &lt; 0.35 | Sin ritmo colectivo |
| Quimera | 0.35 ≤ r &lt; 0.85 | Clústeres sincronizados y caóticos coexisten |
| Sincronía total | r &gt; 0.85 | Bloqueo de fase global |

### 2.4 Proxy de Lyapunov (caos)

\[
\lambda \approx \frac{1}{\Delta t}\ln\frac{\|\delta \mathbf{x}(t)\|}{\delta_0}
\]

Si \(\lambda > 2.5\) → evento `chaos_threshold`: zona donde **fallan los modelos sustitutos**.

### 2.5 Proyección (caverna de Platón)

Composición de rotaciones \(\mathbb{R}^{64} \to \mathbb{R}^{2}\):

\[
(x, y) = \Pi_{\theta_1,\theta_2}(\mathbf{z}_{\mathrm{real}}, \mathbf{z}_{\mathrm{imag}})
\]

Distintos ángulos → **testimonios incompatibles** del mismo estado (metáfora UMBRAL).

### 2.6 DREAM (predicción vs verdad)

- **Verdad:** integración no lineal completa
- **Sustituto:** predictor linealizado de un paso

El índice de divergencia marca el **colapso epistémico** del pronóstico.

---

## 3. ¿Por qué exactamente 32 dimensiones?

### Razones matemáticas

1. **Estados quimera** — redes Kuramoto con \(N \gtrsim 20\) muestran quimeras estables; \(N=32\) está en el régimen estudiado.
2. **Rejilla 8×4** — potencia de dos; visualización clara; métrica PCA₃ significativa.
3. **Equilibrio computacional** — 496 pares; 30 Hz en CPU sin GPU.
4. **Embedding real 64D** — variedad suave para proyección Stiefel.

### Razones prácticas en nuestro ecosistema

| Requisito | Por qué 32 |
|-----------|------------|
| Servidor público 8 núcleos, sin GPU | tick + WebGL + oráculo &lt; 200 MB RAM |
| Micropagos AIMarket | invoke rápido |
| Alien Monitor | telemetría κ/r 1:1 |
| Agentes | bifurcaciones no triviales sin ruido |
| Metáfora ML | bottleneck de 32 — común en redes |

**No es arbitrario:** 32 es la escala mínima donde coexisten **quimera, caos y sincronía total** bajo steering semántico.

---

## 4. Platon como oráculo

**Oráculo** aquí es preciso:

> En eventos dinámicos, Platon emite un **witness** — testimonio corto anclado en \((\kappa, r, \lambda)\), generado por **DeepSeek** (clave Hermes) o plantilla determinista.

Capability: `platon.oracle@v1` — $0.02, con provenance.

No es chat genérico. Es **lenguaje condicionado por eventos** y estado medible.

---

## 5. Casos de uso

### UC-1: Orquestación bajo incertidumbre
Agente busca `intent=chaos probe`, invoca `platon.steer@v1`, lee \(\kappa, r\), decide escalar o cambiar estrategia.

### UC-2: Horizonte de pronóstico
Agente cuant invoca `platon.dream@v1`; si `divergence_at < 15`, el ML downstream no confía en horizontes largos.

### UC-3: Arte generativo
Agente artístico mapea fases de `platon.state@v1` a MIDI/CC.

### UC-4: Registro científico
Agente de laboratorio archiva witnesses en nacimientos de quimera con hash reproducible.

### UC-5: Operaciones con Monitor
Operador ve `chaos_threshold` en el nodo Platon y correlaciona con fallos de agentes.

### UC-6: Comercio federado
Hub externo indexa `platon.*@v1` y enruta invokes pagados.

---

## 6. Visualización de invocaciones de agentes

| Visual | Significado |
|--------|-------------|
| **Haces cian** | invoke de agente |
| **Haces violeta** | predicción (dream, oracle) |
| **Trayectoria rosa** | sustituto DREAM |
| **Trayectoria cian** | verdad DREAM |
| **Panel Agent channel** | feed en vivo de capability_id |

Los invokes vía Hub aparecen en tiempo real (WebSocket).

---

## 7. Cableado del ecosistema

Clave DeepSeek: `~/.hermes/.env` → `DEEPSEEK_API_KEY`.

---

## 8. Tarjeta de ecuaciones

\[
\boxed{
\begin{aligned}
&\dot\theta_j = \omega_j + b_j + \kappa\sin(\Theta - \theta_j) \\
&r = \left|\langle e^{i\theta}\rangle\right| \\
&\lambda \approx \frac{1}{\Delta t}\ln\frac{\|\delta\mathbf{x}\|}{\delta_0} \\
&\text{Witness} = f_{\mathrm{DeepSeek}}(\kappa, r, \lambda, \text{event})
\end{aligned}
}
\]

**Platon UMBRAL** — una realidad de alta dimensión, muchas proyecciones 2D incompatibles, un oráculo federado.
