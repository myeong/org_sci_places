#!/usr/bin/env python3
"""Screen ALL text reviews of a place with Gemini to find the few that say something about social boundaries.

Step 1 of screen-then-score. A random sample of 12 reviews made rare reports, above all
`unwelcome`, a matter of luck. Here every text review of a place is read once with a short prompt
(data/reference/review_screening_prompt.md, sent verbatim) that only picks candidates and tags them.
build_dimension_inputs.py then puts the picked reviews first among the up to 20 the scoring model reads.

Places with K (20) or fewer text reviews are not screened: all their reviews go to scoring.
Places with more than CAP (100) text reviews are not read in full (to cut cost): CAP reviews are
drawn, spread equally across the star ratings. Reports of being unwelcome sit mostly in 1- and 2-star reviews, which
are about 15% of all reviews, so the equal spread finds far more of them than a random draw of the same size.
Each record keeps, per star rating, how many text reviews the place has and how many were screened, so any rate
computed from the picks can be weighted back to all of the place's reviews.

  .venv/bin/python scripts/screen_reviews.py --ids data/analysis/repilot_ids_places.txt   # a subset
  .venv/bin/python scripts/screen_reviews.py                                              # all eligible places
Options: --workers N (default 16), --model ID (default gemini-3.8-flash), --batch N reviews per request (default 100)

Output (data/analysis/, gitignored): review_screen.jsonl, one line per place, resumable.
Tracked: data/reference/review_screen_meta.json (model, prompt hash, dates, token use)
"""
import argparse, collections, gzip, hashlib, json, os, re, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]; A = ROOT / "data/analysis"; REF = ROOT / "data/reference"
SEED, K, MIN_TEXT, MAX_CHARS, CAP = "orgsci-2026", 20, 10, 500, 100
TAGS = ["unwelcome", "barrier", "targeting", "cultural", "political"]
ap = argparse.ArgumentParser(); ap.add_argument("--ids"); ap.add_argument("--workers", type=int, default=16); ap.add_argument("--batch", type=int, default=100)
ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL_FLASH", "gemini-3.8-flash")); ap.add_argument("--out", default=str(A / "review_screen.jsonl"))
args = ap.parse_args()
PROJECT = os.environ["GEMINI_PROJECT"]
PROMPT = (REF / "review_screening_prompt.md").read_text(); PROMPT_HASH = hashlib.sha1(PROMPT.encode()).hexdigest()[:12]
OUT = Path(args.out)

def prio(review_id):
    return int(hashlib.sha1((SEED + review_id).encode()).hexdigest()[:12], 16)

def show(text):
    """Review text as the models see it: Google's translation only, markup-free, cut to MAX_CHARS."""
    m = re.match(r"\(Translated by Google\)\s*(.*?)\s*\(Original\)\s*(.*)", text, re.S)
    t = re.sub(r"\s+", " ", m.group(1) if m else text).strip()
    t = t if len(t) <= MAX_CHARS else t[:MAX_CHARS].rsplit(" ", 1)[0] + " ..."
    return ("[translated] " if m else "") + t

want = {l.strip() for l in open(args.ids)} if args.ids else None
done = {json.loads(l)["unit_id"] for l in OUT.open() if l.strip()} if OUT.exists() else set()
revs = collections.defaultdict(list)
with gzip.open(A / "google_reviews_2017_2020.jsonl.gz", "rt") as f:
    for line in f:
        d = json.loads(line)
        if d["text"] and (want is None or d["gmap_id"] in want) and d["gmap_id"] not in done:
            revs[d["gmap_id"]].append((prio(d["review_id"]), d["review_id"], d["rating"], show(d["text"])))
def star(rt): return int(rt) if rt == rt and rt is not None else 0          # 0 = no rating recorded

