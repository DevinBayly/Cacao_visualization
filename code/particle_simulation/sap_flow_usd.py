#!/usr/bin/env python3
"""
sap_flow_usd.py

Turn a tree-skeleton PLY point cloud + a sap-flow CSV into an animated
Pixar USD (usdc) file where particles flow from the roots of the tree
up to its leaf tips. The animation speed of each particle is driven by
the measured sap flow in the CSV, so the result can be played back over
time in Blender.

Pipeline (one function per stage, see README.md for a walkthrough):

    load_ply          -> skeleton point cloud             (N, 3)
    build_graph       -> networkx graph of the skeleton   (points + edges)
    find_roots_tips   -> which endpoints are roots, which are leaves
    compute_paths     -> root-to-leaf route for every particle
    build_tracks      -> 3D position sequence for each particle
    load_flow_csv     -> measured flow table              (roots, time)
    simulate          -> particle positions per frame     list[(P, 3)]
                        (recycled streams, not one shot)
    export_usd        -> animated /mypoints in a usdc

Usage:
    python sap_flow_usd.py --skeleton skeleton.ply --flow flow.csv \
                           --out sap_flow.usdc [--num-roots 4] [--speed 1.0]

The flow CSV has one numeric column per root (same order as the
discovered roots, i.e. sorted by y, lowest first) - or a single column
with the overall sap flow rate, which is then applied to every branch.
An optional leading "time" column is ignored.  Flow values are used as
a per-frame speed multiplier: a value of 0 freezes the particles,
larger values make them travel faster along the skeleton.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import struct
from pathlib import Path

import networkx as nx
import numpy as np

log = logging.getLogger("sap_flow_usd")


# ---------------------------------------------------------------------------
# Stage 1: read the PLY skeleton
# ---------------------------------------------------------------------------

# (format char, size in bytes) for the property types we care about
_PLY_TYPES = {
    "char": ("b", 1), "int8": ("b", 1),
    "uchar": ("B", 1), "uint8": ("B", 1),
    "short": ("h", 2), "int16": ("h", 2),
    "ushort": ("H", 2), "uint16": ("H", 2),
    "int": ("i", 4), "int32": ("i", 4),
    "uint": ("I", 4), "uint32": ("I", 4),
    "float": ("f", 4), "float32": ("f", 4),
    "double": ("d", 8), "float64": ("d", 8),
}


def load_ply(path: Path) -> np.ndarray:
    """Read vertex x/y/z from an ASCII or binary PLY file.

    Returns a (N, 3) float32 array. List properties (e.g. face indices)
    are skipped, so this works for both point clouds and meshes.
    """
    path = Path(path)
    raw = path.read_bytes()
    end = raw.find(b"end_header")
    if end < 0:
        raise ValueError(f"{path} is not a valid PLY file (no end_header)")
    nl = raw.find(b"\n", end)
    header = raw[:nl].decode("ascii", "replace")
    body = raw[nl + 1:]

    fmt, n_verts, props = None, 0, []
    in_vertex = False
    for line in header.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "format":
            fmt = parts[1]
        elif parts[0] == "element":
            in_vertex = parts[1] == "vertex"
            if in_vertex:
                n_verts = int(parts[2])
        elif parts[0] == "property" and in_vertex:
            if len(parts) == 3:
                props.append((None, parts[1], parts[2]))          # plain
            elif len(parts) == 4 and parts[1] == "list":
                props.append((parts[2], parts[3], parts[4]))      # list
            else:
                raise ValueError(f"unsupported property line: {line}")

    if fmt is None or not n_verts:
        raise ValueError(f"{path}: no vertex element found in header")
    names = [p[2] for p in props]
    for i in range(len(names) - 2):
        if names[i:i + 3] == ["x", "y", "z"]:
            break
    else:
        raise ValueError(f"{path}: vertex element has no x/y/z properties")

    out = np.zeros((n_verts, 3), dtype=np.float32)
    if fmt == "ascii":
        toks = body.split()
        v, idx = 0, 0
        while v < n_verts and idx < len(toks):
            for count_type, val_type, name in props:
                if count_type is None:
                    val = float(toks[idx])
                    idx += 1
                    if name in ("x", "y", "z"):
                        out[v, "xyz".index(name)] = val
                else:
                    count = int(float(toks[idx]))
                    idx += 1 + count  # skip the list payload
            v += 1
        if v < n_verts:
            raise ValueError(f"{path}: only parsed {v} of {n_verts} ascii vertices")
        return out

    # ---- binary ----------------------------------------------------------
    endian = "<" if fmt == "binary_little_endian" else ">"
    if fmt not in ("binary_little_endian", "binary_big_endian"):
        raise ValueError(f"{path}: unsupported PLY format {fmt!r}")

    # stride = fixed bytes per vertex; list payloads handled per vertex
    stride = 0
    for count_type, val_type, name in props:
        if count_type is None:
            stride += _PLY_TYPES[val_type][1]
        else:
            stride += _PLY_TYPES[count_type][1]  # payload counted per vertex

    if len(body) < n_verts * stride:
        raise ValueError(f"{path}: binary body shorter than expected")

    for v in range(n_verts):
        base = v * stride
        off = 0
        for count_type, val_type, name in props:
            if count_type is None:
                ch, size = _PLY_TYPES[val_type]
                val = struct.unpack_from(endian + ch, body, base + off)[0]
                if name == "x":
                    out[v, 0] = val
                elif name == "y":
                    out[v, 1] = val
                elif name == "z":
                    out[v, 2] = val
                off += size
            else:
                cch, csize = _PLY_TYPES[count_type]
                _, vsize = _PLY_TYPES[val_type]
                count = struct.unpack_from(endian + cch, body, base + off)[0]
                off += csize + count * vsize
    return out


def write_ply(path: Path, points: np.ndarray) -> None:
    """Write points as an ASCII PLY (used by the test/convert helper)."""
    with open(path, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(points)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("end_header\n")
        for x, y, z in points:
            f.write(f"{x} {y} {z}\n")


# ---------------------------------------------------------------------------
# Stage 2: build the networkx graph from the point cloud
# ---------------------------------------------------------------------------

def _knn(points: np.ndarray, k: int, chunk: int = 512) -> np.ndarray:
    """Indices of the k nearest neighbours of every point (brute force,
    computed in row chunks so memory stays bounded)."""
    n = len(points)
    nn = np.empty((n, k), dtype=np.int64)
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        d = np.linalg.norm(points[s:e, None, :] - points[None, :, :], axis=2)
        d[np.arange(e - s), np.arange(s, e)] = np.inf  # exclude self
        nn[s:e] = np.argpartition(d, k - 1, axis=1)[:, :k]
    return nn


def build_graph(points: np.ndarray, k: int = 4, k_max: int = 12) -> nx.Graph:
    """Rebuild the skeleton's connectivity from a raw point cloud.

    The original notebook fed hand-labelled polyline branches into the
    graph; a PLY point cloud has no ordering, so we connect each point
    to its k nearest neighbours.  k starts at `k` and is increased (up
    to `k_max`) until the graph is one connected component, so sparse
    skeleton exports still bridge across branch junctions.
    """
    n = len(points)
    nn_full = _knn(points, k_max)

    g = None
    for k_try in range(k, k_max + 1):
        g = nx.Graph()
        g.add_nodes_from(range(n))
        for i in range(n):
            for j in nn_full[i, :k_try]:
                g.add_edge(i, int(j))
        if nx.number_connected_components(g) == 1:
            log.info("graph connected with k=%d neighbours", k_try)
            break
    else:
        log.warning(
            "graph still has %d components at k=%d - some tips may be "
            "unreachable", nx.number_connected_components(g), k_max
        )

    for i, (x, y, z) in enumerate(points):
        g.nodes[i]["x"], g.nodes[i]["y"], g.nodes[i]["z"] = (
            float(x), float(y), float(z)
        )
    return g


def find_tip_candidates(points: np.ndarray, angle: float = 60.0) -> np.ndarray:
    """Indices of 'dead-end' points: the two nearest neighbours sit in
    almost the same direction (small angle), which marks the end of a
    branch.  Interior points have neighbours on opposite sides (~180 deg).
    """
    nn2 = _knn(points, 2)
    a = points[nn2[:, 0]] - points
    b = points[nn2[:, 1]] - points
    cosang = (a * b).sum(1) / (
        np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12
    )
    ang = np.degrees(np.arccos(np.clip(cosang, -1.0, 1.0)))
    return np.where(ang < angle)[0]


# ---------------------------------------------------------------------------
# Stage 3: find the roots and leaf tips
# ---------------------------------------------------------------------------

def find_roots_tips(g: nx.Graph, points: np.ndarray, num_roots: int,
                    tip_angle: float = 60.0, root_end: str = "low"):
    """Split the dead-end tips into roots and leaf tips.

    Tips are sorted by their y (height) coordinate and the `num_roots`
    tips at `root_end` ("low" = smallest y, "high" = largest y) are
    the roots (the tree base); the rest are the leaf tips sap must
    reach.  `root_end` exists because it depends on how your skeleton
    was exported which way y points - if the particles appear to run
    backwards over the tree, flip it.
    """
    tips = find_tip_candidates(points, angle=tip_angle)
    if len(tips) < num_roots + 1:
        raise ValueError(
            f"expected at least {num_roots + 1} tip candidates, found "
            f"{len(tips)} - try a larger --tip-angle"
        )
    # note that sometimes we want 1 for y, but if the model comes from blender, then 2 for z height
    ys = points[tips, 2]
    order = tips[np.argsort(ys, kind="stable")]
    if root_end == "high":
        order = order[::-1]
    roots = [int(i) for i in order[:num_roots]]
    tips = [int(i) for i in order[num_roots:]]
    root_ys = [points[r, 1] for r in roots]
    log.info(
        "found %d roots (y at %s end: %s), %d leaf tips",
        len(roots), root_end,
        ", ".join(f"{y:.3f}" for y in root_ys), len(tips),
    )
    return roots, tips


# ---------------------------------------------------------------------------
# Stage 4: compute root-to-leaf paths
# ---------------------------------------------------------------------------

def compute_paths(g: nx.Graph, roots, tips) -> list[dict]:
    """Shortest path from every root to every leaf.

    Each entry is {"source", "target", "paths"} where "paths" is the
    list of (start_id, end_id) node pairs along the route - the same
    structure the notebook used.
    """
    paths = []
    skipped = 0
    for r, t in itertools.product(roots, tips):
        try:
            simple = nx.shortest_path(g, r, t)
        except nx.NetworkXNoPath:
            skipped += 1
            continue
        paths.append(
            {"source": r, "target": t, "paths": list(itertools.pairwise(simple))}
        )
    if skipped:
        log.warning("skipped %d unreachable root/tip pairs", skipped)
    log.info("computed %d root-to-leaf paths", len(paths))
    return paths


# ---------------------------------------------------------------------------
# Stage 5: build particle tracks
# ---------------------------------------------------------------------------

def build_tracks(g: nx.Graph, paths: list[dict]) -> list[np.ndarray]:
    """For each path, the ordered x/y/z positions a particle will follow."""
    xyz = np.array(
        [[g.nodes[i]["x"], g.nodes[i]["y"], g.nodes[i]["z"]] for i in g],
        dtype=np.float32,
    )
    # node id -> row index
    order = {n: i for i, n in enumerate(g)}
    tracks = []
    for p in paths:
        ids = [start for start, _ in p["paths"]]  # end of one pair starts the next
        tracks.append(np.asarray([xyz[order[i]] for i in ids]))
    return tracks


# ---------------------------------------------------------------------------
# Stage 6: read the sap flow CSV
# ---------------------------------------------------------------------------

def load_flow_csv(path: Path, num_roots: int) -> np.ndarray:
    """Read the flow table.

    Expected layout: one numeric column per root (same order as the
    discovered roots), rows = time frames - or a single numeric column
    with the overall sap flow rate, which is broadcast to every root.
    An optional first column named "time" is dropped.  Returns a
    (num_roots, T) float array.

    Uses pandas if available, plain csv module otherwise.
    """
    path = Path(path)
    try:
        import pandas as pd
        df = pd.read_csv(path)
        cols = list(df.columns)
        if cols and str(cols[0]).strip().lower() == "time":
            df = df.drop(columns=[cols[0]])
        flow = df.to_numpy(dtype=float).T  # (cols, rows) -> (roots, time)
    except ImportError:
        import csv
        with open(path, newline="") as f:
            rows = list(csv.reader(f))
        header, data = rows[0], rows[1:]
        if header and header[0].strip().lower() == "time":
            data = [r[1:] for r in data]
        flow = np.array(data, dtype=float).T
    n_cols = flow.shape[0]
    if n_cols == 1 and num_roots > 1:
        log.info("single flow column detected - applying it to all %d "
                 "roots", num_roots)
        flow = np.repeat(flow, num_roots, axis=0)
    elif n_cols != num_roots:
        raise ValueError(
            f"flow CSV has {n_cols} data columns but the skeleton has "
            f"{num_roots} roots (a single column is also accepted as a "
            "flow rate for all branches). Check --num-roots or the CSV "
            "layout."
        )
    log.info("loaded flow table: %d roots x %d frames", *flow.shape)
    return flow


# ---------------------------------------------------------------------------
# Stage 7: simulate the particle motion
# ---------------------------------------------------------------------------

def simulate(tracks: list[np.ndarray], root_of_track, flow: np.ndarray,
             speed: float = 1.0, spacing: float = 20.0) -> list[np.ndarray]:
    """Advance continuous streams of particles along the tracks.

    Each track carries a stream of particles, staggered along its path
    `spacing` skeleton points apart.  Every frame each particle
    advances by `speed * flow[root, frame]` skeleton steps; when a
    particle reaches the tip it is recycled back to the root, so new
    particles keep entering the tree for the whole run instead of the
    cloud only thinning out.  Positions are linearly interpolated
    between skeleton points so the motion is smooth.

    Returns a list with one (P, 3) float32 array per frame.
    """
    t_max = flow.shape[1]
    # drop degenerate tracks (need at least 2 points to travel along)
    keep = np.array([len(t) >= 2 for t in tracks])
    tracks = [t for t, k in zip(tracks, keep) if k]
    root_of_track = root_of_track[keep]
    n = len(tracks)

    actual = np.array([len(t) for t in tracks])
    starts = np.concatenate([[0], np.cumsum(actual)[:-1]])
    flat = np.concatenate(tracks).astype(np.float32)

    # one stream per track: staggered starting offsets along the path
    tidx_list, prog_list = [], []
    for i in range(n):
        m = max(1, int(np.ceil((actual[i] - 1) / spacing)))
        tidx_list.append(np.full(m, i, dtype=np.int64))
        prog_list.append(np.arange(m, dtype=np.float64) * spacing)
    tidx = np.concatenate(tidx_list)
    progress = np.concatenate(prog_list)

    plen = actual[tidx]                     # track length per particle
    pstart = starts[tidx]                   # offset into flat per particle
    rate_idx = root_of_track[tidx]          # which flow column drives it
    period = plen - 1                       # wrap range: root -> just before tip

    log.info("simulating %d particles across %d tracks "
             "(spacing %.1f points)", len(progress), n, spacing)
    if len(progress) > 200_000:
        log.warning("%d particles is a lot - consider a larger --spacing",
                    len(progress))

    time_steps = []
    for t in range(t_max):
        idx = np.minimum(progress.astype(np.int64), plen - 1)
        frac = progress - idx
        a = flat[pstart + idx]
        b = flat[pstart + np.minimum(idx + 1, plen - 1)]
        time_steps.append((a + (b - a) * frac[:, None]).astype(np.float32))
        # advance for the next frame; recycle particles that reached a tip
        progress = (progress + speed * flow[rate_idx, t]) % period
    log.info("simulated %d frames", t_max)
    return time_steps


# ---------------------------------------------------------------------------
# Stage 8: export the animated USD
# ---------------------------------------------------------------------------

def export_usd(time_steps: list[np.ndarray], out: Path, fps: float = 24.0) -> Path:
    """Write /mypoints (UsdGeom.Points) with one position value per frame."""
    from pxr import Usd, UsdGeom, Vt

    out = Path(out)
    stage = Usd.Stage.CreateNew(str(out))
    pts = UsdGeom.Points.Define(stage, "/mypoints")
    points = pts.GetPointsAttr()

    t_end = len(time_steps) - 1
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(t_end)
    stage.SetTimeCodesPerSecond(int(round(fps)))

    for i, arr in enumerate(time_steps):
        points.Set(time=i, value=Vt.Vec3fArray.FromNumpy(arr))

    stage.Save()
    log.info("wrote USD file: %s (%d frames @ %d fps)", out, t_end + 1, fps)
    return out


# ---------------------------------------------------------------------------
# Optional side outputs (kept from the notebook for web visualisation)
# ---------------------------------------------------------------------------

def export_json(time_steps: list[np.ndarray], out: Path) -> Path:
    """Web-prototyping format: list of frames of {x,y,z} objects."""
    payload = [
        [{"x": float(p[0]), "y": float(p[1]), "z": float(p[2])} for p in frame]
        for frame in time_steps
    ]
    out = Path(out)
    out.write_text(json.dumps(payload))
    log.info("wrote json: %s", out)
    return out


def export_obj_curves(g: nx.Graph, paths: list[dict], out_dir: Path) -> Path:
    """Write one .obj per root-to-leaf path (polyline visualisation)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    x_attr = nx.get_node_attributes(g, "x")
    y_attr = nx.get_node_attributes(g, "y")
    z_attr = nx.get_node_attributes(g, "z")

    for i, p in enumerate(paths):
        vmap, n = {}, 0
        for a, b in p["paths"]:
            for node_id in (a, b):
                if node_id in vmap:
                    continue
                vmap[node_id] = (n, x_attr[node_id], y_attr[node_id], z_attr[node_id])
                n += 1
        verts = "\n".join(
            f"v {x} {y} {z}" for _, x, y, z in vmap.values()
        )
        lines = "\n".join(
            f"l {vmap[a][0] + 1} {vmap[b][0] + 1}" for a, b in p["paths"]
        )
        (out_dir / f"curve_{i:04d}.obj").write_text(verts + "\n" + lines + "\n")
    log.info("wrote %d curve .obj files to %s", len(paths), out_dir)
    return out_dir


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run(args) -> None:
    # 1 - skeleton points
    points = load_ply(args.skeleton)
    log.info("loaded %d skeleton points from %s", len(points), args.skeleton)

    # 2 - graph
    g = build_graph(points, k=args.k, k_max=args.k_max)
    log.info("built graph: %d nodes, %d edges", g.number_of_nodes(),
             g.number_of_edges())

    # 3 - roots / tips
    roots, tips = find_roots_tips(g, points, args.num_roots,
                                  tip_angle=args.tip_angle,
                                  root_end=args.root_end)

    # 4 - paths
    paths = compute_paths(g, roots, tips)

    # 5 - tracks  (remember which root each track starts from)
    tracks = build_tracks(g, paths)
    root_index = {r: i for i, r in enumerate(roots)}
    root_of_track = np.array([root_index[p["source"]] for p in paths])

    # 6 - flow data
    flow = load_flow_csv(args.flow, len(roots))

    # 7 - simulation
    time_steps = simulate(tracks, root_of_track, flow, speed=args.speed,
                          spacing=args.spacing)

    # 8 - usd output
    export_usd(time_steps, args.out, fps=args.fps)

    if args.out_json:
        export_json(time_steps, args.out_json)
    if args.obj_dir:
        export_obj_curves(g, paths, args.obj_dir)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Map sap-flow CSV data onto a tree skeleton PLY and "
                    "emit an animated USD particle file for Blender."
    )
    ap.add_argument("--skeleton", required=True, type=Path,
                    help="PLY file with the tree skeleton point cloud")
    ap.add_argument("--flow", required=True, type=Path,
                    help="CSV with one numeric flow column per root, or a "
                         "single flow-rate column applied to all branches; "
                         "rows = frames")
    ap.add_argument("--out", default="sap_flow.usdc", type=Path,
                    help="output USD file (default: sap_flow.usdc)")
    ap.add_argument("--num-roots", type=int, default=4,
                    help="number of endpoints at the base to treat as roots "
                         "(default: 4)")
    ap.add_argument("--root-end", dest="root_end", choices=["low", "high"],
                    default="low",
                    help="which y end of the tree the roots are at: 'low' "
                         "= smallest y (default), 'high' = largest y. "
                         "Flip this if the particles run backwards over "
                         "the tree.")
    ap.add_argument("--k", type=int, default=4,
                    help="starting nearest-neighbour count used to connect "
                         "the skeleton (default: 4)")
    ap.add_argument("--k-max", dest="k_max", type=int, default=12,
                    help="k is increased up to this until the graph is "
                         "connected (default: 12)")
    ap.add_argument("--tip-angle", dest="tip_angle", type=float, default=60.0,
                    help="max angle (deg) between the two nearest "
                         "neighbours for a point to count as a branch tip "
                         "(default: 60)")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="global speed multiplier on top of the flow values")
    ap.add_argument("--spacing", type=float, default=20.0,
                    help="skeleton points between particles in each branch "
                         "stream (smaller = denser flow, default: 20)")
    ap.add_argument("--fps", type=float, default=24,
                    help="frame rate written into the USD time period "
                         "(default: 24)")
    ap.add_argument("--out-json", type=Path, default=None,
                    help="also write the simulation as a json for web prototyping")
    ap.add_argument("--obj-dir", type=Path, default=None,
                    help="also write one .obj curve per root-to-leaf path here")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )
    run(args)


if __name__ == "__main__":
    main()
