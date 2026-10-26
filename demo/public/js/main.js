// Entry point: load the data, build the sidebar, and redraw the map whenever the state changes.
import { DIMENSIONS } from "./config.js";
import { loadAll } from "./data.js";
import { readTokens } from "./scales.js";
import { createMap, draw, setTitles } from "./mapview.js";
setTitles((id) => DIMENSIONS.find((d) => d.id === id)?.title || id);
import { buildSidebar } from "./sidebar.js";

const status = document.getElementById("status");
const state = {
  layers: { places: true, venues: true },
  minEvents: 3,                     // a venue used once or twice says little about a place; its score is the one group's
  dim: DIMENSIONS[0],
  minScore: 2,                      // level 1 is a single passing remark; start above it
  institutions: false,              // targeting: identity-based only by default
  choice: { targeting: "all", cultural: "all", political: "all" },   // identity or leaning picked for each dimension
  family: "all",
  criteria: [{ dim: "cultural", choice: "all", min: 3 }, { dim: "targeting", choice: "all", min: 3 }],
  share: 0.2,                       // Combined criteria with Unwelcomeness: share of an area's places that must meet the other conditions
  hiddenCats: { places: new Set(), venues: new Set() },
  view: "points",                   // "points" (marks or hexagons) or "areas" (regions and boundary lines)
  areaSource: "meetup",             // the one source an Areas view is built from: "google" or "meetup"
  topOpen: false,                   // the "strongest shown" list starts collapsed
};

// The state is mirrored in the address bar, so a view can be shared as a link: ?dim=cultural&id=Korean&min=3
const q = new URLSearchParams(location.search);
state.dim = DIMENSIONS.find((d) => d.id === q.get("dim")) || state.dim;
if (q.has("min")) state.minScore = Math.max(0, Math.min(5, +q.get("min") || 0));
state.family = q.get("family") || "all"; state.institutions = q.get("inst") === "1";
if (q.has("id") && state.dim.id in state.choice) state.choice[state.dim.id] = q.get("id");
if (q.has("crit")) state.criteria = q.get("crit").split("|").slice(0, 4).map((s) => { const [dim, choice, min] = s.split("~"); return { dim, choice: choice || "all", min: +min || 1 }; }).filter((c) => ["cultural", "targeting", "barrier", "political", "unwelcome"].includes(c.dim));
if (state.criteria.some((c) => c.dim === "unwelcome")) state.criteria = state.criteria.filter((c) => c.dim !== "political");   // areas come from places, which have no political score
if (!state.criteria.length) state.criteria = [{ dim: "cultural", choice: "all", min: 3 }];
if (q.has("share")) state.share = Math.min(0.5, Math.max(0.05, +q.get("share") || 0.2));
for (const k of ["places", "venues"]) if (q.get(k) === "0") state.layers[k] = false;
if (q.has("ev")) state.minEvents = Math.max(1, +q.get("ev") || 3);
if (q.get("v") === "areas") state.view = "areas";
if (["google", "meetup"].includes(q.get("src"))) state.areaSource = q.get("src");
function saveState() {
  const p = new URLSearchParams();
  if (state.dim.id !== "category") p.set("dim", state.dim.id);
  if (state.dim.kind === "score" && state.minScore !== 2) p.set("min", state.minScore);
  if (state.choice[state.dim.id] && state.choice[state.dim.id] !== "all") p.set("id", state.choice[state.dim.id]);
  if (state.dim.id === "combine") p.set("crit", state.criteria.map((c) => `${c.dim}~${c.choice}~${c.min}`).join("|"));
  if (state.dim.id === "combine" && state.criteria.some((c) => c.dim === "unwelcome") && state.share !== 0.2) p.set("share", state.share);
  if (state.dim.id === "unwelcome" && state.family !== "all") p.set("family", state.family);
  if (state.dim.id === "targeting" && state.institutions) p.set("inst", "1");
  for (const k of ["places", "venues"]) if (!state.layers[k]) p.set(k, "0");
  if (state.minEvents !== 3) p.set("ev", state.minEvents);
  if (state.view === "areas" && (state.dim.kind === "score" || state.dim.kind === "area")) { p.set("v", "areas"); p.set("src", state.areaSource); }
  history.replaceState(null, "", p.size ? `?${p}` : location.pathname);
}

try {
  const view = createMap("map");
  const data = await loadAll();
  let tokens = readTokens();
  let sidebar;
  let ticket = 0;                   // only the latest redraw may update the sidebar (Areas load asynchronously)
  const redraw = async (rebuildOptions = true) => {
    const mine = ++ticket;
    if (rebuildOptions) sidebar.renderOptions();
    saveState();
    const shown = await draw(view, data, state, tokens);
    if (mine === ticket) sidebar.update(shown);
  };
  let lastDim = state.dim.id;
  // The sidebar's options are rebuilt when the dimension changes or a control asks for it (adding a condition);
  // not on every slider move, so the slider keeps focus while dragged.
  const build = () => { sidebar = buildSidebar(document.getElementById("sidebar"), document.getElementById("legend"), view.map, data, state, tokens, (rebuild = false) => { const changed = rebuild || lastDim !== state.dim.id; lastDim = state.dim.id; redraw(changed); }); };
  build(); await redraw();
  view.onZoomBand(() => redraw(false));
  view.onThemeChange(() => { tokens = readTokens(); build(); redraw(); });
  window.__sgl = { view, data, state };   // a handle for automated screenshots and for debugging in the console
  status.remove();
} catch (err) {
  console.error(err);
  status.textContent = `Could not load the map data: ${err.message}`;
}
