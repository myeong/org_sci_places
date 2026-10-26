#!/usr/bin/env python3
"""Turn the dimension scores into the small files the map website loads.

Reads   data/analysis/dimension_scores_{places,groups}<suffix>.jsonl, dimension_inputs_places<suffix>.jsonl.gz,
        data/analysis/tables/ (place, group, venue, event attributes), data/reference/dimension_label_vocabulary.csv,
        data/reference/identity_vocabulary.csv (merges label variants into one identity, e.g. "Black" and "African American", and gives its family)
Writes  demo/data/{meta,places,venues,hexes,groups}.json   (tracked; no review text, no quotes)
Then    scripts/upload_firestore.py copies them to Firestore.

What goes on the map, and which conceptual dimension it stands for:
  places   Google places as points: category, exclusivity by design (`targeting`, social), socio-economic barrier (social), cultural identity (cultural).
           Exclusivity and cultural identity are also stored per identity (`ti`, `ci`: {identity: 0-5}), so the map can show
           "aimed at women" or "Korean culture" rather than a score that mixes every group. Labels inferred only from the
           language reviews are written in are kept for the pop-up but not counted as an identity of the place.
           Political identity is NOT exported for places (groups only).
           `unwelcome` is NOT exported per place (areas only).
  venues   Meetup street-level venues as points: the event-weighted mean of the scores of the in-region groups that met there,
           overall and per identity; political identity also per lean (`pl`: {left, right, nonpartisan_civic}).
  hexes    `unwelcome` (psychological: who reports not belonging) as a rate per 1,000 text reviews, pooled over H3 hexagons.

The unwelcome rate. A report is a review that (a) the screening picked, and (b) the scoring model listed under a named
social group. Screening reads at most 100 reviews per place, spread equally across star ratings, so each report is
weighted by (reviews with that rating at the place) / (reviews with that rating that were screened). Places with 20 or
fewer text reviews are read in full (weight 1). While only a sample of places is scored, each place also carries its
sample weight. Rate = weighted reports / weighted text reviews, summed over the hexagon; shown only above MIN_PLACES
and MIN_REVIEWS, because one report among few reviews would otherwise colour a whole cell.

Run: .venv/bin/python scripts/build_demo_data.py --suffix _sample
"""
import argparse, collections, gzip, json, re, time
from pathlib import Path
import h3
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]; A = ROOT / "data/analysis"; REF = ROOT / "data/reference"; OUT = ROOT / "demo/data"
ap = argparse.ArgumentParser(); ap.add_argument("--suffix", default=""); ap.add_argument("--hex-res", type=int, default=7)
ap.add_argument("--min-places", type=int, default=3); ap.add_argument("--min-reviews", type=int, default=300)
args = ap.parse_args()

PLACE_CATS = ["Food & drink", "Shopping", "Services", "Recreation, arts & lodging", "Health & medical", "Automotive & transport", "Education & civic", "Religion"]
FAMILY = {"race": "origin", "ethnicity_nationality": "origin", "language": "origin", "gender": "gender_sexuality", "sexuality": "gender_sexuality",
          "class_economic": "economic", "age": "other_social", "disability": "other_social", "religion": "other_social", "appearance_other": "other_social", "political": "political"}
FAMILIES = [("origin", "Race, origin, and language"), ("gender_sexuality", "Gender and sexuality"), ("economic", "Economic"),
            ("other_social", "Age, disability, and other social"), ("political", "Political")]
IDENTITY_BASIS = {"ethnicity_nationality", "religion", "gender", "sexuality", "race", "language"}
r2 = lambda x: round(float(x), 2)

