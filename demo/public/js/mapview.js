// The Leaflet map: basemap, the two point layers (Google places = circles, Meetup venues = diamonds), and the hexagon layer.
// Dataset identity is carried by shape, so both datasets can share one colour scale.
// Each view's pop-up shows only that view's dimension: the score, what the level means, and the details behind it.
/* global L */
import { MAP_START, BASIS_WORDS, IDENTITY_BASIS, LEVELS, valueOf } from "./config.js";
import { categoryColor, scoreColor, rateColor, scoreBin } from "./scales.js";
import { loadSurface } from "./data.js";

// A canvas renderer that can draw a circle marker as a diamond.
const ShapeCanvas = L.Canvas.extend({
  _updateCircle(layer) {
    if (layer.options.shape !== "diamond") return L.Canvas.prototype._updateCircle.call(this, layer);
    if (!this._drawing || layer._empty()) return;
    const p = layer._point, ctx = this._ctx, r = Math.max(Math.round(layer._radius), 1) * 1.3;
    ctx.beginPath(); ctx.moveTo(p.x, p.y - r); ctx.lineTo(p.x + r, p.y); ctx.lineTo(p.x, p.y + r); ctx.lineTo(p.x - r, p.y); ctx.closePath();
    this._fillStroke(ctx, layer);
  },
});

const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const fmt = (v) => (Number.isInteger(v) ? String(v) : v.toFixed(1));
const words = (s) => (s || "").replace(/_/g, " ");

export function createMap(container) {
  const map = L.map(container, { preferCanvas: true, zoomControl: true, minZoom: 9, maxZoom: 17 }).setView(MAP_START.center, MAP_START.zoom);
  const dark = window.matchMedia("(prefers-color-scheme: dark)");
  // OpenStreetMap's standard tiles, greyed (and inverted in dark mode) in css/app.css so the data carries the colour.
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19 }).addTo(map);
  map.createPane("hexes").style.zIndex = 380;
  map.createPane("regions").style.zIndex = 385; map.createPane("blines").style.zIndex = 420;
  const svg = L.svg({ pane: "blines", padding: 0.3 }), svgRegions = L.svg({ pane: "regions", padding: 0.3 });
  const renderer = new ShapeCanvas({ padding: 0.3 });
  const points = L.layerGroup().addTo(map), hexLayer = L.layerGroup().addTo(map);
  const band = () => (map.getZoom() <= 10 ? 0 : map.getZoom() <= 12 ? 1 : 2);
  return { map, renderer, points, hexLayer, svg, svgRegions,
    onZoomBand: (fn) => { let b = band(); map.on("zoomend", () => { if (band() !== b) { b = band(); fn(); } }); },
    onThemeChange: (fn) => dark.addEventListener("change", fn) };
}

// ---- pop-ups: built with textContent, because names come from review sites and Meetup
function head(title, sub) { const d = el("div", "pop"); d.append(el("h3", "", title), el("div", "sub", sub)); return d; }
function scoreBlock(d, label, value, meaning) {
  const b = el("div", "score"); b.append(el("span", "big", fmt(value)), el("span", "of", " / 5"), el("span", "lbl", label));
  d.append(b); if (meaning) d.append(el("p", "meaning", meaning));
}
function rows(d, list) {
  const t = el("table");
  for (const [k, v] of list) { const tr = el("tr"); tr.append(el("td", "k", k), el("td", "", v)); t.append(tr); }
  d.append(t);
}
const choiceLabel = (dimId, choice, meta) => choice === "all" ? "" : dimId === "political" ? meta.political_leans.find((l) => l.id === choice)?.label || choice : choice;
const subPlace = (p) => `Google place · ${p.cat} · ${p.co}`;
const subVenue = (v) => `Meetup venue · ${v.ev.toLocaleString()} events by ${v.ng} group${v.ng > 1 ? "s" : ""} · ${v.co}`;

