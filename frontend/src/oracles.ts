/** Public source links. Every oracle except Platon lives in the `oracles` family repo. */
export const GITHUB_ORG = "https://github.com/alexar76";
export const ORACLES_REPO = `${GITHUB_ORG}/oracles`;

export interface Cap {
  id: string;
  price: string;
  what: string;
}

export interface Oracle {
  slug: string;
  name: string;
  accent: string;
  skill: string; // one-line headline skill
  blurb: string; // what it is, why agents need it
  math: string; // the real mathematics
  caps: Cap[];
  camera: [number, number, number];
  tests: number;
  /** Full interactive cockpit (Platon UMBRAL only) */
  cockpitUrl?: string;
  /** Project README / docs */
  docsUrl?: string;
  /** Source repo. Defaults to the oracles family monorepo subfolder (see oracleGithubUrl). */
  githubUrl?: string;
  /** Fullscreen ambient canvas (static HTML visual) instead of an R3F scene */
  ambient?: boolean;
}

export const ORACLES: Oracle[] = [
  {
    slug: "platon",
    name: "Platon",
    accent: "#6ee7ff",
    skill: "Verifiable randomness + dynamical oracle",
    blurb:
      "A 32-dimensional chaotic substrate that emits signed, auditable entropy and signals — the randomness agents need for sampling, nonces, tie-breaks, lotteries and leader election.",
    math: "Coupled Stuart-Landau / Kuramoto oscillators · chaos-VRF · hash-chained beacon · commit-reveal",
    caps: [
      { id: "platon.random@v1", price: "$0.004", what: "signed random bytes + proof" },
      { id: "platon.beacon@v1", price: "$0.004", what: "hash-chained beacon round" },
      { id: "platon.commit@v1", price: "$0.004", what: "commit-reveal (bias-resistant)" },
      { id: "platon.oracle@v1", price: "$0.02", what: "LLM mathematical witness" },
      { id: "platon.ask@v1", price: "$0.003", what: "grounded read-only guide" },
    ],
    camera: [0, 1.5, 11],
    tests: 65,
    cockpitUrl: "/platon/umbral",
    githubUrl: `${GITHUB_ORG}/platon`,
    docsUrl: `${ORACLES_REPO}/blob/main/docs/platon-preview.ru.md`,
  },
  {
    slug: "chronos",
    name: "Chronos",
    accent: "#c084fc",
    skill: "Verifiable delay — proof of elapsed sequential time",
    blurb:
      "Proves that real, non-parallelizable time has passed. Fair ordering, anti-MEV, timeouts — and an unbiasable randomness beacon when wrapped over Platon.",
    math: "Wesolowski VDF over the unfactored RSA-2048 modulus · publicly verifiable, no trust in the oracle",
    caps: [
      { id: "chronos.eval@v1", price: "$0.01", what: "y = g^(2^T) + proof" },
      { id: "chronos.verify@v1", price: "$0.001", what: "cheap trustless verify" },
    ],
    camera: [0, 3, 16],
    tests: 8,
  },
  {
    slug: "lattice",
    name: "Lattice",
    accent: "#7dd3fc",
    skill: "Low-discrepancy (quasi-random) sequences",
    blurb:
      "When agents need EVEN coverage, not random clumps: quasi-Monte-Carlo integration, sampling, coverage testing, optimization seeding.",
    math: "Halton sequence · van der Corput radical inverse · discrepancy O((log N)^d / N)",
    caps: [{ id: "lattice.sequence@v1", price: "$0.002", what: "signed low-discrepancy points" }],
    camera: [0, 2, 13],
    tests: 13,
  },
  {
    slug: "murmuration",
    name: "Murmuration",
    accent: "#f472b6",
    skill: "Robust consensus aggregation",
    blurb:
      "Turns a noisy crowd of agent estimates into one breakdown-resistant number — outliers can't move it. Price feeds, sortition, federated decisions.",
    math: "Median · trimmed mean · Tukey biweight (IRLS) · DeGroot consensus dynamics",
    caps: [{ id: "murmuration.aggregate@v1", price: "$0.003", what: "robust aggregate + proof" }],
    camera: [0, 4, 16],
    tests: 15,
  },
  {
    slug: "lumen",
    name: "Lumen",
    accent: "#fbbf24",
    skill: "Reputation & trust scores",
    blurb:
      "Who should an agent trust to invoke? Sybil-resistant reputation over an interaction graph — the basic need of any agent economy.",
    math: "EigenTrust / PageRank power iteration · dominant eigenvector centrality",
    caps: [{ id: "lumen.reputation@v1", price: "$0.002", what: "signed reputation scores" }],
    camera: [0, 2, 14],
    tests: 18,
  },
  {
    slug: "colony",
    name: "Colony",
    accent: "#34d399",
    skill: "Optimization with a quality certificate",
    blurb:
      "Agents offload NP-hard sub-problems (routing, assignment, scheduling) and get a near-optimal answer WITH a proof of how good it is.",
    math: "Nearest-neighbour + 2-opt TSP · admissible lower bound · optimality gap",
    caps: [{ id: "colony.optimize@v1", price: "$0.005", what: "tour + length + bound + gap" }],
    camera: [0, 8, 14],
    tests: 12,
  },
  {
    slug: "turing",
    name: "Turing",
    accent: "#a78bfa",
    skill: "Blue-noise structured sampling",
    blurb:
      "Even, organic, never-clumped point sets — superior to white noise for sampling, dithering, stippling and procedural masks.",
    math: "Mitchell best-candidate blue-noise · maximal minimum pairwise distance",
    caps: [{ id: "turing.bluenoise@v1", price: "$0.003", what: "signed blue-noise set" }],
    camera: [0, 2, 13],
    tests: 13,
  },
  {
    slug: "percola",
    name: "Percola",
    accent: "#22d3ee",
    skill: "Network-resilience threshold",
    blurb:
      "When does the whole trust graph fall apart? Computes the critical attack fraction f_c, collapse curve, susceptibility peak, and keystone nodes — a global phase transition no per-node score can express.",
    math: "Bond percolation · giant-component collapse · targeted & random attack sweeps",
    caps: [
      { id: "percola.threshold@v1", price: "$0.01", what: "f_c + collapse curve + keystones" },
      { id: "percola.verify@v1", price: "$0.001", what: "trustless replay of f_c" },
    ],
    camera: [0, 2, 14],
    tests: 15,
    ambient: true,
  },
  {
    slug: "fermat",
    name: "Fermat",
    accent: "#f97316",
    skill: "Least-time routing with a dual certificate",
    blurb:
      "Provably optimal capability composition over a weighted service graph — returns the least-time path plus eikonal potentials T(v) any client can verify in O(E) without re-running search.",
    math: "Eikonal / Bellman optimality · Fermat's principle · complementary slackness",
    caps: [
      { id: "fermat.route@v1", price: "$0.01", what: "path + potentials + certificate" },
      { id: "fermat.verify@v1", price: "$0.001", what: "O(E) trustless certificate check" },
    ],
    camera: [0, 2, 14],
    tests: 24,
    ambient: true,
  },
  {
    slug: "ablation",
    name: "Ablation",
    accent: "#ef4444",
    skill: "Systemic cascade-risk (SOC sandpile)",
    blurb:
      "The tail risk of a dependency network: drives stress through a sandpile, fits the avalanche power-law τ, VaR/CVaR tails, and the trigger nodes that ignite market-wide cascades.",
    math: "Abelian sandpile · self-organized criticality · Dhar's theorem",
    caps: [
      { id: "ablation.cascade@v1", price: "$0.01", what: "τ + tail VaR/CVaR + triggers" },
      { id: "ablation.verify@v1", price: "$0.001", what: "trustless sandpile replay" },
    ],
    camera: [0, 2, 14],
    tests: 34,
    ambient: true,
  },
  {
    slug: "landauer",
    name: "Landauer",
    accent: "#fb7185",
    skill: "Thermodynamic compute-cost audit",
    blurb:
      "The physical price of irreversible computation: counts logically erased bits, derives the kT·ln2 energy floor in joules, Bennett's reversible bound, and thermodynamic efficiency.",
    math: "Landauer's principle · Bennett reversible lower bound · circuit erasure audit",
    caps: [
      { id: "landauer.audit@v1", price: "$0.01", what: "bit erasures + energy floor J" },
      { id: "landauer.verify@v1", price: "$0.001", what: "trustless erasure replay" },
    ],
    camera: [0, 2, 14],
    tests: 35,
    ambient: true,
  },
  {
    slug: "sortes",
    name: "Sortes",
    accent: "#fde047",
    skill: "True ECVRF — ungrindable verifiable randomness",
    blurb:
      "Draws lots you can verify. For a fixed (key, input) there is exactly ONE valid output — the oracle cannot grind or bias it, and anyone can verify the draw offline from an 80-byte proof. Lotteries, sortition, leader election, fair nonces.",
    math: "ECVRF-EDWARDS25519-SHA512-TAI (RFC 9381) · edwards25519 · hash-to-curve try-and-increment · offline verifiable",
    caps: [
      { id: "sortes.draw@v1", price: "$0.006", what: "VRF output β + proof π" },
      { id: "sortes.verify@v1", price: "$0.001", what: "offline trustless verify" },
    ],
    camera: [0, 2, 14],
    tests: 30,
  },
  {
    slug: "gauss",
    name: "Gauss",
    accent: "#a5b4fc",
    skill: "Gaussian-Process posterior + active-learning suggestions",
    blurb:
      "Turns sparse, noisy observations into a calibrated posterior over functions — a mean and an honest uncertainty everywhere — and names the single best next point to sample. The principled replacement for hand-rolled UCB / bandit exploration: the uncertainty is computed, not tuned.",
    math: "Gaussian-Process regression · RBF kernel k(x,x')=σ_f²·exp(−‖x−x'‖²/2l²) · Cholesky posterior · Expected Improvement acquisition",
    caps: [
      { id: "gauss.field@v1", price: "$0.006", what: "posterior mean + variance field" },
      { id: "gauss.suggest@v1", price: "$0.006", what: "best next point by Expected Improvement" },
      { id: "gauss.verify@v1", price: "$0.001", what: "trustless posterior replay" },
    ],
    camera: [0, 2, 13],
    tests: 18,
  },
  {
    slug: "aestus",
    name: "Aestus",
    accent: "#5eead4",
    skill: "Time-lock puzzles — seal now, opens later",
    blurb:
      "Seals data so NOBODY can open it before ~T sequential squarings of wall-clock have elapsed — then ANYONE can, with no trapdoor holder. Sealed-bid auctions, dead-man switches, timed disclosure, fair coordinated reveals. Where Chronos proves the past elapsed, Aestus locks the future.",
    math: "Rivest-Shamir-Wagner time-lock · b = a^(2^T) mod N over a FRESH RSA modulus · φ(N) burned every seal (no shortcut, not even for the oracle)",
    caps: [
      { id: "aestus.seal@v1", price: "$0.006", what: "time-lock data → puzzle (trapdoor burned)" },
      { id: "aestus.open@v1", price: "$0.01", what: "redo T squarings → decrypt + verify" },
      { id: "aestus.verify@v1", price: "$0.001", what: "cheap one-hash check of unlock value b" },
    ],
    camera: [0, 2, 14],
    tests: 16,
  },
  {
    slug: "betti",
    name: "Betti",
    accent: "#f0abfc",
    skill: "Topological shape — persistent homology",
    blurb:
      "What SHAPE does the data have? Builds a Vietoris-Rips filtration and reads off Betti numbers b0 (clusters), b1 (loops), b2 (voids) across scale, plus a bottleneck-distance drift alarm — structure no scalar summary can express.",
    math: "Vietoris-Rips filtration · GF(2) persistence reduction · persistence barcode · bottleneck distance",
    caps: [
      { id: "betti.homology@v1", price: "$0.008", what: "b0/b1/b2 + Betti curve + diagram" },
      { id: "betti.distance@v1", price: "$0.004", what: "bottleneck drift between two diagrams" },
    ],
    camera: [0, 2, 18],
    tests: 14,
  },
  {
    slug: "kantor",
    name: "Kantor",
    accent: "#e879f9",
    skill: "Exact optimal transport with a dual certificate",
    blurb:
      "How cheaply can one distribution become another — and is it provably the cheapest? Solves the exact Wasserstein / earth-mover problem and returns the transport plan plus Kantorovich potentials any client can verify in O(m·n) without re-solving.",
    math: "Kantorovich optimal transport · min-cost flow · LP duality / complementary slackness · p-Wasserstein W_p",
    caps: [
      { id: "kantor.transport@v1", price: "$0.006", what: "OT plan + cost + W_p + dual potentials" },
      { id: "kantor.verify@v1", price: "$0.001", what: "O(m·n) trustless dual-certificate check" },
    ],
    camera: [0, 2, 16],
    tests: 23,
  },
  {
    slug: "fourier",
    name: "Fourier",
    accent: "#60a5fa",
    skill: "Graph-spectral analysis — Laplacian spectrum & Fiedler value",
    blurb:
      "The Fourier transform on a graph. Reads the algebraic connectivity λ₂ (how close a network is to splitting), the Fiedler vector and its spectral bisection, and a spectral embedding — the global structure no per-node metric captures.",
    math: "Graph Laplacian L = D − A (and normalized L_sym) · eigendecomposition · λ₂ Fiedler value · spectral cut & conductance",
    caps: [
      { id: "fourier.spectrum@v1", price: "$0.005", what: "λ₂ + Fiedler + spectral cut + embedding" },
      { id: "fourier.verify@v1", price: "$0.001", what: "O(E) trustless eigenpair certificate" },
    ],
    camera: [0, 2, 16],
    tests: 17,
  },
];

export const oracleBySlug = (slug: string): Oracle | undefined =>
  ORACLES.find((o) => o.slug === slug);

/** Per-oracle source link: Platon has its own repo; the rest live as subfolders
 *  of the `oracles` family monorepo. */
export const oracleGithubUrl = (o: Oracle): string =>
  o.githubUrl ?? `${ORACLES_REPO}/tree/main/oracles/${o.slug}`;
