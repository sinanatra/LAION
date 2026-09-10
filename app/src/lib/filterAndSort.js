export function filterItems(
  items,
  { query, scoreMode = "unsafe", minScore = 0, maxScore = 1 },
) {
  const q = query.trim().toLowerCase();
  const field = scoreMode === "watermark" ? "pwatermark" : "punsafe";
  return items.filter((item) => {
    const matchesQuery =
      !q ||
      item.caption.toLowerCase().includes(q) ||
      item.source_url.toLowerCase().includes(q);
    const withinScore =
      item[field] === undefined ||
      (item[field] >= minScore && item[field] <= maxScore);
    return matchesQuery && withinScore;
  });
}

const UNSAFE_BLUR_THRESHOLD = 0.1;

export function isFlaggedUnsafe(item) {
  return item.punsafe !== undefined && item.punsafe > UNSAFE_BLUR_THRESHOLD;
}

// Orders items by UMAP x/y in a snake/raster pattern (banded by y, alternating
// x direction per band) so neighbors in the list are neighbors in embedding
// space too — a gradient, not random adjacency. Items without coordinates
// (e.g. downloaded after the last embeddings/UMAP run) are appended at the
// end rather than breaking the gradient for everyone. Falls back to sorting
// by similarity score when no items have coordinates yet.
export function sortItems(matches) {
  const withCoords = matches.filter(
    (item) => item.x !== undefined && item.y !== undefined,
  );
  const withoutCoords = matches.filter(
    (item) => item.x === undefined || item.y === undefined,
  );

  if (withCoords.length > 0) {
    const numBands = Math.max(1, Math.round(Math.sqrt(withCoords.length)));
    const banded = withCoords.map((item) => ({
      item,
      band: Math.min(numBands - 1, Math.floor(item.y * numBands)),
    }));
    banded.sort((a, b) => {
      if (a.band !== b.band) return a.band - b.band;
      const direction = a.band % 2 === 0 ? 1 : -1;
      return direction * (a.item.x - b.item.x);
    });
    return [...banded.map((entry) => entry.item), ...withoutCoords];
  }

  const withSimilarity = matches.filter(
    (item) => item.similarity !== undefined && item.similarity !== null,
  );
  const withoutSimilarity = matches.filter(
    (item) => item.similarity === undefined || item.similarity === null,
  );
  withSimilarity.sort((a, b) => b.similarity - a.similarity);
  return [...withSimilarity, ...withoutSimilarity];
}
