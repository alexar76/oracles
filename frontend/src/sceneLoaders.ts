import type { ComponentType } from "react";

// One R3F scene module per oracle (Vite-static dynamic imports). Shared by the
// full-screen App router and the landing's live mini-previews so the two never
// drift. Ambient oracles (percola/fermat/ablation/landauer) are not here — they
// render as an HTML-canvas iframe, both full-screen and as a live preview.
export const LOADERS: Record<string, () => Promise<{ default: ComponentType }>> = {
  platon: () => import("./scenes/platon"),
  chronos: () => import("./scenes/chronos"),
  lattice: () => import("./scenes/lattice"),
  murmuration: () => import("./scenes/murmuration"),
  lumen: () => import("./scenes/lumen"),
  colony: () => import("./scenes/colony"),
  turing: () => import("./scenes/turing"),
  sortes: () => import("./scenes/sortes"),
  gauss: () => import("./scenes/gauss"),
  aestus: () => import("./scenes/aestus"),
  betti: () => import("./scenes/betti"),
  kantor: () => import("./scenes/kantor"),
  fourier: () => import("./scenes/fourier"),
};
