import Fuse from "fuse.js";

const byNewest = (a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || "");

// Words that carry no meaning in a workbook search.
const FILLER = new Set(["the", "and", "for", "show", "open", "please", "sigma", "workbook", "workbooks", "dashboard"]);

function searchWords(text) {
  const all = text.toLowerCase().split(/[^\p{L}\p{N}&]+/u).filter(Boolean);
  const meaningful = all.filter((word) => word.length >= 3 && !FILLER.has(word));
  return meaningful.length ? meaningful : all;
}

function makeFuse(workbooks) {
  return new Fuse(workbooks, {
    keys: [
      { name: "name", weight: 0.8 },
      { name: "path", weight: 0.2 },
    ],
    threshold: 0.4,
    ignoreLocation: true,
    includeScore: true,
    minMatchCharLength: 2,
  });
}

// Fuzzy-matches workbook names (and paths) and ranks the best matches first.
// With no query, returns the most recently updated workbooks. When the whole
// phrase finds nothing, each word is matched on its own, so word order does
// not matter and a few extra words do not hide the right workbook.
export function searchWorkbooks(workbooks, query, limit = 20) {
  const active = workbooks.filter((workbook) => !workbook.archived);
  const text = (query || "").trim();

  if (!text) return [...active].sort(byNewest).slice(0, limit);

  const fuse = makeFuse(active);
  const whole = fuse.search(text);
  if (whole.length) {
    return whole
      .sort((a, b) => a.score - b.score || byNewest(a.item, b.item))
      .slice(0, limit)
      .map(({ item, score }) => ({ ...item, score: Number(score.toFixed(3)) }));
  }

  const words = searchWords(text);
  if (words.length < 2) return [];

  const hits = new Map();
  for (const word of words) {
    for (const { item, score } of fuse.search(word)) {
      const entry = hits.get(item) || { item, scores: [] };
      entry.scores.push(score);
      hits.set(item, entry);
    }
  }

  return [...hits.values()]
    .map(({ item, scores }) => ({
      item,
      coverage: scores.length / words.length,
      score: scores.reduce((sum, value) => sum + value, 0) / scores.length,
    }))
    .filter((entry) => entry.coverage >= 0.5)
    .sort((a, b) => b.coverage - a.coverage || a.score - b.score || byNewest(a.item, b.item))
    .slice(0, limit)
    .map(({ item, score, coverage }) => ({ ...item, score: Number((score + (1 - coverage) * 0.5).toFixed(3)) }));
}

// True when one workbook is clearly the match, so it can be opened without
// asking. Otherwise the user should be asked to choose.
export function hasClearMatch(results) {
  if (results.length === 1) return true;
  if (results.length < 2 || results[0].score === undefined) return false;
  return results[0].score <= 0.1 && results[1].score - results[0].score >= 0.1;
}
