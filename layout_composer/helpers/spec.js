const { presets } = require('./presets');

// A styled title comes back as { text, fontWeight, fontSize } instead of a plain string.
const elementName = (el) => (typeof el.name === 'string' ? el.name : (el.name && el.name.text) || el.id);

// Library elements are the elements placed on the first page of the library workbook.
function listLibraryElements(doc) {
  const firstPage = doc.layout.split('<Page ')[1];
  const ids = [...firstPage.matchAll(/elementId="([^"]+)"/g)].map((m) => m[1]);
  return ids.map((id) => {
    const el = doc.elements.find((e) => e.id === id);
    return { id, name: elementName(el), kind: el.kind };
  });
}

// Keep the placed elements plus anything they use as a source (for example the Source page table).
function neededElementIds(doc, placedIds) {
  const needed = new Set(placedIds);
  let grew = true;
  while (grew) {
    grew = false;
    for (const el of doc.elements) {
      if (!needed.has(el.id)) continue;
      const dep = el.source && el.source.elementId;
      if (dep && !needed.has(dep)) {
        needed.add(dep);
        grew = true;
      }
    }
  }
  return needed;
}

// placements: { [zoneIndex]: elementId }
function buildDocument(libraryDoc, presetId, placements) {
  const preset = presets.find((p) => p.id === presetId);
  if (!preset) throw new Error(`Unknown preset: ${presetId}`);

  const placed = Object.entries(placements).filter(([zone]) => preset.zones[zone]);
  const libraryIds = new Set(listLibraryElements(libraryDoc).map((e) => e.id));
  const placedIds = placed.map(([, id]) => id);
  if (placedIds.some((id) => !libraryIds.has(id))) throw new Error('Unknown library element');

  const keep = neededElementIds(libraryDoc, placedIds);
  const [canvasBlock, ...otherBlocks] = libraryDoc.layout
    .split('<Page ')
    .slice(1)
    .map((b) => '<Page ' + b.replace(/\s+$/, ''));

  const leaves = placed
    .map(([zone, id]) => {
      const [c1, c2, r1, r2] = preset.zones[zone];
      return `  <Element elementId="${id}" gridColumn="${c1} / ${c2}" gridRow="${r1} / ${r2}"/>`;
    })
    .join('\n');
  const canvasOpen = canvasBlock.match(/<Page [^>]*>/)[0];

  const canvasPageId = canvasOpen.match(/id="([^"]+)"/)[1];

  // Keep a supporting page (such as Source) only if every element on it is kept;
  // a layout that references a removed element is rejected.
  const keptBlocks = otherBlocks.filter((block) =>
    [...block.matchAll(/elementId="([^"]+)"/g)].every((m) => keep.has(m[1]))
  );
  const keptPageIds = new Set(keptBlocks.map((block) => block.match(/id="([^"]+)"/)[1]));
  const pages = libraryDoc.pages
    .filter((pg) => pg.id === canvasPageId || keptPageIds.has(pg.id))
    .map((pg) => (pg.id === canvasPageId ? { ...pg, name: 'Layout Composer' } : { ...pg, visibility: 'hidden' }));

  return {
    ...libraryDoc,
    pages,
    elements: libraryDoc.elements.filter((e) => keep.has(e.id)),
    layout: ['<?xml version="1.0" encoding="utf-8"?>', `${canvasOpen}\n${leaves}\n</Page>`, ...keptBlocks].join('\n'),
  };
}

module.exports = { listLibraryElements, buildDocument };
