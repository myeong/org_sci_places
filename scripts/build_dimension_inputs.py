#!/usr/bin/env python3
"""Build the text that the LLM reads for each Meetup group and each Google place.

Every input has two parts, as the codebook describes: [ABOUT] (facts; never quoted) and [TEXT] (what is scored).

Groups: every group in the 2017-2020 analysis files that is based in the region (groups with no county in the
        region on file are dropped). [ABOUT] name, Meetup category, where it is based, private or not.
        [TEXT] topics, description (markup stripped, cut to 2,500 characters), up to 12 of its most frequent event titles.
Places: every place with at least MIN_TEXT text reviews in the window. Up to K reviews, each cut to MAX_CHARS:
        first the reviews picked by the screening step (scripts/screen_reviews.py): up to UNWELCOME_FIRST picked for
        `unwelcome`, the rarest and most consequential theme, then one at a time across the screening tags so no
        theme crowds out another; then random reviews (fixed seed; reviews of MIN_LEN+
        characters first) to fill up. A place with more than K text reviews and no screening record is skipped.
        Reviewer names and ids are not included. Reviews written in another language are shown in Google's
        translation followed by the first words of the original.

Outputs (gitignored): data/analysis/dimension_inputs_groups<suffix>.jsonl.gz, dimension_inputs_places<suffix>.jsonl.gz
Run: .venv/bin/python scripts/build_dimension_inputs.py
     .venv/bin/python scripts/build_dimension_inputs.py --suffix _repilot --ids-places FILE --ids-groups FILE   # a subset
"""
import argparse, gzip, hashlib, heapq, html, json, re, collections
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]; A = ROOT / "data/analysis"
SEED, K, MIN_TEXT, MIN_LEN, MAX_CHARS, UNWELCOME_FIRST = "orgsci-2026", 20, 10, 80, 500, 10
TAGS = ["unwelcome", "barrier", "targeting", "political", "cultural"]          # order in which flagged reviews take the K places
TAG_WORDS = {"unwelcome": "people made unwelcome", "barrier": "cost, dress, or status", "targeting": "who the place is for", "political": "politics", "cultural": "cultural identity"}
ap = argparse.ArgumentParser(); ap.add_argument("--suffix", default=""); ap.add_argument("--ids-places"); ap.add_argument("--ids-groups")
ap.add_argument("--only", choices=["groups", "places"])
args = ap.parse_args()
ids = lambda p: {l.strip() for l in open(p)} if p else None
want_p, want_g = ids(args.ids_places), ids(args.ids_groups)

def clean(t, limit=None):
    t = html.unescape(re.sub(r"<[^>]+>", " ", t or ""))
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)                 # markdown images
    t = re.sub(r"\[([^\]]*)\]\((?:https?://)[^)]*\)", r"\1", t)  # markdown links -> their text
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t if not limit or len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + " ..."

# ---------------------------------------------------------------- groups
if args.only != "places":
    g = pd.read_json(A / "meetup_groups_2017_2020.jsonl.gz", lines=True, dtype={"group_id": str})
    n_all = len(g); g = g[g.group_county.notna()]
    print(f"groups based outside the region dropped: {n_all - len(g):,} of {n_all:,}")
    e = pd.read_json(A / "meetup_events_2017_2020.jsonl.gz", lines=True, dtype={"group_id": str, "event_id": str})
    titles = e.groupby("group_id").event_title.agg(lambda s: [clean(t, 100) for t in s.value_counts().index[:12]])
    n = 0
    with gzip.open(A / f"dimension_inputs_groups{args.suffix}.jsonl.gz", "wt") as out:
        for r in g.itertuples():
            if want_g is not None and r.group_id not in want_g: continue
            text = (f"[ABOUT]\nUnit: Meetup group\nName: {clean(r.name, 150)}\nMeetup category: {r.topicCategory_name}\n"
                    f"Based in: {r.city}{', ' + r.state if isinstance(r.state, str) and r.state else ''}\nPrivate group: {'yes' if r.isPrivate else 'no'}\n"
                    f"[TEXT]\nTopics: {clean(r.topics, 400)}\nDescription: {clean(r.description, 2500)}\n"
                    f"Frequent event titles: " + " | ".join(titles.get(r.group_id, [])))
            out.write(json.dumps({"unit_id": r.group_id, "unit_type": "group", "name": r.name, "text": text}) + "\n"); n += 1
    print(f"groups: {n:,}")
if args.only == "groups": raise SystemExit

# ---------------------------------------------------------------- places
def prio(review_id):                      # stable pseudo-random order, independent of file order
    return int(hashlib.sha1((SEED + review_id).encode()).hexdigest()[:12], 16)

