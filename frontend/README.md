# Oracle family — cinematic 3D visuals

> **Live landing:** [oracles.modelmarket.dev](https://oracles.modelmarket.dev) · **Monorepo:** [oracles](../README.md)  
> **Platon preview vs UMBRAL:** [docs/platon-preview.en.md](../docs/platon-preview.en.md) · [ru](../docs/platon-preview.ru.md)

Cosmic **portal** for all seven AIMarket oracles — hero, economy loop, capability cards, and
3D scenes (`?o=<name>`). Agents buy signed capabilities via the Hub; this app is the human
showcase, not the invoke endpoint.

```bash
npm install
npm run dev        # http://localhost:5180/
npm run build
```

`?o=` ∈ `platon · chronos · lattice · murmuration · lumen · colony · turing`.

## Portal vs Platon UMBRAL cave

All seventeen oracles are **full products** in the AI economy (see [family README](../README.md)).
This frontend is the **shared visual layer** for the portal.

**Platon UMBRAL** (`/platon/umbral`) is a **separate product** — an educational cave that
deep-dives into oracle #1 with live backend, telemetry, and controls. The `?o=platon` scene
here is the family showcase card, not the cave.

→ **[Seventeen oracles & Platon cave (EN)](../docs/platon-preview.en.md)** · [RU](../docs/platon-preview.ru.md)

## How it works

- **`src/CosmicCanvas.tsx`** — the shared environment extracted from Platon: a procedural
  fbm **nebula** shader backdrop, two parallax **starfields**, Sparkles, three point lights,
  fog, an auto-rotating camera, and a **Bloom + Vignette** post-processing pass. Every oracle
  scene renders as `children` inside it, so the whole family shares one cosmic look.
- **`src/scenes/<oracle>.tsx`** — each oracle's signature 3D motif (R3F), reflecting its real
  math: Chronos = a sequential **helix-thread** laid bead-by-bead by a comet head
  (`y = g^(2^T)`); Lattice = a point cloud **snapping from chaos into a Halton lattice**;
  Murmuration = a **boid flock** collapsing to a consensus core; Lumen = a **trust graph**
  with light flowing to the top-ranked node; Colony = a **TSP tour** untangling via 2-opt;
  Turing = an even **blue-noise membrane**.
- **`src/App.tsx`** — reads `?o=`, lazy-loads the scene, wraps it in `CosmicCanvas` + an
  ErrorBoundary (a broken scene can't blank the others) + a title overlay and oracle picker.

## Recorded videos

Pre-rendered loops live in [`public/media/`](public/media) (`platon.webm`, `chronos.webm`,
`lattice.webm`, `murmuration.webm`, `lumen.webm`, `colony.webm`, `turing.webm`) — they double as
the **landing-page card previews** (the home at `/` is a full portal: hero, economy explainer,
and a card per oracle). Regenerate with `vite preview` + the Playwright capture script.

> Platon UMBRAL cave lives in `oracles/platon/frontend` (`/platon/umbral` in prod) —
> a separate product for oracle #1. See [docs/platon-preview.en.md](../docs/platon-preview.en.md).
