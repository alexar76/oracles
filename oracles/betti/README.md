# Betti — Topological-Shape Oracle 🕳️

**Betti sells the *shape* of data.** Given a point cloud it builds a **Vietoris–Rips
filtration** and runs the standard **GF(2) persistence reduction** to read off the
**Betti numbers** as a function of scale:

- **b₀** — connected components (how many clusters),
- **b₁** — loops / holes (1-cycles that don't fill in),
- **b₂** — voids / cavities (hollow 3-D regions),

plus the full **persistence barcode/diagram** and a **bottleneck distance** between two
diagrams — a basis-free, noise-stable **drift detector**: ~0 when two clouds share a
topology, clearly positive when the shape changed (a loop appeared, components merged,
a cavity opened).

Built on **`oracle-core`** (AIMarket Protocol v2). Where [Lumen](../lumen) scores *who*
to trust and [Percola](../percola) finds *when a graph collapses*, Betti answers *what
shape the data has* — structure no scalar summary statistic can express.

```bash
# Homology: 24 points on a ring → one loop (b1 = 1), one component (b0 = 1)
curl -s -X POST http://localhost:9313/ai-market/v2/invoke -H "Content-Type: application/json" \
  -d '{"capability_id":"betti.homology@v1","input":{"points":[[1,0],[0.97,0.26],[0.87,0.5],[0.71,0.71],[0.5,0.87],[0.26,0.97],[0,1],[-0.26,0.97],[-0.5,0.87],[-0.71,0.71],[-0.87,0.5],[-0.97,0.26],[-1,0],[-0.97,-0.26],[-0.87,-0.5],[-0.71,-0.71],[-0.5,-0.87],[-0.26,-0.97],[0,-1],[0.26,-0.97],[0.5,-0.87],[0.71,-0.71],[0.87,-0.5],[0.97,-0.26]],"max_scale":0.5}}'
```

| Capability | What | Price |
|---|---|---|
| `betti.homology@v1` | b₀/b₁/b₂ at scale, Betti curve, persistence diagram | $0.008 |
| `betti.distance@v1` | bottleneck distance between two diagrams (topology drift) | $0.004 |

## The mathematics

- **Vietoris–Rips:** vertices at scale 0; an edge when a pair distance ≤ ε; a triangle
  when all three edges exist; a tetrahedron when all four faces exist (needed for a true
  b₂). Each simplex's filtration value (birth) is its longest edge.
- **Reduction:** sort simplices by `(filtration, dimension)`, build the boundary matrix as
  GF(2) columns of face-index sets, reduce left-to-right by the low-row pivot. Each pivot
  pairs a birth simplex with a death simplex → a persistence interval `[birth, death]`;
  unpaired columns are essential (infinite) bars. b₀ is cross-checked with union–find.
- **Betti curve:** `b_k(ε)` = number of dim-k bars alive at ε.
- **Bottleneck:** exact matching via *binary search on ε + Hopcroft–Karp/Kuhn perfect
  matching* on the threshold bipartite graph, with the diagonal allowed. Complexity per
  feasibility check `O(E·√V)`; `V ≤ 2(|A|+|B|)` after the diagram cap.

## Hard caps (no silent truncation)

The protocol layer does **not** validate input, so the handlers do. A Rips complex is
combinatorially explosive, so Betti caps **points at 300** and **total simplices at
150 000**; if it clips, it says so in the response `notes`/`capped` fields rather than
quietly dropping data. Missing/malformed `points` raise `ValueError` → `{ok:false}`.

Part of the [AICOM oracle family](https://github.com/alexar76/oracles). MIT.
