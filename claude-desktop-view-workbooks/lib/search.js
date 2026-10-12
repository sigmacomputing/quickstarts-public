import Fuse from "fuse.js";

const byNewest = (a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || "");

// Fuzzy-matches workbook names (and paths) and ranks the best matches first.
// With no query, returns the most recently updated workbooks.
export function searchWorkbooks(workbooks, query, limit = 20) {
  const active = workbooks.filter((workbook) => !workbook.archived);
  const text = (query || "").trim();

  if (!text) return [...active].sort(byNewest).slice(0, limit);

  const fuse = new Fuse(active, {
    keys: [
      { name: "name", weight: 0.8 },
      { name: "path", weight: 0.2 },
    ],
    threshold: 0.4,
    ignoreLocation: true,
    includeScore: true,
    minMatchCharLength: 2,
  });

  return fuse
    .search(text)
    .sort((a, b) => a.score - b.score || byNewest(a.item, b.item))
    .slice(0, limit)
    .map(({ item, score }) => ({ ...item, score: Number(score.toFixed(3)) }));
}

// True when one workbook is clearly the match, so it can be opened without
// asking. Otherwise the user should be asked to choose.
export function hasClearMatch(results) {
  if (results.length === 1) return true;
  if (results.length < 2 || results[0].score === undefined) return false;
  return results[0].score <= 0.1 && results[1].score - results[0].score >= 0.1;
}
