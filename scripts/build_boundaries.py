#!/usr/bin/env python3
"""Regions and boundary lines for the map: where a characteristic is concentrated, and how sharply it changes.

Design:
  - polygons that let a reader see boundaries between regions for the dimension in focus, not only shaded hexagons;
  - Google places and Meetup groups kept separate;
  - boundary lines drawn according to the evidence: faint or blurred where data are sparse or the line's position is
    uncertain, thick and crisp where two neighbouring regions differ sharply.

Method, for each source and each dimension (or identity, or lean):
  1. Units. Google: each scored place, weighted by its sample weight; indicator = score of 3 or more.
     Meetup: each group at each street-level venue where it met, weighted by its events there; indicator = the group's score.
     Unwelcomeness (Google only): weighted reports and weighted text reviews per place, as in build_demo_data.py.
  2. Surface. Bin the weights onto a 250 m grid and smooth with a Gaussian kernel (sigma 1.5 km). The smoothed share is
     smoothed(indicator x weight) / smoothed(weight); support is the Kish effective number of units under the kernel.
  3. Regions. Classes relative to the region-wide share r: below average (< r/2), about average, concentrated (>= 2r),
     strongly concentrated (>= 4r). Only where support is at least MIN_SUPPORT. Filled contours become polygons.
  4. Lines. Contours at 2r and 4r, cut into short pieces. Each piece gets
       sharpness  = how fast the share changes across the line (in multiples of r per km), and
       certainty  = how precisely the line is placed: bootstrap spread of the share divided by that rate of change (km),
                    and the support there.
     Sharp and certain pieces are drawn thick and crisp; gradual or uncertain ones thin, faint, or blurred.
  5. Stability. 100 bootstrap resamples (Google by place, Meetup by group). A region's stability is the share of
     resamples in which its cells stay in the same class.

Output: demo/data/boundaries/<key>.json and an index in demo/data/boundaries_index.json; scripts/upload_firestore.py uploads them.
Run:    python scripts/build_boundaries.py   (add --suffix _x to read dimension_scores_places_x.jsonl and its inputs)
"""
import argparse, collections, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]; D = ROOT / "demo/data"; A = ROOT / "data/analysis"
ap = argparse.ArgumentParser(); ap.add_argument("--suffix", default="", help="score files to read, e.g. _sample, as in build_demo_data.py"); args = ap.parse_args()
CELL_M, SIGMA_M, MIN_SUPPORT, MIN_UNITS, N_BOOT, SEED = 250, 1500, 5.0, 15, 100, 20261026
LEVELS = [0.5, 2.0, 4.0]                       # in multiples of the region-wide share
CLASS_NAMES = ["below average", "about average", "concentrated", "strongly concentrated"]

places = json.load(open(D / "places.json")); groups = {g["id"]: g for g in json.load(open(D / "groups.json"))}
venues = {v["id"]: v for v in json.load(open(D / "venues.json"))}
meta = json.load(open(D / "meta.json"))
IDENTITY_BASIS = {"ethnicity_nationality", "religion", "gender", "sexuality", "race", "language"}

# ---------------------------------------------------------------- grid (local metres around the region's centre)
lats = [p["lat"] for p in places] + [v["lat"] for v in venues.values()]; lons = [p["lon"] for p in places] + [v["lon"] for v in venues.values()]
LAT0, LON0 = float(np.median(lats)), float(np.median(lons)); KX, KY = 111320 * math.cos(math.radians(LAT0)), 110540
def xy(lat, lon): return (lon - LON0) * KX, (lat - LAT0) * KY
xs, ys = zip(*(xy(a, b) for a, b in zip(lats, lons))); PAD = 4 * SIGMA_M
X0, Y0 = min(xs) - PAD, min(ys) - PAD; NX, NY = int((max(xs) + PAD - X0) / CELL_M) + 1, int((max(ys) + PAD - Y0) / CELL_M) + 1
SIG = SIGMA_M / CELL_M
def to_latlon(px, py):                         # grid coordinates (column, row) -> lat, lon
    return round(LAT0 + (Y0 + py * CELL_M) / KY, 5), round(LON0 + (X0 + px * CELL_M) / KX, 5)
def cell(lat, lon):
    x, y = xy(lat, lon); return int((y - Y0) / CELL_M), int((x - X0) / CELL_M)
print(f"grid {NX} x {NY} cells of {CELL_M} m; kernel sigma {SIGMA_M} m")

