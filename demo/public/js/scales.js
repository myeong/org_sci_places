// Colour is assigned by the job it does: identity (categories), magnitude (scores, rates).
// Values come from the CSS tokens so light and dark mode stay in one place (css/app.css).
import { RATE_BREAKS } from "./config.js";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export function readTokens() {
  return {
    cat: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => css(`--c${i}`)), other: css("--c-other"),
    score: [0, 1, 2, 3, 4, 5].map((i) => css(`--s${i}`)), rate: [0, 1, 2, 3, 4, 5].map((i) => css(`--r${i}`)),
    ring: css("--ring"), ink: css("--ink"), areaLow: css("--area-low"),
  };
}

// Categories keep their slot whatever is filtered: colour follows the entity, never its rank.
export function categoryColor(tokens, list, name) {
  const i = list.indexOf(name);
  return i >= 0 && i < 8 ? tokens.cat[i] : tokens.other;
}

export const scoreBin = (v) => Math.max(0, Math.min(5, Math.round(v)));
export const scoreColor = (tokens, v) => tokens.score[scoreBin(v)];

export function rateBin(rate) {
  if (!(rate > 0)) return 0;
  let b = 1;
  while (b < RATE_BREAKS.length && rate > RATE_BREAKS[b]) b++;
  return b;
}
export const rateColor = (tokens, rate) => tokens.rate[rateBin(rate)];