function placeDetails(p, dimId, choice) {
  if (dimId === "targeting") return p.t ? [["Aimed at", p.tw || "—"], ["Kind of group", BASIS_WORDS[p.tb] || words(p.tb)]] : [];
  if (dimId === "barrier") return p.b && p.bk && p.bk !== "none" ? [["Kind of barrier", words(p.bk)]] : [];
  if (dimId === "cultural") {
    const ids = p.lab.filter((l) => l.s === "desc" && (choice === "all" || l.l === choice));
    return ids.length ? [["Identities named", ids.map((l) => `${l.l} ${l.i}`).join(", ")]] : [];
  }
  return [];
}
function placePopup(p, dim, choice, meta) {
  const what = choiceLabel(dim.id, choice, meta), v = valueOf(p, dim.id, choice);
  const d = head(p.n, subPlace(p));
  scoreBlock(d, what ? `${dim.title}: ${what}` : dim.title, v, LEVELS[dim.id]?.[scoreBin(v)]);
  const det = placeDetails(p, dim.id, choice); if (det.length) rows(d, det);
  d.append(el("div", "foot", `Scored by an AI model from up to 20 of this place's ${p.nr.toLocaleString()} reviews (2017–2020). Review text is not shown.`));
  return d;
}
function groupLine(g, dim, choice, meta) {
  const v = valueOf(g, dim.id, choice), li = el("li");
  const top = el("div", "gl"); top.append(el("b", "", fmt(v)), el("span", "gname", g.n));
  li.append(top);
  const extra = dim.id === "targeting" && g.t ? `Aimed at: ${g.tw}` : dim.id === "political" && g.p && g.lean !== "none" ? `Leaning: ${choiceLabel("political", g.lean, meta) || words(g.lean)}`
    : dim.id === "barrier" && g.b && g.bk !== "none" ? `Barrier: ${words(g.bk)}` : dim.id === "cultural" && g.lab.length ? `Identities: ${g.lab.filter((l) => l.k !== "political").map((l) => `${l.l} ${l.i}`).join(", ")}` : "";
  if (extra) li.append(el("div", "gx", extra));
  if (g.pd) li.append(el("div", "gd", g.pd));
  return li;
}
function venuePopup(v, dim, choice, data) {
  const what = choiceLabel(dim.id, choice, data.meta), val = valueOf(v, dim.id, choice);
  const d = head(v.n, subVenue(v));
  scoreBlock(d, what ? `${dim.title}: ${what}` : dim.title, val, `This describes the Meetup groups that met here, not the venue itself: the average of their scores, weighted by events. Nearest level: ${LEVELS[dim.id]?.[scoreBin(val)].toLowerCase()}.`);
  const gs = v.top.map((t) => data.groups.get(t.id)).filter(Boolean).sort((a, b) => valueOf(b, dim.id, choice) - valueOf(a, dim.id, choice)).slice(0, 3);
  if (gs.length) { d.append(el("div", "k2", "Groups that met here")); const ul = el("ul", "groups"); gs.forEach((g) => ul.append(groupLine(g, dim, choice, data.meta))); d.append(ul); }
  d.append(el("div", "foot", "Each group was scored by an AI model from its own description. Descriptions are shortened and anonymised."));
  return d;
}
function categoryPopup(r, source, data) {
  if (source === "places") { const d = head(r.n, subPlace(r)); return d; }
  const d = head(r.n, subVenue(r)); d.append(el("p", "meaning", `Most events here are by ${r.cat.toLowerCase()} groups.`));
  const gs = r.top.map((t) => data.groups.get(t.id)).filter(Boolean).slice(0, 3);
  if (gs.length) { d.append(el("div", "k2", "Most active groups")); const ul = el("ul", "groups"); gs.forEach((g) => { const li = el("li"); li.append(el("div", "gname", `${g.n} · ${g.cat}`)); if (g.pd) li.append(el("div", "gd", g.pd)); ul.append(li); }); d.append(ul); }
  return d;
}
function criteriaPopup(r, source, state, data) {
  const d = head(r.n, source === "places" ? subPlace(r) : subVenue(r));
  rows(d, state.criteria.filter((c) => c.dim !== "unwelcome").map((c) => {
    const v = valueOf(r, c.dim, c.choice), what = choiceLabel(c.dim, c.choice, data.meta);
    return [`${titleOf(c.dim)}${what ? `: ${what}` : ""}`, `${fmt(v)} / 5`];
  }));
  return d;
}
let titleOf = (id) => id;
export function setTitles(fn) { titleOf = fn; }

