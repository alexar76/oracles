# Oracles README gallery

Assets for the monorepo [README](../README.md) and GitHub mirror.

| Asset | Description |
|-------|-------------|
| `docs/recordings/oracle-portal.webm` | Hero — cosmic landing + scene hops |
| `docs/screenshots/01-landing-hero.png` | Live portal hero |
| `docs/screenshots/02-economy-flow.png` | How the economy works |
| `docs/screenshots/03-oracle-cards.png` | Seventeen oracle cards with live 3D |
| `docs/screenshots/04-*-scene.png` … | Full-screen 3D per oracle |
| `docs/recordings/loops/*.gif` | Card preview loops for README (GitHub renders GIF, not `<video>`) |
| `frontend/public/media/*.webm` | Card preview loops on live landing |

**Live site:** [oracles.modelmarket.dev](https://oracles.modelmarket.dev)

## Regenerate

```bash
cd frontend
npm install
npm run build && npm run preview -- --port 5180 &
npx playwright install chromium
# All 17 card loops → docs/recordings/loops/*.gif (screenshot-based; needs fresh build)
node scripts/capture-card-loops.mjs
# Portal hero + static screenshots
node scripts/capture-landing.mjs
```

> **Note:** Restart `preview` after every `build` — a stale server serves the old 11-oracle bundle and loops will be blank.

Legacy split (physics ambient only — now included in `capture-card-loops.mjs`):

```bash
node scripts/capture-physics.mjs
for s in percola fermat ablation landauer; do
  ffmpeg -y -t 6 -i "public/media/$s.webm" \
    -vf "fps=10,scale=400:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse" \
    -loop 0 "../docs/recordings/loops/$s.gif"
done
```

Platon UMBRAL storefront (separate UI): `cd oracles/platon/frontend && node scripts/gallery.mjs`
