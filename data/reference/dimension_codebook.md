# Codebook: social and cultural dimensions of places and groups

You read text about ONE unit and score it on five dimensions. A unit is either a **Meetup group** (its own name, description, topics, and a sample of its event titles) or a **Google Maps place** (its name, category, and a selection of its reviews).

The scores describe signals in the text. They are measurements for a research study of social and cultural boundaries in the Washington, DC area. They are not judgments about whether a place or group is good or bad.

## What you are given

The input has two parts.

- **`[ABOUT]`**: facts about the unit (name, category, jurisdiction, counts). Use them to understand what the unit is. Never quote from this part.
- **`[TEXT]`**: for a group, its topics, description, and frequent event titles. For a place, numbered reviews, `R1`, `R2`, and so on. Scores must rest on this part, and every quote must come from it.

For a place, the reviews are not a random sample. The place's reviews were screened first (all of them, or for a place with many reviews a sample of 100 spread across star ratings), and reviews that seemed to say something about who the place is for, who feels unwelcome, cost or dress, cultural identity, or politics were put first. The rest are random. The `[ABOUT]` part says how many reviews the place has in total, how many were screened, and how many the screening picked for each theme. A review marked `[translated]` was written in another language; you see Google's English translation, followed by the first words of the original. Keep that in mind for every dimension except `unwelcome`: three reviews about high prices out of 20 shown and 2,000 in total is a weaker signal than three out of 20 in total. For `unwelcome`, the level says how specific the reports are, and the review numbers you list say how many there are; do not lower the level because the place has many other reviews.

## Scale

Every dimension uses the same scale:

- **0** no signal in the text
- **1** weak signal: one passing or vague remark
- **2** weak-to-moderate
- **3** moderate: a clear, specific signal, or a weak one repeated by several sources
- **4** moderate-to-strong
- **5** strong: explicit, central to what the unit is, or reported repeatedly and specifically

For a place, the score reflects the reviews taken together. One reviewer's remark is a weak signal. The same point made by several reviewers is stronger.

## Dimensions

### 1. `targeting` — aimed at a specific social group by design

How narrowly the unit is aimed at people of a particular social group.

- 0: open to anyone; no social group is named. A shared interest alone (hikers, Python programmers, wine lovers, dog owners) is NOT a social group and scores 0. A remark about who would enjoy it ("great for families", "good for business travellers", "a nice date spot") is NOT targeting and scores 0.
- 1: a group is mentioned loosely as the usual crowd ("mostly young professionals here", "a lot of students").
- 3: clearly oriented to a group, with others welcome ("for women in tech, allies welcome", "a meetup for Spanish speakers and learners").
- 5: explicitly restricted to, or exclusively for, a group ("women only", "must be 40 or older", "for Korean Americans", "members of our church").

`who`: the group it is aimed at, in a few words. Empty when the score is 0.

`basis`: what kind of group it is. Choose one:

- `ethnicity_nationality`, `religion`, `gender`, `sexuality`, `race`, `language`: an identity.
- `age_life_stage`: an age band or life stage chosen as a social identity ("20s and 30s", "singles over 50", "new moms").
- `class_occupation`: the unit is for members of a profession, employer, or class position as people ("nurses only", "for women engineers", "employees of one company", "executives"). A group about a professional subject that names the professions likely to be interested ("for designers and healthcare professionals working on healthcare design") is a shared interest and scores 0.
- `service_eligibility`: the unit is an institution that serves a defined clientele by its function, such as a school, a preschool, a seniors centre, a shelter, a veterans' clinic, a military credit union. The clientele follows from the service, not from a choice about identity.
- `none`: when the score is 0.

Score the level the same way for every basis. The basis is what tells identity targeting apart from clientele.

### 2. `unwelcome` — people report being excluded or made unwelcome

How much the text reports people being turned away, treated worse, stared at, ignored, or made to feel they do not belong **because of who they are** (race, ethnicity or nationality, religion, gender, sexuality, age, disability, language, class or income, political views, appearance).

- 0: nothing of the kind. Ordinary bad service (rude, slow, overpriced) is NOT this unless the writer ties it to who they are. Being judged for something other than a social identity is also NOT this: being suspected of shoplifting with no reason given, being asked to order or leave, a hobby or a costume, a job or a uniform. If you cannot name a social group in `groups`, the score is 0. A review that says staff were kind **despite** how the writer looked or who they are is the opposite of this and scores 0.
- 1: one vague remark ("we felt out of place").
- 2: several vague remarks, or one account where the link to identity is suggested but not stated.
- 3: one specific account of unequal treatment that the writer ties to identity.
- 4: two or three separate reviews with specific accounts (whichever groups they name).
- 5: four or more separate reviews with specific accounts, or the accounts describe a stated policy or practice.

`groups`: the social groups reported as unwelcome, one entry per group, at most 4, the group with the most reports first. Empty when the score is 0. Different reviews often name different groups (one says Black customers were ignored, another that Spanish speakers were mocked): list them separately, never merged into one entry. Each entry has:

- `group`: the people made unwelcome, as a short standard noun: "Black", "Latino", "Asian", "White", "Non-Korean", "Foreigners", "Non-English speakers", "Non-Spanish speakers", "Women", "LGBTQ", "Transgender", "Older adults", "Young adults", "Disabled", "Muslim", "Low-income", "Homeless", "Conservatives". Name the people excluded, not the people favoured: at a place said to serve only Koreans well, the group is "Non-Korean".
- `basis`: `race`, `ethnicity_nationality`, `language`, `religion`, `gender`, `sexuality`, `age`, `disability`, `class_economic` (income, class, homelessness, how well-off someone looks), `political` (political views or affiliation), or `appearance_other` (looks, body, clothing style not tied to class, or another social identity).
- `outsider`: `true` when the place belongs to a particular cultural community and the people made unwelcome are those outside it (non-Koreans at a Korean restaurant, non-Spanish speakers at a Latino salon, straight customers at a gay bar). `false` when the place serves the general public and the people made unwelcome are a social group within that public (Black customers at a department store, a disabled customer at a car dealer, foreigners at a car rental desk). When unsure, `false`.
- `reviews`: for a place, the numbers of the reviews that report it for this group (`[2, 7]` for R2 and R7). One review naming two groups is listed under both. List only reviews you can see. For a Meetup group, an empty list.