vocab = pd.read_csv(REF / "dimension_label_vocabulary.csv", keep_default_na=False)
CANON = {r.raw_label.lower(): r.canonical_label for r in vocab.itertuples()}; GENERIC = {r.raw_label.lower() for r in vocab.itertuples() if str(r.generic_flag) == "True"}
IDV = {r.label: (r.identity, r.family) for r in pd.read_csv(REF / "identity_vocabulary.csv", keep_default_na=False).itertuples()}
FAMILY_OF = {}
FAMILY_BY_KIND = {"race": "Race and ethnicity", "ethnic_national": "Nationality and origin", "language": "Language", "religious": "Religion and belief", "lgbtq": "Gender and sexuality",
                  "gender": "Gender and sexuality", "age_life_stage": "Age and life stage", "class_status": "Class and occupation", "political": "Political", "other": "Other"}
CULTURAL_KINDS = {"race", "ethnic_national", "language", "religious", "lgbtq", "other"}   # what the codebook calls a cultural community; not gender, age, class
def labels(rec, k=5):
    out, seen = [], set()
    for l in rec["labels"]:
        raw = l["label"].strip(); low = raw.lower()
        if not raw or low in GENERIC: continue
        c = CANON.get(low, raw); c, fam = IDV.get(c, (c, FAMILY_BY_KIND.get(l["kind"], "Other"))); FAMILY_OF[c] = fam
        if c.lower() in seen: continue
        seen.add(c.lower()); out.append({"l": c, "k": l["kind"], "i": l["intensity"], "s": "lang" if l.get("source") == "review_language" else "desc"})
    return out[:k]

def per_identity(lab, t):
    """{identity: score} for exclusivity (the unit's targeting score, for each identity it names) and cultural identity (the label's own intensity)."""
    ids = [l for l in lab if l["s"] == "desc" and FAMILY_OF.get(l["l"]) != "Political" and l["i"] >= 2]
    return ({l["l"]: t for l in ids} if t >= 1 else {}), {l["l"]: l["i"] for l in ids if l["k"] in CULTURAL_KINDS and FAMILY_OF.get(l["l"]) not in ("Age and life stage", "Class and occupation")}

# ---------------------------------------------------------------- places
scores = [json.loads(l) for l in open(A / f"dimension_scores_places{args.suffix}.jsonl")]
inputs = {d["unit_id"]: d for d in map(json.loads, gzip.open(A / f"dimension_inputs_places{args.suffix}.jsonl.gz", "rt"))}
attr = pd.read_csv(A / "tables/google_businesses.csv", keep_default_na=False).set_index("gmap_id")
wfile = A / "sample_weights_places.json"                       # only while a sample of places is scored; absent for the full run
weight = json.load(open(wfile)) if wfile.exists() and args.suffix else {}
places, hexagg = [], collections.defaultdict(lambda: collections.Counter()); misses = collections.Counter()
# Business and venue names are shown as invented names (scripts/pseudonymize_names.py); a real name must never reach demo/data.
PSEUDO = {d["id"]: d["pseudonym"] for d in map(json.loads, open(A / "pseudonyms.jsonl"))} if (A / "pseudonyms.jsonl").exists() else None
def shown_name(uid, real):
    if PSEUDO is None: raise SystemExit("data/analysis/pseudonyms.jsonl is missing: run scripts/pseudonymize_names.py first (real names must not be published)")
    if uid not in PSEUDO: raise SystemExit(f"no invented name for {uid}: rerun scripts/pseudonymize_names.py")
    return PSEUDO[uid]
