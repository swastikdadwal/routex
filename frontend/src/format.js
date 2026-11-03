export const SHORT_NAMES = {
  greedy: 'Greedy',
  dp: 'DP',
  brute: 'Brute',
  bnb: 'B&B',
  approx: 'Approx.',
};

export const SOURCE_NAMES = {
  osrm: 'OSRM road network',
  dijkstra: 'Dijkstra on OpenStreetMap roads',
  straight: 'Straight line',
};

export const ACTIVE_RUN_STATES = ['pending', 'distances', 'solving'];

export const km = (metres) => `${(metres / 1000).toFixed(2)} km`;

export function formatMs(ms) {
  if (ms == null) return '–';
  if (ms < 0.1) return `${ms.toFixed(3)} ms`;
  if (ms < 10) return `${ms.toFixed(2)} ms`;
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatTick(ms) {
  if (ms >= 1000) return `${ms / 1000} s`;
  return `${ms} ms`;
}

export function formatCount(value) {
  if (value == null) return '–';
  return new Intl.NumberFormat('en', {
    notation: value >= 100000 ? 'compact' : 'standard',
    maximumFractionDigits: 1,
  }).format(value);
}

export const seriesColor = (index) => `var(--series-${(index % 8) + 1})`;
// White on every series colour except yellow, per the palette's fill-label rule.
export const seriesInk = (index) => (index % 8 === 3 ? '#0b0b0b' : '#ffffff');

export const isComplete = (result) => result.distance_m != null;

export function powerTicks(values) {
  const positive = values.filter((v) => v != null && v > 0);
  if (positive.length === 0) return [1];
  const low = Math.floor(Math.log10(Math.min(...positive)));
  const high = Math.ceil(Math.log10(Math.max(...positive)));
  const ticks = [];
  for (let p = low; p <= Math.max(high, low + 1); p += 1) ticks.push(Number((10 ** p).toPrecision(1)));
  return ticks;
}