def show(text):
    """Google's translation (if any) cut to MAX_CHARS, then the first words of the original so the language can be told."""
    m = re.match(r"\(Translated by Google\)\s*(.*?)\s*\(Original\)\s*(.*)", text, re.S)
    t = clean(m.group(1) if m else text, MAX_CHARS)
    return f'[translated] {t} (original begins: "{clean(m.group(2))[:60]}")' if m else t

screen = {}
if (A / "review_screen.jsonl").exists():
    for l in (A / "review_screen.jsonl").open():
        d = json.loads(l); screen[d["unit_id"]] = d
flag_tags = {f["review_id"]: f["tags"] for d in screen.values() for f in d["flagged"]}

n_text, n_foreign = collections.Counter(), collections.Counter()
long_h, short_h, flagged = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
with gzip.open(A / "google_reviews_2017_2020.jsonl.gz", "rt") as f:
    for line in f:
        d = json.loads(line)
        if not d["text"]: continue
        gid = d["gmap_id"]
        if want_p is not None and gid not in want_p: continue
        n_text[gid] += 1; n_foreign[gid] += d["text"].startswith("(Translated by Google)")
        item = (-prio(d["review_id"]), d["review_id"], d["rating"], d["date_local"][:4], d["text"])   # max-heap on priority keeps the K smallest
        if d["review_id"] in flag_tags: flagged[gid].append(item)
        h = long_h[gid] if len(d["text"]) >= MIN_LEN else short_h[gid]
        if len(h) < K: heapq.heappush(h, item)
        elif item > h[0]: heapq.heapreplace(h, item)

b = pd.read_json(A / "google_businesses_2017_2020.jsonl.gz", lines=True)
kept = skipped = 0
with gzip.open(A / f"dimension_inputs_places{args.suffix}.jsonl.gz", "wt") as out:
    for r in b.itertuples():
        gid = r.gmap_id
        if n_text[gid] < MIN_TEXT: continue
        if n_text[gid] > K and gid not in screen: skipped += 1; continue
        # flagged reviews, one tag at a time in TAGS order, so a place with 300 "cultural" picks still shows its one "unwelcome" pick
        by_tag = {t: sorted((it for it in flagged[gid] if t in flag_tags[it[1]]), reverse=True) for t in TAGS}
        picks = by_tag["unwelcome"][:UNWELCOME_FIRST]; seen = {it[1] for it in picks}
        while len(picks) < K and any(by_tag.values()):
            for t in TAGS:
                while by_tag[t] and by_tag[t][0][1] in seen: by_tag[t].pop(0)
                if by_tag[t] and len(picks) < K:
                    it = by_tag[t].pop(0); picks.append(it); seen.add(it[1])
        n_flag = len(picks)
        for it in sorted(long_h[gid], reverse=True) + sorted(short_h[gid], reverse=True):
            if len(picks) >= K: break
            if it[1] not in seen: picks.append(it); seen.add(it[1])
        counts = collections.Counter(t for it in flagged[gid] for t in flag_tags[it[1]])
        cats = ", ".join(r.category) if isinstance(r.category, list) else "unknown"
        if n_text[gid] > K:
            n_scr = screen[gid]["n_screened"]
            how = ((f"All {n_scr} were screened. " if n_scr >= n_text[gid] else f"{n_scr} of them were screened, spread across star ratings. ") + "Picked by the screening: " + "; ".join(f"{TAG_WORDS[t]} {counts[t]}" for t in TAGS) +
                   f". Shown below: {len(picks)} reviews, the first {n_flag} picked by the screening, the rest random.")
        else:
            how = f"All {len(picks)} are shown below."
        text = (f"[ABOUT]\nUnit: Google Maps place\nName: {clean(r.name, 150)}\nGoogle categories: {cats}\nJurisdiction: {r.county}\n"
                f"Reviews with text in 2017-2020: {n_text[gid]}, of which {n_foreign[gid]} not written in English. {how}\n[TEXT]\n" +
                "\n".join(f"R{i} [{int(rt) if rt == rt and rt is not None else '?'} stars, {yr}] {show(tx)}" for i, (_, _, rt, yr, tx) in enumerate(picks, 1)))
        out.write(json.dumps({"unit_id": gid, "unit_type": "place", "name": r.name, "n_text_reviews": n_text[gid], "n_foreign_reviews": n_foreign[gid],
                              "screened": n_text[gid] > K, "flag_counts": {t: counts[t] for t in TAGS}, "n_flagged_shown": n_flag, "n_shown": len(picks),
                              "strata": screen[gid].get("strata") if gid in screen else None, "n_screened": screen[gid]["n_screened"] if gid in screen else n_text[gid],
                              "shown": [{"review_id": it[1], "stars": int(it[2]) if it[2] == it[2] and it[2] is not None else 0, "picked": flag_tags.get(it[1], [])} for it in picks],
                              "text": text}) + "\n")
        kept += 1
print(f"places with {MIN_TEXT}+ text reviews written: {kept:,}; skipped for lack of a screening record: {skipped:,}")