for s in scores:
    u = s["unit_id"]; a = attr.loc[u]; inp = inputs[u]; w = weight.get(u, 1.0)
    cat = a.map_group if a.map_group in PLACE_CATS else "Other"
    t = s["targeting"]; lab = labels(s); ti, ci = per_identity(lab, t["score"])
    cell = h3.latlng_to_cell(float(a.latitude), float(a.longitude), args.hex_res)
    places.append({"id": u, "n": shown_name(u, a["name"]), "lat": round(float(a.latitude), 5), "lon": round(float(a.longitude), 5), "co": a.county, "cat": cat,
                   "t": t["score"], "tb": t["basis"], "tw": t["who"][:60], "b": s["socioeconomic_barrier"]["score"], "bk": s["socioeconomic_barrier"]["kind"],
                   "c": s["cultural_identity"]["score"], "lab": lab, "ti": ti, "ci": ci,
                   "nr": int(inp["n_text_reviews"]), "hx": cell, "w": round(w, 2)})
    # ---- unwelcome: weighted reports for the hexagon this place falls in (never stored per place)
    H = hexagg[cell]
    H["places"] += 1; H["reviews"] += w * inp["n_text_reviews"]; H["reviews_raw"] += inp["n_text_reviews"]
    strata = inp.get("strata") or {}
    def rw(k):                                                  # weight of review number k, or None if it does not count as a report
        if not 1 <= k <= len(inp["shown"]): return None
        sh = inp["shown"][k - 1]
        if not inp["screened"]: return 1.0
        if not sh["picked"]: return None                         # found only among the random fill: outside the screened sample
        N, n = strata[str(sh["stars"])]; return N / n
    fam_seen, out_seen, all_seen = collections.defaultdict(set), set(), set()
    for g in s["unwelcome"]["groups"] if s["unwelcome"]["score"] >= 1 else []:
        for k in g["reviews"]:
            if rw(k) is None: misses["report_outside_screened_sample"] += 1; continue
            fam_seen[FAMILY[g["basis"]]].add(k); all_seen.add(k)
            if g["outsider"]: out_seen.add(k)
    H["reports"] += w * sum(rw(k) for k in all_seen); H["reports_raw"] += len(all_seen); H["places_with_report"] += bool(all_seen)
    H["outsider"] += w * sum(rw(k) for k in out_seen)
    for f, ks in fam_seen.items(): H["f_" + f] += w * sum(rw(k) for k in ks)

hexes = []
for cell, H in hexagg.items():
    show = H["places"] >= args.min_places and H["reviews_raw"] >= args.min_reviews
    lat, lon = h3.cell_to_latlng(cell)
    hexes.append({"id": cell, "ring": [[round(a, 5), round(b, 5)] for a, b in h3.cell_to_boundary(cell)], "lat": round(lat, 5), "lon": round(lon, 5),
                  "places": H["places"], "reviews": int(H["reviews_raw"]), "show": bool(show),
                  "rate": r2(1000 * H["reports"] / H["reviews"]) if show else None, "reports": H["reports_raw"] if show else None,
                  "outsider_share": r2(H["outsider"] / H["reports"]) if show and H["reports"] else None,
                  "fam": {f: r2(1000 * H["f_" + f] / H["reviews"]) for f, _ in FAMILIES} if show else None})
tot = collections.Counter()
for H in hexagg.values(): tot.update(H)

# ---------------------------------------------------------------- Meetup: groups, then venues
gs = {d["unit_id"]: d for d in map(json.loads, open(A / f"dimension_scores_groups{args.suffix}.jsonl"))}
# anonymised 1-2 sentence summaries of each group's description (scripts/public_descriptions.py); the raw description never goes to the site
pdesc = {d["unit_id"]: d["public_description"] for d in map(json.loads, open(A / "public_descriptions_groups.jsonl"))} if (A / "public_descriptions_groups.jsonl").exists() else {}
gattr = pd.read_csv(A / "tables/meetup_groups.csv", dtype={"group_id": str}, keep_default_na=False).set_index("group_id")
ev = pd.read_csv(A / "tables/meetup_events_slim.csv.gz", dtype={"group_id": str, "N_ID": str}, usecols=["group_id", "N_ID", "location_source", "location_quality"])
ev = ev[(ev.location_source == "clean_venue") & (ev.location_quality == "ok") & ev.group_id.isin(gs)]
vattr = pd.read_csv(A / "tables/meetup_venues.csv", dtype={"venue_key": str}, keep_default_na=False).set_index("venue_key")
DIM = {"t": "targeting", "b": "socioeconomic_barrier", "c": "cultural_identity", "p": "political_identity"}
groups = []
for u, d in gs.items():
    lab = labels(d); ti, ci = per_identity(lab, d["targeting"]["score"])
    groups.append({"id": u, "n": d["name"], "cat": gattr.loc[u].broad_category if u in gattr.index else "Other", "private": str(gattr.loc[u].isPrivate) == "True" if u in gattr.index else False,
                   **{k: d[v]["score"] for k, v in DIM.items()}, "tb": d["targeting"]["basis"], "tw": d["targeting"]["who"][:60], "bk": d["socioeconomic_barrier"]["kind"],
                   "lean": d["political_identity"]["lean"], "lab": lab, "ti": ti, "ci": ci,
                   # private groups keep their scores but their description summary is not shown
                   "pd": "" if (u in gattr.index and str(gattr.loc[u].isPrivate) == "True") else pdesc.get(u, "")})
