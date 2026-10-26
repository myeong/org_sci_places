# Mapping social and cultural boundaries with AI

**Live demo: https://org-sci-boundaries.web.app**

Maps usually show *space*: streets, parks, county lines. This project maps *place*: who a location is for, whose culture it expresses, what it takes to get in, and who feels they do not belong there. None of that is on an official map. It lives in what people write about places, so we use an AI language model to read that writing and turn it into scores that can be mapped.

The demo covers the Washington, DC area (DC and the surrounding counties in Maryland and Virginia) from 2017 to 2020, using two kinds of text:

- **Google reviews** of local businesses and institutions, and
- **Meetup** group descriptions, the pages that local clubs and communities write about themselves.

This repository holds everything needed to build the demo: the website, the scripts that score the text, the plain-language instructions the AI model follows, and the scores shown on the map.

## What the map shows

Pick one dimension in the left panel and the map colours every place and group by it, on a scale from **0** (no sign of it) to **5** (strong and explicit).

| Dimension | The question it answers | Example |
|---|---|---|
| Exclusivity by design | Who is this place or group built for? | A cycling group whose description says "You must identify as a woman to be part of this closed group" scores 5 |
| Cultural identity | Whose heritage or community does it express? | A bar that one reviewer calls "DC's gay neighborhood living room" scores 5 for LGBTQ |
| Political leaning | Which political cause does it advance? (Meetup groups only) | A regional political party's Meetup group scores 5 |
| Socio-economic barrier | What does it cost, in money, dress, or status, to take part? | A steakhouse where reviewers say to "come dressed to wow" scores 3 |
| Unwelcomeness | Who reports being treated worse because of who they are? | Shown only as a rate per 1,000 reviews for areas, never for a single place |

You can also choose a specific group or community within a dimension (for example "aimed at women" or "Korean"), and use **Combined criteria** to find the places that meet several conditions at once. Clicking a place shows its score, what that level means, and the details behind it. The **About** page on the site explains the ideas in more depth.

## How it works

1. **Collect the text.** For each Meetup group: its description, topics, and event titles. For each Google place: its reviews.
2. **Pick the reviews worth reading.** A short AI prompt reads up to 100 reviews per place, spread across star ratings, and flags the few that mention who the place is for, cost or dress, cultural identity, politics, or people being made to feel unwelcome. Up to 20 reviews per place, the flagged ones first, go to the next step.
3. **Score.** The AI model reads the text against a written codebook ([`data/reference/dimension_codebook.md`](data/reference/dimension_codebook.md)) that defines each dimension and what each level means. For every score above 0 it must quote the passage that supports it.
4. **Map.** Places are shown at their addresses. Meetup groups are shown at the venues where they met. Unwelcomeness is pooled into hexagonal areas of about 5 km².

Because the codebook is plain text, anyone can read exactly what was measured, and change it to measure something else.

## What is in this repository

```
demo/public/        the website (HTML, CSS, JavaScript; no build step)
demo/data/          the scores shown on the map (no review text)
demo/firebase.json  hosting settings for Firebase
demo/firestore.rules  who may read and write the map data
data/reference/     the codebook and other instructions given to the AI model, and the identity vocabulary
scripts/            the steps that turn text into scores and scores into the map
data/analysis/      where the input files go (empty here; see below)
```

## Rebuilding the demo

You need Python 3.11 or later, a Google Cloud project with the Vertex AI API enabled (for the Gemini model), and a Firebase project (to host the site and store the map data).

```bash
pip install -r requirements.txt
gcloud auth application-default login       # lets the scripts call Gemini and write to Firestore
export GEMINI_PROJECT=your-google-cloud-project
export FIREBASE_PROJECT=your-firebase-project
```

**Input files.** The scripts read these files from `data/analysis/`. They are not included, because the source datasets cannot be redistributed (see below).

| File | Contents |
|---|---|
| `google_businesses_2017_2020.jsonl.gz` | one line per place: id, name, address, coordinates, categories, county |
| `google_reviews_2017_2020.jsonl.gz` | one line per review: place id, review id, rating, date, text |
| `meetup_groups_2017_2020.jsonl.gz` | one line per group: id, name, category, topics, description, city, county |
| `meetup_events_2017_2020.jsonl.gz` | one line per event: group id, title, venue, date |
| `tables/google_businesses.csv`, `tables/meetup_groups.csv`, `tables/meetup_events_slim.csv.gz`, `tables/meetup_venues.csv` | compact tables of the same records, with the folded categories used for map colours |

**Steps.**

```bash
python scripts/screen_reviews.py            # 1. flag the reviews worth reading
python scripts/build_dimension_inputs.py    # 2. assemble the text the model reads for each group and place
python scripts/score_dimensions.py groups   # 3. score the Meetup groups
python scripts/score_dimensions.py places   #    and the Google places
python scripts/public_descriptions.py       # 4. write short, anonymised summaries of the group descriptions
python scripts/build_demo_data.py           # 5. turn the scores into the map files in demo/data/
python scripts/upload_firestore.py          # 6. store the map files in Firestore
cd demo && firebase deploy --only hosting,firestore:rules --project "$FIREBASE_PROJECT"   # 7. publish the site
```

Every scoring step can be stopped and resumed. As a guide to cost, in our runs the model used about 50 input tokens per review screened, about 5,600 input and 280 output tokens per place scored, and about 4,600 input and 280 output tokens per Meetup group. Before using the site with your own Firebase project, change `firebaseConfig` in `demo/public/js/config.js` to your project's web settings.

## Data and privacy

- **Sources.** Google reviews come from the Google Local dataset of the McAuley Lab at UC San Diego; please cite their work if you use it. Meetup data were collected by our research lab. Neither dataset is redistributed here.
- **No review text on the site.** The map shows scores and short descriptions only. Pop-ups for places explain the score without quoting any review.
- **Unwelcomeness is shown for areas only**, as reports per 1,000 reviews, because a single anonymous review should not brand a business.
- **Group descriptions are summarised.** The site shows a one- or two-sentence summary of each Meetup group's description, written by the AI model with names of people, contact details, addresses, and prices removed. Descriptions of private groups are not shown.
- **Private homes are left out.** Meetup venues whose names indicate someone's home are excluded.

## Limitations

- The scores are illustrations from an AI model. The scoring rules were calibrated on cases coded by the authors and the outputs were checked on samples by other AI models, but the scores have not yet been validated against trained human coders.
- The live demo scores a sample of 1,648 of the 32,411 eligible Google places, chosen to include more places with a cultural focus; it scores all 2,224 Meetup groups based in the region.
- Reviews and group pages speak for the people who write them. People who never visited, or never wrote, are not on the map.
- Scores of 1 rest on a single passing remark and can change from one run to the next; the map starts at 2 by default.

## Author

Myeong Lee