# ---------------------------------------------------------------- units per source
# Google: (row, col, weight, unit id); Meetup: (row, col, events, group id)
G_UNITS = [(*cell(p["lat"], p["lon"]), p["w"], p["id"]) for p in places]
ev = pd.read_csv(A / "tables/meetup_events_slim.csv.gz", dtype={"group_id": str, "N_ID": str}, usecols=["group_id", "N_ID", "location_source", "location_quality"])
ev = ev[(ev.location_source == "clean_venue") & (ev.location_quality == "ok") & ev.group_id.isin(groups) & ev.N_ID.isin(venues)]
M_UNITS = [(*cell(venues[vk]["lat"], venues[vk]["lon"]), float(n), g) for (g, vk), n in ev.groupby(["group_id", "N_ID"]).size().items()]
print(f"units: {len(G_UNITS):,} Google places; {len(M_UNITS):,} Meetup group-venue pairs from {ev.group_id.nunique():,} groups")

def value(rec, dim, choice):
    if dim == "targeting":
        if choice == "all": return rec["t"] if (rec.get("tb") in IDENTITY_BASIS) else 0
        return rec["ti"].get(choice, 0)
    if dim == "cultural": return rec["c"] if choice == "all" else rec["ci"].get(choice, 0)
    if dim == "barrier": return rec["b"]
    if dim == "political": return rec["p"] if choice == "all" else (rec["p"] if rec["lean"] == choice else 0)

# ---------------------------------------------------------------- unwelcome reports per place (aggregate only; never written per place)
def unwelcome_units():
    import gzip
    W = json.load(open(A / "sample_weights_places.json")) if args.suffix and (A / "sample_weights_places.json").exists() else {}
    inp = {d["unit_id"]: d for d in map(json.loads, gzip.open(A / f"dimension_inputs_places{args.suffix}.jsonl.gz", "rt"))}
    out = []
    for s in map(json.loads, open(A / f"dimension_scores_places{args.suffix}.jsonl")):
        u = s["unit_id"]; i = inp[u]; w = W.get(u, 1.0); strata = i.get("strata") or {}; rep = 0.0; seen = set()
        for g in s["unwelcome"]["groups"] if s["unwelcome"]["score"] >= 1 else []:
            for k in g["reviews"]:
                if k in seen or not 1 <= k <= len(i["shown"]): continue
                sh = i["shown"][k - 1]
                if not i["screened"]: wk = 1.0
                elif not sh["picked"]: continue
                else: N, n = strata[str(sh["stars"])]; wk = N / n
                seen.add(k); rep += wk
        p = next(q for q in places if q["id"] == u)
        out.append((*cell(p["lat"], p["lon"]), w, u, rep, i["n_text_reviews"]))
    return out

# ---------------------------------------------------------------- surfaces
def smooth(rows, cols, vals, sigma=None):
    g = np.zeros((NY, NX)); np.add.at(g, (rows, cols), vals); return gaussian_filter(g, SIG if sigma is None else sigma, mode="constant")
def surfaces(units, ind, w):
    r, c = units[:, 0].astype(int), units[:, 1].astype(int)
    num, den = smooth(r, c, w * ind), smooth(r, c, w)
    # Kish effective size under the kernel k: (sum k w)^2 / sum (k w)^2. A squared Gaussian of width s is a Gaussian of
    # width s/sqrt(2) divided by 4 pi s^2, so sum k^2 w^2 is the w^2 surface smoothed at s/sqrt(2), over 4 pi s^2.
    w2 = smooth(r, c, w * w, SIG / math.sqrt(2)) / (4 * math.pi * SIG ** 2)
    with np.errstate(invalid="ignore", divide="ignore"):
        share = np.where(den > 1e-9, num / den, np.nan); ess = np.where(w2 > 1e-12, den ** 2 / w2, 0)
    return share, ess

def polygons_from_contourf(cs_paths, scale_fn):
    """Matplotlib filled-contour paths -> shapely polygons in lat/lon (outer rings with their holes)."""
    polys = []
    for path in cs_paths:
        rings = [r for r in path.to_polygons() if len(r) >= 4]
        shapes = sorted((Polygon(r) for r in rings), key=lambda p: -abs(p.area))
        outers = []
        for s in shapes:
            if not s.is_valid: s = s.buffer(0)
            host = next((o for o in outers if o[0].contains(s.representative_point())), None)
            if host: host[1].append(s)
            else: outers.append([s, []])
        for o, holes in outers:
            poly = o.difference(unary_union(holes)) if holes else o
            polys.append(poly)
    return polys

def ring_ll(coords): return [list(to_latlon(px, py)) for px, py in coords]

