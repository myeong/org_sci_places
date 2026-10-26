# Screening prompt: which reviews are worth reading closely

You are given numbered Google Maps reviews of ONE place. Most reviews are about service, food, or quality and say nothing about social boundaries. Your task is to find the few that do. A second step will read the reviews you pick and score the place, so pick anything that could matter and leave the judging to that step. When in doubt, pick it.

Pick a review if it says something about any of these:

- `unwelcome`: the writer, or someone they saw, was turned away, treated worse, stared at, ignored, or made to feel out of place, and ties it to who they are (race, ethnicity, religion, gender, sexuality, age, disability, class, language, appearance). Also pick vague versions ("we felt out of place", "they treat people like us differently"). Ordinary rude or slow service with no such link is not this.
- `barrier`: cost, dress, or status that keeps people out: a dress code, cover charge, minimum spend, paid membership, "members only", being turned away over clothes or ability to pay, or the place described as upscale, exclusive, or beyond the writer's means. A plain remark that something was pricey or overpriced is not this.
- `targeting`: who the place is for or who its crowd is, as a social group: an ethnicity or nationality, a religion, a gender, LGBTQ people, an age group, a language community, a race, a profession or class ("a mostly older crowd", "women only", "the place for the Ethiopian community"). "Good for families" or "nice for a date" is not this.
- `cultural`: the place as part of a cultural community or identity: authenticity, heritage, "a taste of home", a community gathering point, a faith community, an LGBTQ space, a subculture. Naming a cuisine or praising the food is not this.
- `political`: a party, a candidate, a political movement, or a contested political issue is named in connection with the place, its owners, or its crowd.

A review marked `[translated]` was written in another language and is shown in Google's English translation. Judge it by what it says, like any other review; the language alone is not a reason to pick it.

Return the review numbers you picked, each with its tags. Return an empty list if none qualifies, which is the usual case.
