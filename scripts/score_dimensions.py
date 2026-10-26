#!/usr/bin/env python3
"""Score Meetup groups and Google places on the social/cultural dimensions with Gemini (Vertex AI).

The instructions sent to the model are data/reference/dimension_codebook.md, verbatim.
One request per unit. Results are appended to a JSONL file, so the run can be stopped and resumed.

  .venv/bin/python scripts/score_dimensions.py groups                 # all groups
  .venv/bin/python scripts/score_dimensions.py places --pilot 1500    # stratified pilot sample of places
  .venv/bin/python scripts/score_dimensions.py places                 # all eligible places
  .venv/bin/python scripts/score_dimensions.py places --suffix _repilot   # reads dimension_inputs_places_repilot, writes dimension_scores_places_repilot
Options: --workers N (default 16), --model ID (default gemini-3.8-flash), --limit N (first N pending units)

Outputs (data/analysis/, gitignored): dimension_scores_{groups,places}<suffix>.jsonl
Tracked: data/reference/dimension_scores_meta.json (model, prompt hash, dates, token use)
Auth: gcloud auth application-default login.  Project: set GEMINI_PROJECT to your Google Cloud project.
"""
import argparse, gzip, hashlib, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]; A = ROOT / "data/analysis"; REF = ROOT / "data/reference"
ap = argparse.ArgumentParser(); ap.add_argument("kind", choices=["groups", "places"])
ap.add_argument("--pilot", type=int); ap.add_argument("--limit", type=int); ap.add_argument("--workers", type=int, default=16)
ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL_FLASH", "gemini-3.8-flash")); ap.add_argument("--out"); ap.add_argument("--suffix", default="")
args = ap.parse_args()
PROJECT = os.environ["GEMINI_PROJECT"]
OUT = Path(args.out) if args.out else A / f"dimension_scores_{args.kind}{args.suffix}.jsonl"
CODEBOOK = (REF / "dimension_codebook.md").read_text()
PROMPT_HASH = hashlib.sha1(CODEBOOK.encode()).hexdigest()[:12]

S = types.Schema
score = S(type="INTEGER", minimum=0, maximum=5)
quote = S(type="STRING", max_length=160, description="Verbatim excerpt of at most 150 characters from ONE review or from the group's text; empty if score is 0.")
review = S(type="INTEGER", minimum=0, description="Number of the review the quote is taken from (3 for R3); 0 for a group or when there is no quote.")
def dim(extra=None):
    props = {"score": score, "quote": quote, "review": review}; props.update(extra or {})
    return S(type="OBJECT", required=list(props), properties=props)
SCHEMA = S(type="OBJECT", required=["evidence", "targeting", "unwelcome", "socioeconomic_barrier", "cultural_identity", "political_identity", "labels"], properties={
    "evidence": S(type="STRING", enum=["enough", "thin"]),
    "targeting": dim({"who": S(type="STRING"), "basis": S(type="STRING", enum=["ethnicity_nationality", "religion", "gender", "sexuality", "race", "language", "age_life_stage", "class_occupation", "service_eligibility", "none"])}),
    "unwelcome": dim({"groups": S(type="ARRAY", max_items=4, items=S(type="OBJECT", required=["group", "basis", "outsider", "reviews"], properties={
        "group": S(type="STRING"), "outsider": S(type="BOOLEAN"), "reviews": S(type="ARRAY", max_items=20, items=S(type="INTEGER", minimum=1, maximum=20)),
        "basis": S(type="STRING", enum=["race", "ethnicity_nationality", "language", "religion", "gender", "sexuality", "age", "disability", "class_economic", "political", "appearance_other"])}))}),
    "socioeconomic_barrier": dim({"kind": S(type="STRING", enum=["price", "dress_code", "membership_or_fee", "status", "other", "none"])}),
    "cultural_identity": dim(),
    "political_identity": dim({"lean": S(type="STRING", enum=["left", "right", "nonpartisan_civic", "mixed", "other", "none"])}),
    "labels": S(type="ARRAY", max_items=5, items=S(type="OBJECT", required=["label", "kind", "source", "intensity"], properties={
        "label": S(type="STRING"),
        "kind": S(type="STRING", enum=["ethnic_national", "religious", "lgbtq", "gender", "age_life_stage", "language", "race", "class_status", "political", "other"]),
        "source": S(type="STRING", enum=["described", "review_language"]),
        "intensity": S(type="INTEGER", minimum=1, maximum=5)})),
})
client = genai.Client(vertexai=True, project=PROJECT, location="global", http_options=types.HttpOptions(timeout=120_000))
CFG = types.GenerateContentConfig(system_instruction=CODEBOOK, temperature=0, response_mime_type="application/json", response_schema=SCHEMA,
                                  thinking_config=types.ThinkingConfig(thinking_level="low"))