def build(key, source, dim, choice, units, ind, w, kind="share", reports=None, reviews=None):
    rng = np.random.default_rng(SEED)
    if kind == "share":
        share, ess = surfaces(units, ind, w); r_all = float((ind * w).sum() / w.sum())
    else:                                       # unwelcome: reports per 1,000 reviews
        rr, cc = units[:, 0].astype(int), units[:, 1].astype(int)
        num, den = smooth(rr, cc, w * reports), smooth(rr, cc, w * reviews)
        _, ess = surfaces(units, np.zeros(len(units)), w)
        with np.errstate(invalid="ignore", divide="ignore"): share = np.where(den > 1e-9, 1000 * num / den, np.nan)
        r_all = float(1000 * (w * reports).sum() / (w * reviews).sum())
        ess = np.where(smooth(rr, cc, reviews) * 2 * math.pi * SIG ** 2 >= 300, ess, 0)   # at least ~300 reviews under the kernel (its effective area is 2 pi sigma^2)
    if r_all <= 0: return None
    rel = share / r_all; ok = (ess >= MIN_SUPPORT) & np.isfinite(rel)
    # bootstrap: Google by place; Meetup by group
    owners = units[:, 3]; uniq = np.unique(owners); idx = {o: np.where(owners == o)[0] for o in uniq}
    boots = np.empty((N_BOOT, NY, NX), dtype=np.float32)
    for b in range(N_BOOT):
        pick = np.concatenate([idx[o] for o in rng.choice(uniq, size=len(uniq), replace=True)])
        u = units[pick]
        if kind == "share": s, _ = surfaces(u, ind[pick], w[pick]); boots[b] = s / r_all
        else:
            rr, cc = u[:, 0].astype(int), u[:, 1].astype(int)
            n_, d_ = smooth(rr, cc, w[pick] * reports[pick]), smooth(rr, cc, w[pick] * reviews[pick])
            with np.errstate(invalid="ignore", divide="ignore"): boots[b] = np.where(d_ > 1e-9, 1000 * n_ / d_, np.nan) / r_all
    sd = np.nanstd(boots, axis=0)
    cls = np.digitize(np.nan_to_num(rel, nan=-1), LEVELS); cls_b = np.digitize(np.nan_to_num(boots, nan=-1), LEVELS)
    agree = (cls_b == cls[None]).mean(axis=0)
    gy, gx = np.gradient(np.nan_to_num(rel)); grad = np.hypot(gx, gy) / (CELL_M / 1000)     # multiples of r per km

    # regions
    Z = np.ma.array(np.nan_to_num(rel), mask=~ok)
    fig, ax = plt.subplots(); cs = ax.contourf(np.arange(NX), np.arange(NY), Z, levels=[-1, *LEVELS, 1e6])
    regions = []
    for li, path in enumerate(cs.get_paths()):
        if li == 1: continue                     # "about average" is left unfilled
        for poly in polygons_from_contourf([path], None):
            if poly.is_empty or poly.area * (CELL_M / 1000) ** 2 < 1.0: continue          # smaller than 1 km2
            poly = poly.simplify(0.4)
            for part in getattr(poly, "geoms", [poly]):
                if part.area * (CELL_M / 1000) ** 2 < 1.0: continue
                mask = np.zeros((NY, NX), bool)
                minx, miny, maxx, maxy = [int(v) for v in part.bounds]
                from shapely import prepared
                pp = prepared.prep(part)
                from shapely.geometry import Point
                for yy in range(max(miny, 0), min(maxy + 1, NY)):
                    for xx in range(max(minx, 0), min(maxx + 1, NX)):
                        if pp.contains(Point(xx, yy)): mask[yy, xx] = True
                if not mask.any(): continue
                regions.append({"level": li, "name": CLASS_NAMES[li], "outer": ring_ll(part.exterior.coords), "holes": [ring_ll(h.coords) for h in part.interiors],
                                "share": round(float(np.nanmean(share[mask])) * (1 if kind != "share" else 100), 1), "support": round(float(np.nanmean(ess[mask])), 1),
                                "stability": round(float(np.nanmean(agree[mask])), 2), "area_km2": round(float(mask.sum() * (CELL_M / 1000) ** 2), 1)})
    plt.close(fig)

    # lines: contours at 2r and 4r, in pieces of about 1 km, each with its own sharpness and certainty
    fig, ax = plt.subplots(); cl = ax.contour(np.arange(NX), np.arange(NY), Z, levels=LEVELS[1:])
    lines = []
    for li, segs in enumerate(cl.allsegs):
        for seg in segs:
            if len(seg) < 3: continue
            for s0 in range(0, len(seg) - 1, 4):
                piece = seg[s0:s0 + 5]
                if len(piece) < 2: continue
                mx, my = piece[len(piece) // 2]; ix, iy = int(round(mx)), int(round(my))
                if not (0 <= ix < NX and 0 <= iy < NY): continue
                g, sp, sup = float(grad[iy, ix]), float(sd[iy, ix]), float(ess[iy, ix])
                pos_unc = sp / g if g > 1e-6 else 99.0                                   # km
                sharp = 0 if g < 0.5 else 1 if g < 1.5 else 2 if g < 3 else 3
                cert = 0 if (pos_unc > 1.0 or sup < 10) else 1 if (pos_unc > 0.4 or sup < 20) else 2
                lines.append({"pts": [list(to_latlon(px, py)) for px, py in piece], "lvl": li + 2, "sharp": sharp, "cert": cert,
                              "grad": round(g, 2), "unc_km": round(min(pos_unc, 9.9), 2), "support": round(sup, 1)})
    plt.close(fig)
    return {"key": key, "source": source, "dim": dim, "choice": choice, "region_share": round(r_all * (100 if kind == "share" else 1), 2),
            "unit": "%" if kind == "share" else "reports per 1,000 reviews", "regions": regions, "lines": lines,
            "params": {"cell_m": CELL_M, "sigma_m": SIGMA_M, "min_support": MIN_SUPPORT, "levels_x_region": LEVELS, "bootstraps": N_BOOT}}

# ---------------------------------------------------------------- which surfaces
G_arr = np.array([[r, c, w, 0] for r, c, w, _ in G_UNITS], dtype=float); G_ids = [u for *_, u in G_UNITS]
G_arr[:, 3] = np.arange(len(G_arr))                                   # resample by place
M_owner = {g: i for i, g in enumerate(sorted({g for *_, g in M_UNITS}))}
M_arr = np.array([[r, c, n, M_owner[g]] for r, c, n, g in M_UNITS], dtype=float); M_gid = [g for *_, g in M_UNITS]
P_by_id = {p["id"]: p for p in places}
def candidates(recs, dim):
    cnt = collections.Counter(k for x in recs for k, v in x[{"targeting": "ti", "cultural": "ci"}[dim]].items() if v >= 3)
    return [k for k, n in cnt.most_common() if n >= MIN_UNITS]
jobs = []
for dim in ["cultural", "targeting", "barrier"]:
    jobs.append(("google", dim, "all"))
    if dim in ("cultural", "targeting"): jobs += [("google", dim, k) for k in candidates(places, dim)]
for dim in ["cultural", "targeting", "barrier", "political"]:
    jobs.append(("meetup", dim, "all"))
    if dim in ("cultural", "targeting"): jobs += [("meetup", dim, k) for k in candidates(groups.values(), dim)]
jobs += [("meetup", "political", l) for l in ["left", "right"]]

out_dir = D / "boundaries"; out_dir.mkdir(exist_ok=True)
for f in out_dir.glob("*.json"): f.unlink()
index = []
for source, dim, choice in jobs:
    if source == "google": ind = np.array([value(P_by_id[u], dim, choice) >= 3 for u in G_ids], float); units, w = G_arr, G_arr[:, 2]
    else: ind = np.array([value(groups[g], dim, choice) >= 3 for g in M_gid], float); units, w = M_arr, M_arr[:, 2]
    if ind.sum() < MIN_UNITS and choice != "all": continue
    key = f"{source}~{dim}~{choice}"
    res = build(key, source, dim, choice, units, ind, w)
    if not res: continue
    fname = "".join(ch if ch.isalnum() or ch in "~-_" else "_" for ch in key) + ".json"
    (out_dir / fname).write_text(json.dumps(res, separators=(",", ":")))
    index.append({"key": key, "file": fname, "source": source, "dim": dim, "choice": choice, "regions": len(res["regions"]), "lines": len(res["lines"]), "region_share": res["region_share"]})
    print(f"{key:55s} regions {len(res['regions']):3d}  line pieces {len(res['lines']):4d}  region-wide {res['region_share']}")
# unwelcomeness (Google only)
U = unwelcome_units(); Ua = np.array([[r, c, w, i] for i, (r, c, w, *_rest) in enumerate(U)], float)
res = build("google~unwelcome~all", "google", "unwelcome", "all", Ua, None, Ua[:, 2], kind="rate",
            reports=np.array([x[4] for x in U], float), reviews=np.array([x[5] for x in U], float))
(out_dir / "google~unwelcome~all.json").write_text(json.dumps(res, separators=(",", ":")))
index.append({"key": res["key"], "file": "google~unwelcome~all.json", "source": "google", "dim": "unwelcome", "choice": "all", "regions": len(res["regions"]), "lines": len(res["lines"]), "region_share": res["region_share"]})
print(f"{res['key']:55s} regions {len(res['regions']):3d}  line pieces {len(res['lines']):4d}  region-wide {res['region_share']}")
(D / "boundaries_index.json").write_text(json.dumps({"params": {"cell_m": CELL_M, "sigma_m": SIGMA_M, "min_support": MIN_SUPPORT, "levels_x_region": LEVELS, "bootstraps": N_BOOT,
    "classes": CLASS_NAMES}, "surfaces": index}, indent=1))
print(f"{len(index)} surfaces written to {out_dir}")
