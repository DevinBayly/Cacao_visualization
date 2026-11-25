# Sap Flow Particle Visualization

This folder contains a small pipeline that takes **two inputs** — a tree
skeleton (PLY point cloud) and sap flow measurements (CSV) — and turns
them into an **animated Pixar USD file** (`usdc`) where particles flow
from the roots of the tree up through its branches and out to the leaf
tips. The speed of the particles at any moment is driven by the measured
flow, so you can scrub through the animation in Blender and watch the
sap "move" exactly as the data says it did.

Everything that used to live (scattered across 54 cells) in
[`networkx_curve_separation.ipynb`](./networkx_curve_separation.ipynb) is
now restructured into one script with one function per stage:
**[`sap_flow_usd.py`](./sap_flow_usd.py)**.

---

## Quick start

```bash
# 1. dependencies (a ready .venv already exists in this folder)
pip install numpy networkx usd-core        # usd-core provides the `pxr` module
pip install pandas                         # optional, nicer CSV handling

# 2. no data yet? make a demo animation from pure random numbers
python demo_random_usd.py --frames 100 --points 500 --out demo_random.usdc

# 3. the real pipeline (sample inputs included in this folder)
python sap_flow_usd.py --skeleton test_skeleton.ply --flow test_flow.csv \
                       --out sap_flow.usdc

# 4. open sap_flow.usdc in Blender, select /mypoints, scrub the timeline
```

### The two inputs

| Input      | What it is                                                                 |
|------------|----------------------------------------------------------------------------|
| **PLY**    | The thinned tree skeleton as a point cloud (x, y, z per line). ASCII or binary PLY both work. No ordering or branch labels needed — the script reconstructs connectivity itself. |
| **CSV**    | One numeric column **per root**, one row **per time frame** — or a **single column** with the overall sap flow rate, which is applied to every branch. Flow values act as a per-frame speed multiplier: `0` freezes the particles, larger values make them travel faster. An optional leading `time` column is ignored. |

---

## How it works (flow chart)

```
            INPUTS
   skeleton.ply             flow.csv
   (N skeleton points)      (one flow column per root,
                             one row per frame)
        |                            |
        v                            |
 +------------------+                |
 | 1. load_ply      |                |
 |    raw PLY ->    |                |
 |    (N,3) array   |                |
 +------------------+                |
        |                            |
        v                            |
 +------------------+                |
 | 2. build_graph   |                |
 |    connect each  |                |
 |    point to its k |               |
 |    neighbours;    |               |
 |    grow k until   |               |
 |    one component  |               |
 +------------------+                |
        |                            |
        v                            |
 +------------------+                |
 | 3. find_roots_   |                |
 |    tips          |                |
 |    "dead end"    |                |
 |    angle test -> |                |
 |    tips; lowest  |                |
 |    N tips =      |                |
 |    roots         |                |
 +------------------+                |
        |                            |
        v                            |
 +------------------+                |
 | 4. compute_paths |                |
 |    shortest path |                |
 |    for every     |                |
 |    root -> tip   |                |
 +------------------+                |
        |                            |
        v                            |
 +------------------+                |
 | 5. build_tracks  |                |
 |    ordered x,y,z |                |
 |    per path      |                |
 +------------------+                |
        |                            |
        v                            v
 +-------------------------------------------+
 | 6. load_flow_csv    -> (roots, frames)    |
 +-------------------------------------------+
        |
        v
 +-------------------------------------------+
 | 7. simulate                                 |
 |    continuous stream of particles per track |
 |    (staggered --spacing points apart); each |
 |    frame they advance speed * flow[root,    |
 |    frame] points; interpolated between      |
 |    skeleton points; recycled to the root    |
 |    when they reach a tip                    |
 +-------------------------------------------+
        |
        v
 +-------------------------------------------+
 | 8. export_usd                                |
 |    UsdGeom.Points at /mypoints, one         |
 |    position value per frame, time range     |
 |    0..T-1, fps written into the stage       |
 +-------------------------------------------+
        |
        v
   sap_flow.usdc  ---->  Blender: File > Open, scrub the timeline
```

---

## Stage by stage

1. **Load the skeleton (`load_ply`)**
   Reads the vertex x/y/z of a PLY file (ASCII or binary, list
   properties like face indices are skipped) into a plain `(N, 3)`
   numpy array. No 3D library required.

2. **Rebuild the tree graph (`build_graph`)**
   The old notebook got its graph from a hand-labelled polylines file
   where each line was one branch. A raw PLY has no ordering, so the
   script connects each point to its *k* nearest neighbours instead.
   `k` starts at `--k` (default 4) and is automatically increased up to
   `--k-max` until the graph is a single connected component — that
   keeps branch junctions bridged even on sparse skeleton exports.