LEANS = ["left", "right", "nonpartisan_civic"]
gix = {g["id"]: g for g in groups}
MEETUP_CATS = sorted({g["cat"] for g in groups if g["cat"] != "Other"}) + ["Other"]
# Venues that are somebody's home are left off the public map: their names and coordinates would point to a private
# residence and often name the person ("Beth's house"). Found by name, so some homes named only by an address remain.
HOME = re.compile(r"\b\w+['’]s\s+(house|home|place|pad|apartment|condo|cabin|backyard)\b|\bprivate\s+(residence|home|house)\b|\b(residence|home|house)\s+of\b|\b(my|our)\s+(place|home|house|apartment)\b", re.I)
HOME_ADDRESS = re.compile(r"^\s*\d+\s+\w+.*\b(apt|apartment|unit|#)\s*\w+", re.I)    # "1234 Elm St Apt 5": a residential unit
BUSINESS = re.compile(r"kabob|kebab|pizza|grill|cafe|café|restaurant|bar\b|pub\b|brew|tavern|museum|church|chapel|meeting house|wework|realty|fish house|pancake", re.I)
venues = []; dropped_homes = 0
for vk, sub in ev.groupby("N_ID"):
    if vk not in vattr.index: continue
    va = vattr.loc[vk]; cnt = sub.group_id.value_counts(); n = int(cnt.sum())
    if (HOME.search(str(va.venue_name)) or HOME_ADDRESS.search(str(va.venue_name))) and not BUSINESS.search(str(va.venue_name)): dropped_homes += 1; continue
    mean = {k: r2(sum(gix[g][k] * c for g, c in cnt.items()) / n) for k in DIM}
    cats = collections.Counter(); labw = collections.Counter(); lean = collections.Counter(); tiw = collections.Counter(); ciw = collections.Counter(); plw = collections.Counter()
    for g, c in cnt.items():
        cats[gix[g]["cat"]] += c
        for k, s in gix[g]["ti"].items(): tiw[k] += c * s
        for k, s in gix[g]["ci"].items(): ciw[k] += c * s
        if gix[g]["lean"] in LEANS: plw[gix[g]["lean"]] += c * gix[g]["p"]
        for l in gix[g]["lab"]: labw[l["l"]] += c * l["i"]
        if gix[g]["p"] >= 3: lean[gix[g]["lean"]] += c
    top = sorted(cnt.items(), key=lambda x: -x[1])[:3]
    venues.append({"id": vk, "n": shown_name(vk, str(va.venue_name))[:80], "lat": round(float(va.latitude), 5), "lon": round(float(va.longitude), 5), "co": va.county, "cat": cats.most_common(1)[0][0],
                   "ev": n, "ng": int(len(cnt)), **mean, "lean": lean.most_common(1)[0][0] if lean else "none",
                   "lab": [{"l": l, "i": r2(wt / n)} for l, wt in labw.most_common(3)],
                   "ti": {k: r2(x / n) for k, x in tiw.items() if x / n >= 0.05}, "ci": {k: r2(x / n) for k, x in ciw.items() if x / n >= 0.05},
                   "pl": {k: r2(x / n) for k, x in plw.items() if x / n >= 0.05}, "top": [{"id": g, "ev": int(c)} for g, c in sorted(cnt.items(), key=lambda x: -x[1])[:8]]})

