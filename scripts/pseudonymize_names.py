#!/usr/bin/env python3
"""Invented names for the businesses and venues shown on the map, keeping what kind of place each is.

Business names can be privacy-sensitive on a research map, so the site shows an
invented name that keeps the kind of place and its cultural or community cues ("John's Bakery" -> "Mark's Bakery")
but not the real name. The prompt is data/reference/pseudonym_prompt.md, sent verbatim. Every invented name is checked:
it must differ from the real name and must not equal any real business or venue name in the data; failures are
regenerated. Meetup group names are not changed (they are the public titles groups chose).

  .venv/bin/python scripts/pseudonymize_names.py          # resumable
Output (gitignored, holds the real names): data/analysis/pseudonyms.jsonl  {id, kind, real, pseudonym}
build_demo_data.py then writes only the invented names into demo/data/.
"""
import hashlib, json, os, re, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]; A = ROOT / "data/analysis"; OUT = A / "pseudonyms.jsonl"
PROMPT = (ROOT / "data/reference/pseudonym_prompt.md").read_text(); PH = hashlib.sha1(PROMPT.encode()).hexdigest()[:12]
MODEL = os.environ.get("GEMINI_MODEL_FLASH", "gemini-3.8-flash"); BATCH = 40

biz = pd.read_csv(A / "tables/google_businesses.csv", keep_default_na=False).set_index("gmap_id")
ven = pd.read_csv(A / "tables/meetup_venues.csv", dtype={"venue_key": str}, keep_default_na=False).set_index("venue_key")
places = json.load(open(ROOT / "demo/data/places.json")); venues = json.load(open(ROOT / "demo/data/venues.json"))
items = [{"id": p["id"], "kind": "place", "real": biz.loc[p["id"]]["name"],
          "what": f'{biz.loc[p["id"]].primary_category}' + (f' ({biz.loc[p["id"]].cultural_marker})' if biz.loc[p["id"]].cultural_marker else "")} for p in places]
items += [{"id": v["id"], "kind": "venue", "real": str(ven.loc[v["id"]].venue_name) if v["id"] in ven.index else v["n"], "what": "a venue where Meetup groups met (judge the kind of place from its name)"} for v in venues]
REAL = {re.sub(r"\W+", " ", n).strip().lower() for n in list(biz["name"]) + list(ven["venue_name"].astype(str))}
prev = [json.loads(l) for l in OUT.open()] if OUT.exists() else []
todo_ids = None   # set after the checks are defined (below)

client = genai.Client(vertexai=True, project=os.environ["GEMINI_PROJECT"], location="global", http_options=types.HttpOptions(timeout=180_000))
S = types.Schema
CFG = types.GenerateContentConfig(system_instruction=PROMPT, temperature=0.4, response_mime_type="application/json",
    response_schema=S(type="ARRAY", items=S(type="OBJECT", required=["id", "pseudonym"], properties={"id": S(type="STRING"), "pseudonym": S(type="STRING")})),
    thinking_config=types.ThinkingConfig(thinking_level="low"))
norm = lambda s: re.sub(r"\W+", " ", s).strip().lower()
# A word of the real name is distinctive when it is rare among all real business and venue names (e.g. "Schmick",
# "Piquette"); common words that describe the kind of place ("Seafood", "Dental", "Library", "Korean") may stay.
from collections import Counter
WORDFREQ = Counter(w for n in REAL for w in set(n.split()))
# Distinctive real names (with a rare word, 8+ characters): an invented name must not contain one as a phrase,
# or a reader could attach one place's scores to a different real business.
DISTINCT = {n for n in REAL if len(n) >= 8 and any(len(w) > 2 and WORDFREQ[w] < 30 for w in n.split())}
def contains_real(pseudo, own):
    w = norm(pseudo).split()
    return any(" ".join(w[a:b]) in DISTINCT and " ".join(w[a:b]) != norm(own) for a in range(len(w)) for b in range(a + 1, min(len(w), a + 8) + 1))
def ok(item, pseudo):
    if not pseudo or "#" in pseudo or norm(pseudo) == norm(item["real"]) or norm(pseudo) in REAL or contains_real(pseudo, item["real"]): return False
    rare = {w for w in norm(item["real"]).split() if len(w) > 2 and WORDFREQ[w] < 30}
    return not (rare & set(norm(pseudo).split()))
def ask(batch, extra=""):
    body = "\n".join(f'{i["id"]} | {i["real"]} | {i["what"]}' for i in batch)
    for attempt in range(5):
        try:
            r = client.models.generate_content(model=MODEL, config=CFG, contents=extra + "id | real name | kind of place\n" + body)
            return {d["id"]: d["pseudonym"].strip() for d in json.loads(r.text)}
        except Exception as ex:
            err = ex; time.sleep(2 * (attempt + 1) ** 2)
    raise err
def work(batch):
    got = ask(batch); res = []
    for i in batch:
        p = got.get(i["id"], "")
        for retry in range(3):
            if ok(i, p): break
            rare = sorted({w for w in norm(i["real"]).split() if len(w) > 2 and WORDFREQ[w] < 30})
            p = ask([i], "The previous invented name was not acceptable: it repeated the real name, matched a real business, or kept one of these words, which must not appear: "
                         + ", ".join(rare or ["(none)"]) + ". Keep the kind of place, the language, and any cultural cue; change the rest.\n").get(i["id"], "")
        res.append({**{k: i[k] for k in ("id", "kind", "real")}, "pseudonym": p if ok(i, p) else ("A " + i['what'].split(' (')[0].lower() if i["kind"] == "place" else "An event venue"), "fallback": not ok(i, p),
                    "model": MODEL, "prompt_hash": PH})
    return res
by_id = {i["id"]: i for i in items}
is_fallback = lambda r: r.get("fallback") or r["pseudonym"] == "An event venue" or (r["id"] in by_id and r["pseudonym"] == "A " + by_id[r["id"]]["what"].split(" (")[0].lower())
keep = [r for r in prev if r["id"] in by_id and ok(by_id[r["id"]], r["pseudonym"]) and not is_fallback(r)]
OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))
done = {r["id"] for r in keep}; todo = [i for i in items if i["id"] not in done]
print(f"{len(items):,} names; {len(done):,} kept; {len(todo):,} to (re)generate")
batches = [todo[k:k + BATCH] for k in range(0, len(todo), BATCH)]
with OUT.open("a") as f, ThreadPoolExecutor(12) as pool:
    for n, res in enumerate(pool.map(work, batches), 1):
        for r in res: f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if n % 20 == 0: print(f"  {n}/{len(batches)} batches")
rows = [json.loads(l) for l in OUT.open()]
print(f"{len(rows):,} invented names; generic fallbacks used: {sum(bool(r.get('fallback')) for r in rows)}; equal to a real name: {sum(norm(r['pseudonym']) in REAL for r in rows)}")
