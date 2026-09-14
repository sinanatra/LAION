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

const UNSAFE_BLUR_THRESHOLD = 0.05;

export function isFlaggedUnsafe(item) {
  return item.punsafe !== undefined && item.punsafe > UNSAFE_BLUR_THRESHOLD;
}

function hilbertRotate(n, x, y, rx, ry) {
  if (ry !== 0) return [x, y];
  if (rx === 1) {
    x = n - 1 - x;
    y = n - 1 - y;
  }
  return [y, x];
}

const HILBERT_N = 1 << 16; // grid resolution per axis (65536)

function hilbertDistance(x, y) {
  let ix = Math.min(HILBERT_N - 1, Math.floor(x * HILBERT_N));
  let iy = Math.min(HILBERT_N - 1, Math.floor(y * HILBERT_N));
  let d = 0;
  for (let s = HILBERT_N / 2; s > 0; s = Math.floor(s / 2)) {
    const rx = (ix & s) > 0 ? 1 : 0;
    const ry = (iy & s) > 0 ? 1 : 0;
    d += s * s * ((3 * rx) ^ ry);
    [ix, iy] = hilbertRotate(HILBERT_N, ix, iy, rx, ry);
  }
  return d;
}

export function sortItems(matches) {
  const withCoords = matches.filter(
    (item) => item.x !== undefined && item.y !== undefined,
  );
  const withoutCoords = matches.filter(
    (item) => item.x === undefined || item.y === undefined,
  );

  if (withCoords.length > 0) {
    const sorted = [...withCoords].sort(
      (a, b) => hilbertDistance(a.x, a.y) - hilbertDistance(b.x, b.y),
    );
    return [...sorted, ...withoutCoords];
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