one = scores[0]; g1 = next(iter(gs.values()))
label_counts = collections.Counter(l["l"] for p in places for l in p["lab"] if l["s"] == "desc" and l["i"] >= 2) + collections.Counter(l["l"] for v in venues for l in v["lab"] if l["i"] >= 1)
meta = {"generated": time.strftime("%Y-%m-%d"), "stage": "sample" if args.suffix else "full",
        "note": "LLM-generated illustrations, not validated measures." + (" Places are a stratified SAMPLE of the eligible places, with an oversample of places carrying a cultural marker." if args.suffix else ""),
        "model": one["model"], "prompt_hash_places": one["prompt_hash"], "prompt_hash_groups": g1["prompt_hash"], "window": "2017-2020",
        "counts": {"places": len(places), "places_eligible": 32411, "venues": len(venues), "groups": len(groups), "hexes": len(hexes), "hexes_shown": sum(h["show"] for h in hexes),
                   "events_street_level": int(len(ev)), "venues_dropped_as_private_homes": dropped_homes},
        "place_categories": PLACE_CATS + ["Other"], "meetup_categories": MEETUP_CATS, "unwelcome_families": [{"id": f, "label": l} for f, l in FAMILIES],
        "top_labels": [l for l, _ in label_counts.most_common(24)],
        # identities offered in the map's lists: those carried by at least 3 places or groups at 2 or more, grouped by family
        "identities": {dim: sorted(({"id": k, "family": FAMILY_OF.get(k, "Other"), "n": n} for k, n in cnt_.items() if n >= 3), key=lambda x: (x["family"], -x["n"]))
                       for dim, cnt_ in (("targeting", collections.Counter(k for x in places + groups for k in x["ti"] if x["ti"][k] >= 2)),
                                         ("cultural", collections.Counter(k for x in places + groups for k in x["ci"] if x["ci"][k] >= 2)))},
        "identity_families": ["Race and ethnicity", "Nationality and origin", "Language", "Religion and belief", "Gender and sexuality", "Age and life stage", "Class and occupation", "Other"],
        "political_leans": [{"id": "left", "label": "Left-leaning"}, {"id": "right", "label": "Right-leaning"}, {"id": "nonpartisan_civic", "label": "Civic, no side"}],
        "unwelcome": {"hex_resolution": args.hex_res, "min_places": args.min_places, "min_reviews": args.min_reviews,
                      "overall_rate_per_1000": r2(1000 * tot["reports"] / tot["reviews"]), "reports_counted": int(tot["reports_raw"]), "places_with_report": int(tot["places_with_report"]),
                      "reports_not_counted_outside_screened_sample": misses["report_outside_screened_sample"],
                      "family_rates_per_1000": {f: r2(1000 * tot["f_" + f] / tot["reviews"]) for f, _ in FAMILIES}, "outsider_share": r2(tot["outsider"] / tot["reports"])}}
OUT.mkdir(parents=True, exist_ok=True)
for name, obj in [("meta", meta), ("places", places), ("venues", venues), ("hexes", hexes), ("groups", groups)]:
    (OUT / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    print(f"{name}.json  {len(obj):,} records  {(OUT / f'{name}.json').stat().st_size / 1024:.0f} KB")
print(json.dumps(meta, indent=1))
rates = sorted(h["rate"] for h in hexes if h["show"]); print("hex rates (shown):", len(rates), "min/median/max", rates[0], rates[len(rates) // 2], rates[-1], " zero:", sum(r == 0 for r in rates))