function hexPopup(h, families, family) {
  const picked = families.find((f) => f.id === family);
  const d = head(picked ? `${fmt(h.fam[picked.id])} reports per 1,000 reviews` : `${fmt(h.rate)} reports per 1,000 reviews`, `${h.places} scored places · ${h.reviews.toLocaleString()} text reviews in this area`);
  d.append(el("p", "meaning", "A report is a review in which the writer says they were treated worse because of who they are." + (picked ? ` Shown: people made unwelcome as ${picked.label.toLowerCase()}.` : "")));
  rows(d, [["All groups", fmt(h.rate)], ...families.map((f) => [f.label, fmt(h.fam[f.id])])]);
  d.append(el("div", "foot", "Areas only: no single place is shown for this measure."));
  return d;
}
function comboHexPopup(h, share, rate, condText, cls, wordsMap) {
  const d = head(wordsMap[cls][0].toUpperCase() + wordsMap[cls].slice(1), `${h.places} scored places · ${h.reviews.toLocaleString()} text reviews in this area`);
  rows(d, [[`Places meeting: ${condText}`, `${Math.round(share * 100)}%`], ["Unwelcome reports per 1,000 reviews", fmt(rate)]]);
  d.append(el("div", "foot", "Both measures describe the same area; they show where to look, not that one causes the other."));
  return d;
}

// ---- areas: regions where a characteristic is concentrated, and boundary lines styled by the evidence behind them
export const surfaceKey = (state) => `${state.areaSource}~${state.dim.id}~${state.dim.id === "unwelcome" ? "all" : state.choice[state.dim.id] ?? "all"}`;
export function surfaceAvailable(data, key) { return (data.meta.boundaries?.surfaces || []).some((s) => s.key === key); }
const UNIT_WORDS = { google: "Google places", meetup: "Meetup activity (groups weighted by events)" };
async function drawAreas(view, data, state, tokens, shown) {
  const key = surfaceKey(state);
  if (!surfaceAvailable(data, key)) { shown.areaNote = "Not enough data for areas with this choice. Try “Any”, or the other data source."; return; }
  const s = await loadSurface(key);
  if (surfaceKey(state) !== key || state.view !== "areas") return;   // the reader moved on while it loaded
  const fills = { 0: tokens.areaLow, 2: tokens.score[3], 3: tokens.score[5] };
  const unitText = s.unit === "%" ? `${UNIT_WORDS[s.source]} scoring 3 or more` : "reports per 1,000 reviews";
  for (const r of s.regions) {
    const shareText = s.unit === "%" ? `${fmt(r.share)}%` : fmt(r.share);
    L.polygon([r.outer, ...r.holes], { renderer: view.svgRegions, stroke: false, fillColor: fills[r.level], fillOpacity: r.level === 0 ? 0.35 : 0.3 + 0.35 * r.stability })
      .bindTooltip(`${r.name[0].toUpperCase() + r.name.slice(1)}: ${shareText} here vs ${s.unit === "%" ? `${fmt(s.region_share)}%` : fmt(s.region_share)} region-wide`, { sticky: true })
      .bindPopup(() => { const d = head(r.name[0].toUpperCase() + r.name.slice(1), `${UNIT_WORDS[s.source]} · about ${fmt(r.area_km2)} km²`);
        rows(d, [[`Here (${unitText})`, shareText], ["Region-wide", s.unit === "%" ? `${fmt(s.region_share)}%` : fmt(s.region_share)],
                 ["Effective number of units behind it", fmt(r.support)], ["Same class in resampled data", `${Math.round(r.stability * 100)}%`]]);
        d.append(el("div", "foot", "Areas are smoothed over about 1.5 km and shown only where at least 5 units support them. A region describes the data, not a territory of a group."));
        return d; }, { maxWidth: 340 }).addTo(view.hexLayer);
    shown.hexes.push({ lat: r.outer[0][0], lon: r.outer[0][1], value: r.level >= 2 ? r.share : 0, places: 0, reviews: 0, region: r });
  }
  const W = [1, 1.8, 3, 4.6], OP = [0.35, 0.65, 0.95], SHARP = ["gradual", "moderate", "sharp", "very sharp"], CERT = ["uncertain position", "fairly certain position", "certain position"];
  for (const l of s.lines) {
    // boundary lines take a hue of their own, so they are not read as roads on the grey basemap
    L.polyline(l.pts, { renderer: view.svg, color: tokens.cat[1], weight: W[l.sharp], opacity: OP[l.cert], lineCap: "round", className: l.cert === 0 ? "bl-blur" : l.cert === 1 ? "bl-soft" : "bl-crisp", interactive: true })
      .bindTooltip(`${SHARP[l.sharp]} change · ${CERT[l.cert]} (±${fmt(l.unc_km)} km) · ${fmt(l.support)} units`, { sticky: true }).addTo(view.hexLayer);
  }
  shown.surface = s;
}