This dimension applies mostly to places. For a Meetup group, score it only if the group's own text says who is not welcome in a hostile or dismissive way; a neutral eligibility rule belongs under `targeting`.

### 3. `socioeconomic_barrier` — cost, dress, or status limits who can take part

A barrier is something that keeps people out or makes them feel they cannot take part because of money, dress, or social standing. It is not an opinion about value for money.

- 0: none, or the text says it is cheap, free, casual, or affordable. Also 0 for all of these:
  - an ordinary price opinion or complaint ("expensive for what it is", "a bit pricey", "overpriced", "expensive but worth it", "parking was $18");
  - a group that is private, invitation-only, or limited to one employer, with no cost or status element;
  - a professional or business networking rule ("one member per industry").
- 1: one remark that the place is upscale or beyond the writer's means ("out of my budget", "a special-occasion place only").
- 3: several reviews describe it as expensive or upscale as a feature of the place, or the text states a dress code, cover charge, minimum spend, or paid membership.
- 5: clearly exclusive: very expensive by many accounts, a strict dress code, paid members only, high dues, or people report being turned away over dress, appearance, or ability to pay.

`kind`: the main barrier: `price`, `dress_code`, `membership_or_fee`, `status`, `other`, or `none`. Use `membership_or_fee` only when money is involved.

### 4. `cultural_identity` — offers or expresses a specific cultural identity

How strongly the unit expresses, or gives people a sense of belonging to, a particular cultural community: ethnic or national, religious, LGBTQ, a language, a racial community, a region, a diaspora, or a distinct subculture.

- 0: none.
- 1: a cultural flavour with no community meaning (a cuisine named with no further comment).
- 3: the identity is a clear part of what the unit is (a restaurant praised as authentic and "a taste of home"; a Spanish conversation group; a yoga studio with explicit spiritual framing).
- 5: a core community institution or gathering point for that identity (a gay bar described as a community home; a Korean church; a diaspora association; a group whose purpose is celebrating a heritage).

For restaurants and shops, cuisine or product origin alone is 1 or 2. Go higher only when the text shows community, authenticity, heritage, or belonging.

### 5. `political_identity` — expresses or attracts a political leaning or cause

- 0: none. A government office, courthouse, or civic service is not political by that fact. Patriotism, a flag, the national anthem, military or veteran themes, and religious preaching are NOT political leanings by themselves and score 0.
- 1: a passing political remark.
- 3: clear issue advocacy, or a political tone that several reviewers notice.
- 5: explicitly partisan, or an organisation or venue of a political movement.

For a place, score above 1 only when two or more reviews name a party, a candidate, a movement, or a contested political issue in connection with the place itself, or when the place is itself a political body (a party office, a campaign venue, an advocacy organisation). One reviewer's political opinion is at most 1. A political event that guests happened to attend nearby, or a politician seen there, says nothing about the place and scores 0.

`lean`: `left`, `right`, `nonpartisan_civic` (civic engagement without a side), `mixed`, `other`, or `none`.

## `labels`

List the specific identities the text signals, each with its own intensity from 1 to 5. Use short, standard nouns: "LGBTQ", "Korean", "Ethiopian", "Catholic", "Muslim", "Women", "Seniors", "Young professionals", "Black", "Latino", "Spanish-speaking", "Progressive", "Conservative". At most 5 labels, strongest first. Leave the list empty when no specific identity is signalled. Do not use generic clientele words such as "Families", "Adults", "Children", "Tourists", or "Locals". List each identity once.

`kind` for each label: `ethnic_national`, `religious`, `lgbtq`, `gender`, `age_life_stage`, `language`, `race`, `class_status`, `political`, or `other`.

`source` for each label:

- `described`: the text says it about the unit.
- `review_language`: use this only when nothing in the text describes the unit that way and the only evidence is that reviews are written in that language (the `[ABOUT]` part gives the count of reviews not written in English). Use kind `language`; intensity 1 for a few such reviews, 2 when they are a large share. One or two translated reviews at a place with many reviews is not worth a label.

## `evidence`

- `enough`: the text is sufficient to judge.
- `thin`: the text is too short or too generic to judge with any confidence. Still give the scores the text supports.

## Quotes

For every dimension scored 1 or higher, `quote` is a short verbatim excerpt that best supports the score: one sentence or part of one, at most 150 characters. Empty when the score is 0. For a place, the quote comes from ONE numbered review, and `review` is that review's number (3 for R3); do not join text from two reviews, do not copy a whole review, and do not add notes, review numbers, or explanations inside the quote. For a group, `review` is 0. Never quote the `[ABOUT]` part. Never invent a quote.

## Rules

1. Score only what the text shows. Do not infer from stereotypes, from the neighbourhood, or from what such places are usually like.
2. The unit's name and category count as evidence, at a low level. A place called "Seoul Garden Korean BBQ" signals Korean at level 1 by name alone, with an empty quote.
3. Most units score 0 on most dimensions. That is expected. Do not stretch.
4. Do not copy personal names of reviewers, organisers, or staff into `who`, `groups`, labels, or quotes.
5. Do not infer an identity from a person's name, from a greeting, or from the language a group's organiser happens to use.