3. **Find roots and leaf tips (`find_roots_tips`)**
   A point is a branch tip if its two nearest neighbours sit in almost
   the *same* direction (angle `< --tip-angle`, default 60°); interior
   points have neighbours on opposite sides (~180°). Tips are then
   sorted by their y (height) coordinate: the `--num-roots` (default 4)
   tips at the end of the y range chosen by `--root-end` are the
   **roots** at the base of the tree, the rest are the **leaf tips**.
   `--root-end low` (default, the old notebook convention) puts the
   roots at the smallest y; use `--root-end high` if your skeleton
   export has the base at the largest y. *If the particles appear to
   run backwards over the tree, flip `--root-end`.*

4. **Compute paths (`compute_paths`)**
   For every (root, tip) pair, `networkx.shortest_path` gives the route
   sap will take. Unreachable pairs (a broken skeleton) are skipped
   with a warning instead of crashing.

5. **Build tracks (`build_tracks`)**
   Each path becomes a *track*: the ordered list of 3D positions a
   single particle will follow. Every track also remembers which root
   it starts from, which is what lets the flow data drive it later.

6. **Load the flow data (`load_flow_csv`)**
   The CSV is transposed into a `(roots, frames)` table. Column order
   must match root order (lowest tip first) — or you can supply a
   single flow-rate column and it is broadcast to all roots. The
   script errors clearly if the column count matches neither case.

7. **Simulate (`simulate`)**
   Each track carries a **continuous stream** of particles, staggered
   `--spacing` skeleton points apart along the path (default 20).
   Every frame each particle advances by
   `--speed × flow[root, frame]` skeleton points; progress is
   fractional and positions are **linearly interpolated** between
   skeleton points, so motion is smooth rather than point-to-point
   hopping. When a particle reaches its tip it is **recycled back to
   the root**, so fresh particles keep entering the tree for the whole
   run — the density of the flow at any moment is what the data says.
   Output: one `(P, 3)` array per frame.

8. **Export USD (`export_usd`)**
   Creates a new usdc stage with a single `UsdGeom.Points` primitive at
   `/mypoints`, writes one position value per frame, and stamps the
   stage with the frame range (`0..T-1`) and frame rate (`--fps`).
   That's all Blender needs to play the animation back.

### Optional side outputs

* `--out-json FILE` — the whole simulation as JSON (frames of
  `{x,y,z}` objects) for the web visualisation prototyping the old
  notebook used with `cors_vis_server.py`.
* `--obj-dir DIR` — one `.obj` polyline per root-to-leaf path, handy
  for eyeballing the computed routes.

---

## `demo_random_usd.py`

A zero-input starting point for people who don't have data yet: it
generates a series of random numpy arrays (`frames × points × 3`,
exactly what the old notebook prototyped with `test.json`) and writes
them out as a usdc using the **same** `export_usd` function as the main
pipeline. Use it to verify your Blender USD playback setup first:

```bash
python demo_random_usd.py --frames 240 --points 1000 --out demo.usdc --fps 24
```

---

## Tuning & troubleshooting

| Symptom | Try |
|---|---|
| `graph still has N components` warning | raise `--k-max` (e.g. 16) — the skeleton has sparse gaps |
| too few / too many tips found | raise / lower `--tip-angle` |
| wrong points treated as roots | change `--num-roots` |
| particles running backwards over the tree | flip `--root-end` to `high` (or `low`) |
| particles too fast / too slow overall | scale the CSV values or use `--speed` |
| everything arrives before the CSV ends | particles travel ~1 skeleton point per frame per unit of flow — normalise your flow data |
| flow looks too sparse / too dense | lower / raise `--spacing` (points between particles) |
| USD file very large | raise `--spacing` to cut the particle count |
| USD opens but looks empty in Blender | make sure you select `/mypoints` and scrub inside the frame range |

## Files in this folder

| File | Purpose |
|---|---|
| `sap_flow_usd.py` | the main pipeline (this README describes it) |
| `demo_random_usd.py` | random-data demo, no inputs needed |
| `test_skeleton.ply` | sample skeleton (converted from `skel-poly.polylines.txt`) |
| `test_flow.csv` | sample synthetic flow, one column per root (4 × 158 frames) |
| `test_flow_single.csv` | same flow as a single rate column applied to all branches |
| `networkx_curve_separation.ipynb` | the original notebook — kept for history |
| `first_custom.usdc` | example output from the notebook era |
| `skel-poly.polylines.txt` | original hand-labelled branch polylines |
| `cors_vis_server.py` | tiny local CORS server for web prototyping of `--out-json` |
| `.venv/` | ready-to-use virtualenv with all dependencies |