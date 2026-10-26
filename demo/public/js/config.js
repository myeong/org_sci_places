// Static configuration: where the data lives and what each map dimension means.
// Each dimension names the part of the conceptual frame it operationalises (social, psychological, cultural, political).

export const firebaseConfig = {
  projectId: "org-sci-boundaries",
  appId: "1:576065849356:web:28ce52c676c1bf8e5bc629",
  apiKey: "AIzaSyBdYjos5UZy_UHjO8jqQkgWWMuHdLAcvBI",          // a public web identifier, not a secret; access is set by firestore.rules
  authDomain: "org-sci-boundaries.firebaseapp.com",
};

export const MAP_START = { center: [38.9, -77.12], zoom: 10 };

// kind: "category" (colour = identity), "score" (0-5 on points), "area" (rate on hexagons), "filter" (Combined criteria: points meeting every condition, or hexagons when Unwelcomeness is one of them)
// picker: what the reader chooses within the dimension (an identity or a leaning); sources: which datasets carry it
export const DIMENSIONS = [
  { id: "category", kind: "category", frame: "Baseline", title: "Categories",
    desc: "What kind of place or group it is. The starting point that needs no AI.", sources: ["places", "venues"] },
  { id: "targeting", kind: "score", picker: "identity", frame: "Social", title: "Exclusivity by design",
    desc: "How narrowly a place or group limits who it is for, by its own description. Choose a group to see what is aimed at it.", sources: ["places", "venues"] },
  { id: "unwelcome", kind: "area", frame: "Psychological", title: "Unwelcomeness",
    desc: "Reviewers report being made unwelcome because of who they are. Shown for areas only, never for a named place.", sources: ["places"] },
  { id: "barrier", kind: "score", frame: "Social", title: "Socio-economic barrier",
    desc: "Cost, dress, or status limits who can take part.", sources: ["places", "venues"] },
  { id: "cultural", kind: "score", picker: "identity", frame: "Cultural", title: "Cultural identity",
    desc: "Expresses or gives belonging to a specific cultural community. Choose one, such as Korean or LGBTQ.", sources: ["places", "venues"] },
  { id: "political", kind: "score", picker: "lean", frame: "Political", title: "Political leaning",
    desc: "Expresses or attracts a political leaning. Meetup groups only.", sources: ["venues"] },
  { id: "combine", kind: "filter", frame: "Combined", title: "Combined criteria",
    desc: "Pair any dimensions. With Unwelcomeness in the pair, the result is areas, never single places.", sources: ["places", "venues"] },
];

// What each level means, in the codebook's own terms (data/reference/dimension_codebook.md); 2 and 4 lie between.
export const LEVELS = {
  targeting: ["Open to anyone", "A group is mentioned loosely as the usual crowd", "Leans toward a group", "Clearly oriented to a group; others welcome", "Strongly aimed at a group", "Explicitly restricted to, or exclusively for, a group"],
  cultural: ["No cultural identity", "A cultural flavour only, such as a cuisine or a name", "Some sense of a cultural identity", "The identity is a clear part of what it is", "A strong expression of the identity", "A core community institution or gathering point"],
  barrier: ["No barrier", "One remark that it is beyond someone's means", "Some signs of a barrier", "Described as upscale by several reviewers, or a stated dress code, cover charge, or fee", "A strong barrier", "Clearly exclusive"],
  political: ["No political leaning", "A passing political remark", "Some political tone", "Clear issue advocacy", "A strong political orientation", "Explicitly partisan, or part of a political movement"],
};

// The score of a record on a dimension, for a chosen identity or lean ("all" = the general score).
// null means the dimension does not apply to that record (political leaning of a Google place).
export function valueOf(rec, dimId, choice = "all") {
  switch (dimId) {
    case "targeting": return choice === "all" ? rec.t : (rec.ti?.[choice] ?? 0);
    case "cultural": return choice === "all" ? rec.c : (rec.ci?.[choice] ?? 0);
    case "political": return rec.p == null ? null : choice === "all" ? rec.p : rec.pl ? (rec.pl[choice] ?? 0) : (rec.lean === choice ? rec.p : 0);   // venues carry pl; groups their own lean
    case "barrier": return rec.b;
    default: return null;
  }
}
export const CRITERIA_DIMS = ["cultural", "targeting", "barrier", "political", "unwelcome"];

export const SCORE_WORDS = ["none", "weak", "weak to moderate", "moderate", "moderate to strong", "strong"];
export const RATE_BREAKS = [0, 1, 2.5, 5, 10];        // reports per 1,000 reviews: 0 | >0-1 | 1-2.5 | 2.5-5 | 5-10 | 10+
export const RATE_LABELS = ["0", "≤1", "≤2.5", "≤5", "≤10", "10+"];
export const IDENTITY_BASIS = new Set(["ethnicity_nationality", "religion", "gender", "sexuality", "race", "language"]);
export const BASIS_WORDS = {
  ethnicity_nationality: "ethnicity or nationality", religion: "religion", gender: "gender", sexuality: "sexuality", race: "race", language: "language",
  age_life_stage: "age or life stage", class_occupation: "class or occupation", service_eligibility: "an institution's clientele", none: "",
};