def stratified(rs):
    """Up to CAP reviews, spread equally across star ratings; a rating with too few reviews passes its share on to the others."""
    by = collections.defaultdict(list)
    for r in rs: by[star(r[2])].append(r)                                   # rs is already in random (priority) order
    take = {s: 0 for s in by}; left = min(CAP, len(rs)); live = list(by)
    while left > 0 and live:
        q = max(1, left // len(live)); nxt = []
        for s in live:
            a = min(q, len(by[s]) - take[s], left); take[s] += a; left -= a
            if take[s] < len(by[s]): nxt.append(s)
        live = nxt
    return sorted(r for s in by for r in by[s][:take[s]]), {str(s): [len(by[s]), take[s]] for s in sorted(by)}

strata = {}; todo = {}
for g, r in revs.items():
    if len(r) > K and len(r) >= MIN_TEXT: todo[g], strata[g] = stratified(sorted(r))
n_rev = sum(len(r) for r in todo.values())
print(f"places to screen: {len(todo):,} ({n_rev:,} text reviews); already done {len(done):,}; skipped (<= {K} text reviews) {len(revs) - len(todo):,}; model {args.model}; prompt {PROMPT_HASH}", flush=True)

S = types.Schema
SCHEMA = S(type="OBJECT", required=["picks"], properties={"picks": S(type="ARRAY", items=S(type="OBJECT", required=["n", "tags"], properties={
    "n": S(type="INTEGER"), "tags": S(type="ARRAY", items=S(type="STRING", enum=TAGS))}))})
client = genai.Client(vertexai=True, project=PROJECT, location="global", http_options=types.HttpOptions(timeout=120_000))
CFG = types.GenerateContentConfig(system_instruction=PROMPT, temperature=0, response_mime_type="application/json", response_schema=SCHEMA,
                                  thinking_config=types.ThinkingConfig(thinking_level="low"))

def work(gid):
    rs = todo[gid]; flagged = []; tin = tout = 0
    for s in range(0, len(rs), args.batch):
        chunk = rs[s:s + args.batch]
        body = "\n".join(f"{i}. [{int(rt) if rt == rt and rt is not None else '?'} stars] {tx}" for i, (_, _, rt, tx) in enumerate(chunk, 1))
        last = None
        for attempt in range(5):
            try:
                r = client.models.generate_content(model=args.model, config=CFG, contents=body)
                picks = json.loads(r.text)["picks"]; um = r.usage_metadata
                tin += um.prompt_token_count or 0; tout += (um.candidates_token_count or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
                break
            except Exception as ex:
                last = f"{type(ex).__name__}: {str(ex)[:150]}"; time.sleep(2 * (attempt + 1) ** 2)
        else:
            return gid, None, last
        for p in picks:
            if 1 <= p["n"] <= len(chunk) and p["tags"]:
                flagged.append({"review_id": chunk[p["n"] - 1][1], "stars": star(chunk[p["n"] - 1][2]), "tags": sorted(set(p["tags"]), key=TAGS.index)})
    return gid, {"unit_id": gid, "n_text": len(revs[gid]), "n_screened": len(rs), "strata": strata[gid], "flagged": flagged, "input_tokens": tin, "output_tokens": tout}, None

lock = threading.Lock(); tok = collections.Counter(); fails = []; t0 = time.time()
with OUT.open("a") as fout, ThreadPoolExecutor(args.workers) as pool:
    for i, fut in enumerate(as_completed([pool.submit(work, g) for g in todo]), 1):
        gid, rec, err = fut.result()
        if rec is None: fails.append((gid, err))
        else:
            with lock:
                tok["in"] += rec["input_tokens"]; tok["out"] += rec["output_tokens"]; tok["flagged"] += len(rec["flagged"]); tok["reviews"] += rec["n_screened"]
                fout.write(json.dumps({**rec, "model": args.model, "prompt_hash": PROMPT_HASH, "screened_on": time.strftime("%Y-%m-%d")}) + "\n"); fout.flush()
        if i % 100 == 0 or i == len(todo):
            print(f"  {i:,}/{len(todo):,}  {time.time()-t0:.0f}s  in {tok['in']/1e6:.2f}M  out {tok['out']/1e6:.2f}M  flagged {tok['flagged']:,} of {tok['reviews']:,}  failed {len(fails)}", flush=True)

meta_p = REF / "review_screen_meta.json"
meta = json.loads(meta_p.read_text()) if meta_p.exists() else {"runs": []}
meta.update({"provider": "Vertex AI (google-genai SDK)", "project": PROJECT, "prompt": "data/reference/review_screening_prompt.md",
             "request": f"system instruction = screening prompt verbatim; user message = up to {args.batch} numbered reviews of one place, each cut to {MAX_CHARS} characters, translations without the original; places with more than {CAP} text reviews: {CAP} drawn, spread equally across star ratings; temperature 0; thinking_level low; JSON schema enforced"})
meta["runs"].append({"date": time.strftime("%Y-%m-%d %H:%M"), "model": args.model, "prompt_hash": PROMPT_HASH, "subset": bool(args.ids), "places": len(todo) - len(fails),
                     "failed": len(fails), "reviews_screened": tok["reviews"], "reviews_flagged": tok["flagged"], "seconds": round(time.time() - t0),
                     "input_tokens": tok["in"], "output_tokens_incl_thought": tok["out"]})
meta_p.write_text(json.dumps(meta, indent=2))
if fails: print("failed examples:", fails[:3])
print(f"done: {len(todo)-len(fails):,} places screened, {len(fails)} failed")
