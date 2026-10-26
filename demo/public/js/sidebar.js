// The left sidebar: which datasets are on, which dimension colours the map, that dimension's options,
// and a short list of the strongest items shown (so no value is reachable by colour alone). The legend sits on the map.
import { DIMENSIONS, SCORE_WORDS, RATE_LABELS, CRITERIA_DIMS } from "./config.js";
import { categoryColor } from "./scales.js";

const el = (tag, props = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) { if (k === "class") e.className = v; else if (k === "text") e.textContent = v; else if (k in e) e[k] = v; else e.setAttribute(k, v); }
  e.append(...kids); return e;
};
const fmt = (v) => (Number.isInteger(v) ? String(v) : v.toFixed(1));
const dimById = (id) => DIMENSIONS.find((d) => d.id === id);

export function buildSidebar(root, legend, map, data, state, tokens, onChange) {
  const { meta } = data;
  const change = (fn, rebuild = false) => (ev) => { fn(ev); onChange(rebuild); };

  // A <select> of identities, grouped by family, with an "any" entry first.
  function identitySelect(dimId, value, onPick, anyText, rebuild = false) {
    const list = meta.identities[dimId] || [];
    const sel = el("select", { onchange: change((e) => onPick(e.target.value), rebuild) }, el("option", { value: "all", text: anyText }));
    for (const fam of meta.identity_families) {
      const items = list.filter((x) => x.family === fam);
      if (items.length) sel.append(el("optgroup", { label: fam }, ...items.map((x) => el("option", { value: x.id, text: `${x.id} (${x.n})`, selected: value === x.id }))));
    }
    return sel;
  }
  const leanSelect = (value, onPick) => el("select", { onchange: change((e) => onPick(e.target.value)) },
    el("option", { value: "all", text: "Any leaning" }), ...meta.political_leans.map((l) => el("option", { value: l.id, text: l.label, selected: value === l.id })));
  const familySelect = (value, onPick) => el("select", { onchange: change((e) => onPick(e.target.value)) },
    el("option", { value: "all", text: "All groups" }), ...meta.unwelcome_families.map((f) => el("option", { value: f.id, text: f.label, selected: value === f.id })));
  const choiceSelect = (dimId, value, onPick, rebuild = false) => dimId === "unwelcome" ? familySelect(value, onPick) : dimId === "political" ? leanSelect(value, onPick)
    : dimById(dimId).picker === "identity" ? identitySelect(dimId, value, onPick, dimId === "targeting" ? "Any group" : "Any identity", rebuild) : null;

  const slider = (label, min, max, step, value, onInput, show = String) => {
    const out = el("output", { text: show(value) });
    return el("div", { class: "control" }, el("label", { text: label }),
      el("input", { type: "range", min, max, step, value, "aria-label": label, oninput: change((e) => { onInput(+e.target.value); out.textContent = show(+e.target.value); }) }), out);
  };

  // 1. datasets: a layer the current dimension does not cover is shown as unavailable, not as a switch that does nothing
  const layers = el("section");
  function renderLayers() {
    const row = (id, shape, text, count) => {
      const areaMode = state.dim.kind === "filter" && state.criteria.some((c) => c.dim === "unwelcome");   // results are areas built from Google places
      const ok = state.dim.sources.includes(id) && !(areaMode && id === "venues");
      const required = ok && id === "places" && (areaMode || state.dim.kind === "area");
      return el("label", { class: ok ? "row" : "row disabled", title: ok ? (required ? "Areas are built from Google places, so this layer stays on" : "") : "Not available for this dimension" },
        el("input", { type: "checkbox", checked: (state.layers[id] || required) && ok, disabled: !ok || required, onchange: change((e) => { state.layers[id] = e.target.checked; }) }),
        el("span", { class: `swatch ${shape}`, style: "background: var(--s3)" }), el("span", { text }), el("span", { class: "count", text: ok ? count.toLocaleString() : "not for this view" }));
    };
    layers.replaceChildren(el("h2", { text: "Data layers" }), row("places", "", "Google reviews: places", meta.counts.places), row("venues", "diamond", "Meetup: venues of groups", meta.counts.venues));
    if (state.dim.sources.includes("venues") && state.layers.venues && !(state.dim.kind === "filter" && state.criteria.some((c) => c.dim === "unwelcome")))
      layers.append(slider("Venues with events from", 1, 20, 1, state.minEvents, (v) => { state.minEvents = v; }),
        el("p", { class: "hint", text: "A venue used once or twice carries the score of a single group. Venues that look like someone's home are not shown." }));
  }

  // 2. dimension
  const dims = el("section", {}, el("h2", { text: "What the map shows" }));
  for (const d of DIMENSIONS) {
    dims.append(el("label", { class: "row dim" },
      el("span", { class: "title" }, el("input", { type: "radio", name: "dim", checked: state.dim.id === d.id, onchange: change(() => { state.dim = d; }) }), el("span", { text: d.title }), el("span", { class: "tag", text: d.frame })),
      el("span", { class: "desc", text: d.desc })));
  }

  const options = el("section"), top = el("section"), about = el("section");
  about.append(el("p", { class: "note", text: `${meta.note} Scored by ${meta.model}; reviews and events from ${meta.window}. ` }), el("p", { class: "note" }, el("a", { href: "about", text: "How the dimensions and boundaries are derived" })));
  root.replaceChildren(layers, dims, options, top, about);

  function renderOptions() {
    const d = state.dim; renderLayers(); options.replaceChildren(el("h2", { text: "Options" }));
    if (d.kind === "category") {
      for (const [source, title, list, shape] of [["places", "Google place categories", meta.place_categories, ""], ["venues", "Meetup group categories", meta.meetup_categories, "diamond"]]) {
        options.append(el("div", { class: "group-label", text: title }));
        for (const c of list) {
          options.append(el("label", { class: "row" },
            el("input", { type: "checkbox", checked: !state.hiddenCats[source].has(c), onchange: change((e) => { e.target.checked ? state.hiddenCats[source].delete(c) : state.hiddenCats[source].add(c); }) }),
            el("span", { class: `swatch ${shape}`, style: `background:${categoryColor(tokens, list, c)}` }), el("span", { text: c })));
        }
      }
      options.append(el("p", { class: "hint", text: "Eight colours cannot all be told apart on a map. Untick categories to isolate the ones you are comparing, or point at a mark to read its category." }));
    } else if (d.kind === "score") {
      const sel = choiceSelect(d.id, state.choice[d.id], (v) => { state.choice[d.id] = v; if (v !== "all") state.minScore = Math.max(1, state.minScore); }, true);
      if (sel) options.append(el("div", { class: "control" }, el("label", { text: d.id === "targeting" ? "Aimed at" : d.id === "cultural" ? "Identity" : "Leaning" }), sel));
      options.append(slider("Show scores from", state.choice[d.id] && state.choice[d.id] !== "all" ? 1 : 0, 5, 1, state.minScore, (v) => { state.minScore = v; }),
        el("p", { class: "hint", text: "A score of 1 is a single passing remark and can change from one run to the next. Scores of 2 and above are steadier." }));
      if (d.id === "targeting" && state.choice.targeting === "all") options.append(el("label", { class: "row" }, el("input", { type: "checkbox", checked: state.institutions, onchange: change((e) => { state.institutions = e.target.checked; }) }),
        el("span", { text: "Include institutions, occupation, and age" })), el("p", { class: "hint", text: "Off: only places aimed at an ethnicity, religion, gender, sexuality, race, or language. A school or a seniors centre serves a set clientele by function." }));
      if (sel && d.id !== "political") options.append(el("p", { class: "hint", text: "The number after each name counts the places and groups in the current sample (which over-represents culturally marked places), not the whole region." }));
      if (d.id === "political") options.append(el("p", { class: "hint", text: "Meetup groups only. In reviews of places, political remarks are single and unreliable." }));
    } else if (d.kind === "area") {
      options.append(el("div", { class: "control" }, el("label", { text: "Made unwelcome as" }), familySelect(state.family, (v) => { state.family = v; })),
        el("p", { class: "hint", text: `Reports per 1,000 text reviews, pooled over each hexagon. Overall: ${fmt(meta.unwelcome.overall_rate_per_1000)}. A busy place almost always has one report, so a count would only show foot traffic; the rate does not.` }),
        el("p", { class: "hint", text: `Hexagons with fewer than ${meta.unwelcome.min_places} scored places or ${meta.unwelcome.min_reviews} reviews are left blank.` }));
    } else if (d.kind === "filter") {
      state.criteria.forEach((c, i) => {
        const dimSel = el("select", { "aria-label": "Dimension", onchange: change((e) => { c.dim = e.target.value; c.choice = "all"; c.min = c.dim === "unwelcome" ? 5 : Math.min(5, Math.max(1, Math.round(c.min))); }, true) },
          ...CRITERIA_DIMS.map((id) => {
            // Unwelcomeness exists only for areas built from Google places, which have no political score, so the two cannot be paired
            const clash = state.criteria.some((o, j) => j !== i && ((id === "political" && o.dim === "unwelcome") || (id === "unwelcome" && o.dim === "political")));
            return el("option", { value: id, text: dimById(id).title + (clash ? " (not with the other condition)" : ""), selected: c.dim === id, disabled: clash });
          }));
        const box = el("div", { class: "criterion" }, el("div", { class: "control" }, dimSel,
          el("button", { type: "button", class: "ghost", title: "Remove this condition", "aria-label": "Remove this condition", text: "×", disabled: state.criteria.length === 1, onclick: change(() => { state.criteria.splice(i, 1); }, true) })));
        const sel = choiceSelect(c.dim, c.choice, (v) => { c.choice = v; });
        if (sel) box.append(el("div", { class: "control" }, el("label", { text: { political: "Leaning", targeting: "Aimed at", unwelcome: "Made unwelcome as" }[c.dim] || "Identity" }), sel));
        box.append(c.dim === "unwelcome" ? slider("Reports per 1,000 reviews from", 0.5, 10, 0.5, c.min, (v) => { c.min = v; }, fmt) : slider("At least", 1, 5, 1, c.min, (v) => { c.min = v; }));
        options.append(box);
        if (i < state.criteria.length - 1) options.append(el("div", { class: "and", text: "and" }));
      });
      if (state.criteria.length < 4) options.append(el("button", { type: "button", class: "ghost wide", text: "+ Add a condition", onclick: change(() => { state.criteria.push({ dim: "barrier", choice: "all", min: 2 }); }, true) }));
      const hasUw = state.criteria.some((c) => c.dim === "unwelcome"), nOther = state.criteria.filter((c) => c.dim !== "unwelcome").length;
      if (hasUw && nOther) options.append(slider("Share of places meeting the other conditions", 0.05, 0.5, 0.05, state.share, (v) => { state.share = v; }, (v) => `${Math.round(v * 100)}%`));
      options.append(el("p", { class: "hint", text: hasUw
        ? `With Unwelcomeness, the result is areas: hexagons where the unwelcome rate reaches the threshold${nOther ? " and enough of the places meet the other conditions (hexagons with fewer than 5 scored places are left out)" : ""}. ${fmt(meta.unwelcome.overall_rate_per_1000)} reports per 1,000 reviews is the average.`
        : "Google places have no political leaning, so a political condition keeps only Meetup venues. A venue's score is the average of the groups that met there." }));
    }
  }

  function renderLegend(shown) {
    const d = state.dim; legend.replaceChildren();
    const scale = (colors, labels) => el("div", { class: "scale" }, ...colors.map((c, i) => el("div", {}, el("i", { style: `background:${c}` }), labels[i])));
    const keyRow = (color, text, shape = "hex") => el("div", { class: "keyrow" }, el("span", { class: `swatch ${shape}`, style: `background:${color}` }), el("span", { text }));
    if (d.kind === "score") {
      const choice = state.choice[d.id] ?? "all"; const what = choice === "all" ? d.title : d.id === "targeting" ? `Aimed at ${choice}` : d.id === "cultural" ? `${choice} identity` : meta.political_leans.find((l) => l.id === choice)?.label || d.title;
      legend.append(el("div", { class: "note", text: `${what}: 0 none to 5 strong` }), scale(tokens.score, ["0", "1", "2", "3", "4", "5"]),
        el("p", { class: "hint", text: "● Google place (score of the place)   ◆ Meetup venue (average of the groups that met there)" }));
    } else if (d.kind === "area") legend.append(el("div", { class: "note", text: "Reports of being made unwelcome, per 1,000 reviews" }), scale(tokens.rate, RATE_LABELS));
    else if (d.kind === "filter" && state.criteria.some((c) => c.dim === "unwelcome")) {
      if (state.criteria.length > 1) legend.append(el("div", { class: "note", text: "Hexagons" }), keyRow(tokens.cat[2], "Both: places meet the conditions and the unwelcome rate is high"),
        keyRow(tokens.cat[0], "Places meet the conditions; unwelcome rate below the threshold"), keyRow(tokens.cat[1], "Unwelcome rate high; places do not meet the conditions"), keyRow(tokens.rate[0], "Neither"));
      else legend.append(el("div", { class: "note", text: "Hexagons" }), keyRow(tokens.cat[1], "Unwelcome rate at or above the threshold"), keyRow(tokens.rate[0], "Below the threshold"));
    }
    else if (d.kind === "filter") legend.append(el("div", { class: "note", text: "Meets every condition" }), keyRow(tokens.score[4], "Google place", ""), keyRow(tokens.score[4], "Meetup venue", "diamond"));
    else legend.append(el("p", { class: "note", text: "Colours are listed with the category switches in the sidebar. ● Google place   ◆ Meetup venue" }));
    const areaMode = d.kind === "area" || (d.kind === "filter" && state.criteria.some((c) => c.dim === "unwelcome"));
    const n = areaMode ? `${shown.hexes.length} hexagons${d.kind === "filter" ? " meeting every condition" : ""}` : `${shown.places.length.toLocaleString()} places, ${shown.venues.length.toLocaleString()} venues`;
    legend.append(el("p", { class: "hint", text: `Showing ${n}.` }));
  }

  function renderTop(shown) {
    const d = state.dim; top.replaceChildren();
    if (d.kind === "category") return;
    const hexRows = (list) => list.map((h) => ({ value: h.value, at: [h.lat, h.lon], zoom: 13, text: `Area with ${h.places} places, ${h.reviews.toLocaleString()} reviews` }));
    let rows;
    if (d.kind === "area") rows = hexRows(shown.hexes);
    else if (d.kind === "filter" && state.criteria.some((c) => c.dim === "unwelcome")) rows = hexRows(shown.hexes);
    else rows = [...shown.places.map((p) => ({ value: p.value, at: [p.lat, p.lon], zoom: 15, text: `${p.n} · ${p.cat}` })), ...shown.venues.filter((v) => v.ev >= 5).map((v) => ({ value: v.value, at: [v.lat, v.lon], zoom: 15, text: `${v.n} · Meetup, ${v.ev} events` }))];
    rows = rows.filter((r) => r.value > 0).sort((a, b) => b.value - a.value).slice(0, 10);
    top.append(el("h2", { text: { area: "Highest rates shown", filter: "Meeting every condition" }[d.kind] || "Strongest shown" }));
    if (!rows.length) { top.append(el("p", { class: "note", text: "Nothing to list with the current settings." })); return; }
    top.append(el("ul", { class: "toplist" }, ...rows.map((r) => el("li", {}, el("button", { type: "button", title: `Show on the map: ${r.text}`, onclick: () => map.flyTo(r.at, r.zoom) }, el("b", { text: fmt(r.value) }), el("span", { text: r.text }))))));
    const tail = d.kind === "filter" ? "Sorted by the first condition's score. " : "";
    top.append(el("p", { class: "hint", text: tail + (d.kind === "score" || d.kind === "filter" ? `Click a row to go there. Meetup venues are listed only with 5 or more events. Scale: ${SCORE_WORDS.map((w, i) => `${i} ${w}`).join(", ")}.` : "Click a row to go there.") }));
  }

  return { renderOptions, update(shown) { renderLegend(shown); renderTop(shown); } };
}
