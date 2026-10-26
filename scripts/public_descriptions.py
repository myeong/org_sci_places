#!/usr/bin/env python3
"""Write a short public summary of each Meetup group's description, for the map website.

The site shows group descriptions in pop-ups. Raw descriptions often carry organisers' names, phone numbers, emails,
addresses, and prices, so the site shows a 1-2 sentence neutral summary instead.
The prompt is data/reference/public_description_prompt.md, sent verbatim. After the run, every summary is scanned for
emails, phone numbers, links, street addresses, and dollar amounts; flagged summaries are listed for review.

  python scripts/public_descriptions.py              # all groups in dimension_inputs_groups.jsonl.gz, resumable
  python scripts/public_descriptions.py --suffix _x  # reads dimension_inputs_groups_x.jsonl.gz
Output (gitignored): data/analysis/public_descriptions_groups.jsonl  {unit_id, name, public_description, model, prompt_hash}
"""
import argparse, gzip, hashlib, json, os, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]; A = ROOT / "data/analysis"
PROMPT = (ROOT / "data/reference/public_description_prompt.md").read_text(); PH = hashlib.sha1(PROMPT.encode()).hexdigest()[:12]
MODEL = os.environ.get("GEMINI_MODEL_FLASH", "gemini-3.8-flash"); OUT = A / "public_descriptions_groups.jsonl"
ap = argparse.ArgumentParser(); ap.add_argument("--suffix", default=""); args = ap.parse_args()
units = [json.loads(l) for l in gzip.open(A / f"dimension_inputs_groups{args.suffix}.jsonl.gz", "rt")]
done = {json.loads(l)["unit_id"] for l in OUT.open()} if OUT.exists() else set()
todo = [u for u in units if u["unit_id"] not in done]
client = genai.Client(vertexai=True, project=os.environ["GEMINI_PROJECT"], location="global", http_options=types.HttpOptions(timeout=120_000))
S = types.Schema
CFG = types.GenerateContentConfig(system_instruction=PROMPT, temperature=0, response_mime_type="application/json",
                                  response_schema=S(type="OBJECT", required=["public_description"], properties={"public_description": S(type="STRING", max_length=320)}),
                                  thinking_config=types.ThinkingConfig(thinking_level="low"))
def text_of(u):   # the group's own text, without the "[ABOUT]" lines on where it is based
    t = u["text"]; about, body = t.split("[TEXT]\n", 1)
    name = re.search(r"Name: (.*)", about).group(1); cat = re.search(r"Meetup category: (.*)", about).group(1)
    return f"Name: {name}\nMeetup category: {cat}\n{body}"
def work(u):
    for attempt in range(5):
        try:
            r = client.models.generate_content(model=MODEL, config=CFG, contents=text_of(u)); um = r.usage_metadata
            return u, json.loads(r.text)["public_description"].strip(), (um.prompt_token_count or 0, um.candidates_token_count or 0)
        except Exception as ex:
            err = f"{type(ex).__name__}: {str(ex)[:120]}"; time.sleep(2 * (attempt + 1) ** 2)
    return u, None, err
tin = tout = 0; fails = []
with OUT.open("a") as f, ThreadPoolExecutor(16) as pool:
    for u, d, info in (fut.result() for fut in as_completed([pool.submit(work, u) for u in todo])):
        if d is None: fails.append((u["unit_id"], info)); continue
        tin += info[0]; tout += info[1]
        f.write(json.dumps({"unit_id": u["unit_id"], "name": u["name"], "public_description": d, "model": MODEL, "prompt_hash": PH}) + "\n")
print(f"{len(todo) - len(fails):,} written, {len(fails)} failed; {tin/1e6:.2f}M in / {tout/1e6:.2f}M out tokens")

# privacy scan of everything in the file
PAT = {"email": r"[\w.+-]+@[\w-]+\.\w+", "phone": r"\(?\b\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b", "link": r"https?://|www\.|\.com\b|\.org\b",
       "address": r"\b\d{2,5}\s+\w+(\s\w+)?\s(St|Street|Ave|Avenue|Rd|Road|Blvd|Pike|Dr|Drive|Ln|Lane|Way|Pl|Ct)\b", "money": r"\$\s?\d"}
rows = [json.loads(l) for l in OUT.open()]; flagged = [(r["name"], k, r["public_description"]) for r in rows for k, p in PAT.items() if re.search(p, r["public_description"], re.I)]
print(f"{len(rows):,} summaries; flagged by the privacy scan: {len(flagged)}")
for x in flagged[:20]: print("  ", x)
