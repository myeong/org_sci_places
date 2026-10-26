#!/usr/bin/env python3
"""Copy demo/data/*.json to Firestore for the map website (Firebase project org-sci-boundaries).

Layout (kept small so one page view costs about ten document reads, not thousands):
  map/meta                       the meta.json object, plus how many chunks each layer has
  map_chunks/<layer>_<i>         {layer, i, n, json}: a JSON string holding up to ~700 KB of that layer's records
Records are stored as JSON strings because Firestore documents are limited to 1 MB and cannot hold arrays of arrays
(the hexagon outlines). groups.json carries each group's scores and its anonymised public_description, shown in venue pop-ups.

Auth: the owner's Google login (gcloud auth application-default login). The web rules allow no writes.
Run: .venv/bin/python scripts/upload_firestore.py
"""
import hashlib, json, os
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")   # use the system DNS resolver; gRPC's own one can fail on some networks
from pathlib import Path
from google.cloud import firestore

ROOT = Path(__file__).resolve().parents[1]; D = ROOT / "demo/data"
PROJECT = os.environ.get("FIREBASE_PROJECT", "org-sci-boundaries"); LIMIT = 700_000
db = firestore.Client(project=PROJECT)
meta = json.load(open(D / "meta.json")); meta["chunks"] = {}
old = {d.id for d in db.collection("map_chunks").list_documents()}; new = set()
for layer in ["places", "venues", "hexes", "groups"]:
    items = json.load(open(D / f"{layer}.json")); chunks, cur, size = [], [], 0
    for it in items:
        s = len(json.dumps(it, ensure_ascii=False, separators=(",", ":")).encode())
        if cur and size + s > LIMIT: chunks.append(cur); cur, size = [], 0
        cur.append(it); size += s + 1
    if cur: chunks.append(cur)
    for i, c in enumerate(chunks):
        doc = f"{layer}_{i:03d}"; new.add(doc)
        db.collection("map_chunks").document(doc).set({"layer": layer, "i": i, "n": len(c), "json": json.dumps(c, ensure_ascii=False, separators=(",", ":"))})
    meta["chunks"][layer] = len(chunks); print(f"{layer}: {len(items):,} records in {len(chunks)} documents")
# boundary surfaces (scripts/build_boundaries.py): one layer per surface, fetched by the site only when shown
bidx = json.load(open(D / "boundaries_index.json")) if (D / "boundaries_index.json").exists() else {"surfaces": []}
meta["boundaries"] = {"params": bidx.get("params", {}), "surfaces": []}
for s in bidx["surfaces"]:
    obj = json.load(open(D / "boundaries" / s["file"])); layer = "bnd:" + s["key"]
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":")); parts = [txt[i:i + LIMIT] for i in range(0, len(txt), LIMIT)]
    for i, part in enumerate(parts):
        doc = f"bnd_{hashlib.sha1(s['key'].encode()).hexdigest()[:12]}_{i:02d}"; new.add(doc)
        db.collection("map_chunks").document(doc).set({"layer": layer, "i": i, "n": len(parts), "text": part})
    meta["boundaries"]["surfaces"].append({**{k: s[k] for k in ("key", "source", "dim", "choice", "regions", "lines", "region_share")}, "parts": len(parts)})
print(f"boundaries: {len(bidx['surfaces'])} surfaces")
for doc in old - new: db.collection("map_chunks").document(doc).delete()
db.collection("map").document("meta").set(meta)
print(f"uploaded to Firestore project {PROJECT}; removed {len(old - new)} stale documents")