// ---- drawing
export async function draw(view, data, state, tokens) {
  const { points, hexLayer, renderer } = view; points.clearLayers(); hexLayer.clearLayers();
  const dim = state.dim, shown = { places: [], venues: [], hexes: [] };
  if (state.view === "areas" && (dim.kind === "score" || dim.kind === "area")) { await drawAreas(view, data, state, tokens, shown); return shown; }
  const uw = dim.kind === "filter" ? state.criteria.find((c) => c.dim === "unwelcome") : null;

  if (dim.kind === "area" || uw) {                         // areas are always built from the Google places
    const others = dim.kind === "filter" ? state.criteria.filter((c) => c.dim !== "unwelcome") : [];
    if (others.length && !data.byHex) {                    // index the places by hexagon once
      data.byHex = new Map();
      for (const p of data.places) { if (!data.byHex.has(p.hx)) data.byHex.set(p.hx, []); data.byHex.get(p.hx).push(p); }
    }
    const family = uw ? uw.choice : state.family;
    const condText = others.map((c) => `${titleOf(c.dim)}${c.choice !== "all" ? ` (${choiceLabel(c.dim, c.choice, data.meta)})` : ""} ≥ ${c.min}`).join(" and ");
    const colors = { both: tokens.cat[2], ident: tokens.cat[0], unw: tokens.cat[1], none: tokens.rate[0] };
    const wordsMap = { both: "both conditions met", ident: "place conditions met only", unw: "high unwelcome rate only", none: "neither" };
    for (const h of data.hexes) {
      if (!h.show) continue;
      const rate = family === "all" ? h.rate : h.fam[family];
      if (dim.kind === "area") {
        L.polygon(h.ring, { pane: "hexes", color: tokens.ring, weight: 1, fillColor: rateColor(tokens, rate), fillOpacity: 0.72 })
          .bindTooltip(`${fmt(rate)} reports per 1,000 reviews`, { sticky: true }).bindPopup(() => hexPopup(h, data.meta.unwelcome_families, family), { maxWidth: 340 }).addTo(hexLayer);
        shown.hexes.push({ ...h, value: rate }); continue;
      }
      const uh = rate >= uw.min;
      if (!others.length) {                                // unwelcomeness alone: highlight the cells above the threshold
        L.polygon(h.ring, { pane: "hexes", color: tokens.ring, weight: 1, fillColor: uh ? colors.unw : colors.none, fillOpacity: uh ? 0.78 : 0.45 })
          .bindTooltip(`${fmt(rate)} reports per 1,000 reviews`, { sticky: true }).bindPopup(() => hexPopup(h, data.meta.unwelcome_families, family), { maxWidth: 340 }).addTo(hexLayer);
        if (uh) shown.hexes.push({ ...h, value: rate, cls: "unw" }); continue;
      }
      const ps = data.byHex.get(h.id) || [];
      if (ps.length < 5) continue;                          // with fewer places one place would decide the share
      const wsum = ps.reduce((s, p) => s + p.w, 0);
      const share = ps.reduce((s, p) => s + (others.every((c) => { const v = valueOf(p, c.dim, c.choice); return v != null && v >= c.min; }) ? p.w : 0), 0) / wsum;
      const hi = share >= state.share, cls = hi && uh ? "both" : hi ? "ident" : uh ? "unw" : "none";
      L.polygon(h.ring, { pane: "hexes", color: tokens.ring, weight: 1, fillColor: colors[cls], fillOpacity: cls === "none" ? 0.45 : 0.78 })
        .bindTooltip(`${wordsMap[cls]} · ${Math.round(share * 100)}% of places · ${fmt(rate)} per 1,000`, { sticky: true })
        .bindPopup(() => comboHexPopup(h, share, rate, condText, cls, wordsMap), { maxWidth: 340 }).addTo(hexLayer);
      if (cls === "both") shown.hexes.push({ ...h, value: rate, cls });
    }
    return shown;
  }

  // Marks are smaller when zoomed out, where thousands overlap downtown, and grow as the reader zooms in.
  const z = view.map.getZoom(), big = z <= 10 ? 3 : z <= 12 ? 4 : 5.5;
  const marker = (rec, shape, color, strong, popup, tip) =>
    L.circleMarker([rec.lat, rec.lon], { renderer, shape, radius: strong ? big + (dim.kind === "category" ? 0 : 1.5) : big - 1, color: tokens.ring, weight: strong ? 1 : 0.5, fillColor: color, fillOpacity: strong ? 0.92 : 0.6 })
      .bindTooltip(tip, { direction: "top", offset: [0, -4] }).bindPopup(popup, { maxWidth: 340 });

  const add = (records, source, shape, cats) => {
    if (!state.layers[source] || !dim.sources.includes(source)) return;
    const rowsOut = [];
    for (const r of records) {
      if (source === "venues" && r.ev < state.minEvents) continue;
      if (dim.kind === "category") {
        if (state.hiddenCats[source].has(r.cat)) continue;
        rowsOut.push({ r, v: 0, color: categoryColor(tokens, cats, r.cat), strong: true, tip: `${r.n} · ${r.cat}`, pop: () => categoryPopup(r, source, data) });
      } else if (dim.kind === "filter") {
        // the institution rule of the Exclusivity view applies here too: a school's clientele is not identity targeting
        const vals = state.criteria.map((c) => (c.dim === "targeting" && c.choice === "all" && source === "places" && !state.institutions && !IDENTITY_BASIS.has(r.tb)) ? 0 : valueOf(r, c.dim, c.choice));
        if (!vals.every((v, i) => v != null && v >= state.criteria[i].min - 0.5)) continue;   // venue averages round to the nearest level
        rowsOut.push({ r, v: vals[0], color: tokens.score[4], strong: true, tip: `${r.n}`, pop: () => criteriaPopup(r, source, state, data) });
      } else {
        const choice = state.choice[dim.id] ?? "all", v = valueOf(r, dim.id, choice);
        if (v == null || scoreBin(v) < state.minScore) continue;
        if (dim.id === "targeting" && choice === "all" && source === "places" && !state.institutions && v > 0 && !IDENTITY_BASIS.has(r.tb)) continue;
        rowsOut.push({ r, v, color: scoreColor(tokens, v), strong: scoreBin(v) > 0, tip: source === "venues" ? `${r.n} · groups meeting here: ${fmt(v)} / 5` : `${r.n} · ${fmt(v)} / 5`,
          pop: () => (source === "places" ? placePopup(r, dim, choice, data.meta) : venuePopup(r, dim, choice, data)) });
      }
    }
    rowsOut.sort((a, b) => a.v - b.v);                     // zero scores first, so the strong marks sit on top
    for (const x of rowsOut) marker(x.r, shape, x.color, x.strong, x.pop, x.tip).addTo(points);
    shown[source] = rowsOut.map((x) => ({ ...x.r, value: x.v }));
  };
  add(data.places, "places", "circle", data.meta.place_categories);
  add(data.venues, "venues", "diamond", data.meta.meetup_categories);
  return shown;
}
