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

  // 1. datasets as two chips. Points: each can be switched on or off. Areas: Google and Meetup are kept apart, so the chips pick one.
  const layers = el("section");
  const areasOn = () => state.view === "areas" && (state.dim.kind === "score" || state.dim.kind === "area");
  function renderLayers() {
    const comboAreas = state.dim.kind === "filter" && state.criteria.some((c) => c.dim === "unwelcome");
    const chip = (id, src, shape, text, count) => {
      let ok = state.dim.sources.includes(id) && !(comboAreas && id === "venues"), on, title = "";
      if (areasOn()) { ok = state.dim.id === "unwelcome" ? src === "google" : state.dim.sources.includes(id); on = ok && state.areaSource === src; title = "Areas are built from one source at a time"; }
      else { const required = ok && id === "places" && (comboAreas || state.dim.kind === "area"); on = ok && (state.layers[id] || required); if (required) title = "Areas are built from Google places"; }
      if (!ok) title = "Not available for this view";
      return el("button", { type: "button", class: "chip", title, "aria-pressed": String(on), "aria-disabled": String(!ok),
        onclick: change(() => { if (!ok) return; if (areasOn()) state.areaSource = src; else state.layers[id] = !state.layers[id]; }, true) },
        el("span", { class: `swatch ${shape}`, style: "background: var(--s3)" }), el("span", { text: `${text} · ${count.toLocaleString()}` }));
    };
    layers.replaceChildren(el("h2", { text: areasOn() ? "Areas built from" : "Data" }),
      el("div", { class: "chips" }, chip("places", "google", "", "Google places", meta.counts.places), chip("venues", "meetup", "diamond", "Meetup venues", meta.counts.venues)));
  }

  // 2. dimension
  const dims = el("section", {}, el("h2", { text: "What the map shows" }));
  for (const d of DIMENSIONS) {
    dims.append(el("label", { class: "row dim" },
      el("span", { class: "title" }, el("input", { type: "radio", name: "dim", checked: state.dim.id === d.id, onchange: change(() => { state.dim = d; }) }), el("span", { text: d.title }),
        el("span", { class: "info", title: d.desc, "aria-label": d.desc, tabindex: "0", text: "i" }), el("span", { class: "tag", text: d.frame }))));
  }

  const options = el("section"), top = el("section"), about = el("section");
  about.append(el("p", { class: "note", text: `${meta.note} Scored by ${meta.model}; reviews and events from ${meta.window}. ` }), el("p", { class: "note" }, el("a", { href: "about", text: "How the dimensions and boundaries are derived" })));
  root.replaceChildren(layers, dims, options, top, about);

  function renderOptions() {
    const d = state.dim; renderLayers(); options.replaceChildren(el("h2", { text: d.title }));
    const more = el("details", { class: "more" }, el("summary", { text: "More settings" }));
    const seg = (labels, value, onPick) => el("div", { class: "seg", role: "group" }, ...labels.map(([v, txt]) => el("button", { type: "button", "aria-pressed": String(value === v), text: txt, onclick: change(() => onPick(v), true) })));
    const viewSwitch = () => el("div", { class: "control" }, el("label", { text: "Show as" }),
      seg(d.kind === "area" ? [["points", "Hexagons"], ["areas", "Areas"]] : [["points", "Points"], ["areas", "Areas"]], state.view, (v) => {
        state.view = v;
        if (v === "areas") state.areaSource = d.id === "unwelcome" ? "google" : d.sources.includes(state.areaSource === "google" ? "places" : "venues") ? state.areaSource : (d.sources.includes("venues") ? "meetup" : "google");
      }));
    const venueSlider = () => slider("Meetup venues with events from", 1, 20, 1, state.minEvents, (v) => { state.minEvents = v; });
    if (d.kind === "category") {
      for (const [source, title, list, shape] of [["places", "Google place categories", meta.place_categories, ""], ["venues", "Meetup group categories", meta.meetup_categories, "diamond"]]) {
        options.append(el("div", { class: "group-label", text: title }));
        for (const c of list) {
          options.append(el("label", { class: "row" },
            el("input", { type: "checkbox", checked: !state.hiddenCats[source].has(c), onchange: change((e) => { e.target.checked ? state.hiddenCats[source].delete(c) : state.hiddenCats[source].add(c); }) }),
            el("span", { class: `swatch ${shape}`, style: `background:${categoryColor(tokens, list, c)}` }), el("span", { text: c })));
        }
      }
      more.append(venueSlider(), el("p", { class: "hint", text: "Eight colours cannot all be told apart on a map. Untick categories to isolate the ones you are comparing, or point at a mark to read its category." }));
      options.append(more);
    } else if (d.kind === "score") {
      const sel = choiceSelect(d.id, state.choice[d.id], (v) => { state.choice[d.id] = v; if (v !== "all") state.minScore = Math.max(1, state.minScore); }, true);
      if (sel) options.append(el("div", { class: "control" }, el("label", { text: d.id === "targeting" ? "Aimed at" : d.id === "cultural" ? "Identity" : "Leaning" }), sel));
      options.append(viewSwitch());
      if (state.view === "areas") more.append(el("p", { class: "hint", text: "Areas: shaded where the share is at least twice the region's (darker: four times), grey where it is below half. Lines mark the change: thick and crisp where it is sharp and well placed; thin, faint, or blurred where it is gradual or the data are thin. Areas are smoothed over about 1.5 km and need at least 5 units of support." }));
      else {
        more.append(slider("Show scores from", state.choice[d.id] && state.choice[d.id] !== "all" ? 1 : 0, 5, 1, state.minScore, (v) => { state.minScore = v; }),
          el("p", { class: "hint", text: "A score of 1 is a single passing remark and can change from one run to the next." }), venueSlider());
        if (d.id === "targeting" && state.choice.targeting === "all") more.append(el("label", { class: "row" }, el("input", { type: "checkbox", checked: state.institutions, onchange: change((e) => { state.institutions = e.target.checked; }) }),
          el("span", { text: "Include institutions, occupation, and age" })));
      }
      if (sel && d.id !== "political") more.append(el("p", { class: "hint", text: "Numbers in the menu count places and groups in the current sample, not the whole region." }));
      if (d.id === "political") more.append(el("p", { class: "hint", text: "Meetup groups only: in reviews of places, political remarks are single and unreliable." }));
      options.append(more);
    } else if (d.kind === "area") {
      if (state.view !== "areas") options.append(el("div", { class: "control" }, el("label", { text: "Made unwelcome as" }), familySelect(state.family, (v) => { state.family = v; })));
      options.append(viewSwitch());
      more.append(el("p", { class: "hint", text: `Reports per 1,000 text reviews (overall ${fmt(meta.unwelcome.overall_rate_per_1000)}). A rate, because a busy place almost always has one report. Hexagons with fewer than ${meta.unwelcome.min_places} scored places or ${meta.unwelcome.min_reviews} reviews are blank. Areas use all groups together.` }));
      options.append(more);
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
      if (hasUw && nOther) more.append(slider("Share of places meeting the other conditions", 0.05, 0.5, 0.05, state.share, (v) => { state.share = v; }, (v) => `${Math.round(v * 100)}%`));
      if (!hasUw) more.append(venueSlider());
      options.append(more);
      more.append(el("p", { class: "hint", text: hasUw
        ? `With Unwelcomeness, the result is areas: hexagons where the unwelcome rate reaches the threshold${nOther ? " and enough of the places meet the other conditions (hexagons with fewer than 5 scored places are left out)" : ""}. ${fmt(meta.unwelcome.overall_rate_per_1000)} reports per 1,000 reviews is the average.`
        : "Google places have no political leaning, so a political condition keeps only Meetup venues. A venue's score is the average of the groups that met there." }));
    }
  }

  function renderLegend(shown) {
    const d = state.dim; legend.replaceChildren();
    const scale = (colors, labels) => el("div", { class: "scale" }, ...colors.map((c, i) => el("div", {}, el("i", { style: `background:${c}` }), labels[i])));
    const keyRow = (color, text, shape = "hex") => el("div", { class: "keyrow" }, el("span", { class: `swatch ${shape}`, style: `background:${color}` }), el("span", { text }));
    if (state.view === "areas" && (d.kind === "score" || d.kind === "area")) {
      const sw = (c, txt, op = 0.6) => el("div", { class: "keyrow" }, el("span", { class: "swatch hex", style: `background:${c};opacity:${op}` }), el("span", { text: txt }));
      const lk = (w, op, cls, txt) => { const d2 = el("div", { class: "linekey" }); d2.innerHTML = `<svg viewBox="0 0 40 10" aria-hidden="true"><line x1="2" y1="5" x2="38" y2="5" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" opacity="${op}" class="${cls}"/></svg>`; d2.append(el("span", { text: txt })); return d2; };
      legend.append(el("div", { class: "note", text: shown.surface ? `${d.title}${state.choice[d.id] && state.choice[d.id] !== "all" && d.id !== "unwelcome" ? `: ${state.choice[d.id]}` : ""} · ${shown.surface.source === "google" ? "Google places" : "Meetup activity"}` : d.title }),
        sw(tokens.score[5], "Strongly concentrated (4× the region or more)", 0.75), sw(tokens.score[3], "Concentrated (2× or more)", 0.6), sw(tokens.areaLow, "Below half the region's level", 0.5),
        lk(4.6, 0.95, "", "Sharp change, well placed"), lk(1.8, 0.65, "bl-soft", "Gradual change"), lk(1.2, 0.4, "bl-blur", "Uncertain: thin data"));
      legend.querySelectorAll(".linekey svg").forEach((s) => { s.style.color = tokens.cat[1]; });
      legend.append(el("p", { class: "hint", text: shown.areaNote || (shown.surface ? `Region-wide: ${shown.surface.unit === "%" ? `${fmt(shown.surface.region_share)}%` : `${fmt(shown.surface.region_share)} per 1,000 reviews`}. Unshaded: about the region's level, or too little data.` : "Loading…") }));
      return;
    }
    if (d.kind === "score") {
      const choice = state.choice[d.id] ?? "all"; const what = choice === "all" ? d.title : d.id === "targeting" ? `Aimed at ${choice}` : d.id === "cultural" ? `${choice} identity` : meta.political_leans.find((l) => l.id === choice)?.label || d.title;
      legend.append(el("div", { class: "note", text: `${what}: 0 none to 5 strong${state.minScore > 0 ? ` · showing ${state.minScore} and above` : ""}` }), scale(tokens.score, ["0", "1", "2", "3", "4", "5"]),
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
    if (state.view === "areas" && (d.kind === "score" || d.kind === "area")) return;
    const box = el("details", { class: "more", open: state.topOpen, ontoggle: (e) => { state.topOpen = e.target.open; } }, el("summary", { text: { area: "Highest rates shown", filter: "Places meeting every condition" }[d.kind] || "Strongest shown" }));
    top.append(box); const append = (...n) => box.append(...n);
    if (!rows.length) { append(el("p", { class: "note", text: "Nothing to list with the current settings." })); return; }
    append(el("ul", { class: "toplist" }, ...rows.map((r) => el("li", {}, el("button", { type: "button", title: `Show on the map: ${r.text}`, onclick: () => map.flyTo(r.at, r.zoom) }, el("b", { text: fmt(r.value) }), el("span", { text: r.text }))))));
    const tail = d.kind === "filter" ? "Sorted by the first condition's score. " : "";
    append(el("p", { class: "hint", text: tail + (d.kind === "score" || d.kind === "filter" ? `Click a row to go there. Meetup venues are listed only with 5 or more events. Scale: ${SCORE_WORDS.map((w, i) => `${i} ${w}`).join(", ")}.` : "Click a row to go there.") }));
  }

  return { renderOptions, update(shown) { renderLegend(shown); renderTop(shown); } };
}