# ---- units to score
units = [json.loads(l) for l in gzip.open(A / f"dimension_inputs_{args.kind}{args.suffix}.jsonl.gz", "rt")]
if args.kind == "places" and args.pilot:
    # Stratified pilot: proportional across high-level categories with a floor of 40 per category,
    # plus 20% drawn from places whose Google category carries a cultural marker, so the pilot has signal to judge.
    b = pd.read_csv(A / "tables/google_businesses.csv", keep_default_na=False).set_index("gmap_id")
    df = pd.DataFrame({"unit_id": [u["unit_id"] for u in units]}).join(b[["high_level", "cultural_marker"]], on="unit_id")
    n_mark = args.pilot // 5; n_main = args.pilot - n_mark
    quota = (df.high_level.value_counts(normalize=True) * n_main).round().astype(int).clip(lower=40)
    main = pd.concat([d.sample(min(len(d), quota[h]), random_state=7) for h, d in df.groupby("high_level")])
    rest = df[~df.unit_id.isin(main.unit_id) & (df.cultural_marker != "")]
    pick = set(main.unit_id) | set(rest.sample(min(len(rest), n_mark), random_state=7).unit_id)
    units = [u for u in units if u["unit_id"] in pick]
done = set()
if OUT.exists():
    done = {json.loads(l)["unit_id"] for l in OUT.open() if l.strip()}
todo = [u for u in units if u["unit_id"] not in done]
if args.limit: todo = todo[: args.limit]
print(f"{args.kind}: {len(units):,} selected, {len(done & {u['unit_id'] for u in units}):,} already scored, {len(todo):,} to do; model {args.model}; prompt {PROMPT_HASH}", flush=True)

lock = threading.Lock(); tok = {"in": 0, "out": 0, "thought": 0}; fails = []
def work(u):
    last = None
    for attempt in range(5):
        try:
            r = client.models.generate_content(model=args.model, config=CFG, contents=u["text"])
            res = json.loads(r.text); um = r.usage_metadata
            return u, res, (um.prompt_token_count or 0, um.candidates_token_count or 0, getattr(um, "thoughts_token_count", 0) or 0)
        except Exception as ex:
            last = f"{type(ex).__name__}: {str(ex)[:150]}"; time.sleep(2 * (attempt + 1) ** 2)
    return u, None, last

t0 = time.time()
with OUT.open("a") as fout, ThreadPoolExecutor(args.workers) as pool:
    for i, fut in enumerate(as_completed([pool.submit(work, u) for u in todo]), 1):
        u, res, info = fut.result()
        if res is None: fails.append((u["unit_id"], info))
        else:
            with lock:
                tok["in"] += info[0]; tok["out"] += info[1]; tok["thought"] += info[2]
                fout.write(json.dumps({"unit_id": u["unit_id"], "unit_type": u["unit_type"], "name": u["name"], **res,
                                       "model": args.model, "prompt_hash": PROMPT_HASH, "scored_on": time.strftime("%Y-%m-%d")}) + "\n"); fout.flush()
        if i % 250 == 0 or i == len(todo):
            print(f"  {i:,}/{len(todo):,}  {time.time()-t0:.0f}s  in {tok['in']/1e6:.2f}M  out {tok['out']/1e6:.2f}M  thought {tok['thought']/1e6:.2f}M  failed {len(fails)}", flush=True)

meta_p = REF / "dimension_scores_meta.json"
meta = json.loads(meta_p.read_text()) if meta_p.exists() else {"runs": []}
meta.update({"provider": "Vertex AI (google-genai SDK)", "project": PROJECT, "codebook": "data/reference/dimension_codebook.md",
             "request": "system instruction = codebook verbatim; user message = the unit's text from dimension_inputs_*.jsonl.gz; one unit per request; temperature 0; thinking_level low; JSON schema enforced"})
meta["runs"].append({"kind": args.kind, "date": time.strftime("%Y-%m-%d %H:%M"), "model": args.model, "prompt_hash": PROMPT_HASH, "pilot": args.pilot, "suffix": args.suffix,
                     "scored": len(todo) - len(fails), "failed": len(fails), "seconds": round(time.time() - t0),
                     "input_tokens": tok["in"], "output_tokens": tok["out"], "thought_tokens": tok["thought"]})
meta_p.write_text(json.dumps(meta, indent=2))
if fails: print("failed examples:", fails[:3])
print(f"done: {len(todo)-len(fails):,} scored, {len(fails)} failed, total in file {len(done)+len(todo)-len(fails):,}")
