export const SIGNALS = {
  overall: { symbol: '◆', label: { en: 'Overall fastest', sv: 'Snabbast totalt' } },
  personal: { symbol: '●', label: { en: 'Personal best', sv: 'Personbästa' } },
  timed: { symbol: '■', label: { en: 'Recorded time', sv: 'Registrerad tid' } },
  previous: { symbol: '↶', label: { en: 'Previous lap', sv: 'Föregående varv' } },
  deleted: { symbol: '×', label: { en: 'Deleted time', sv: 'Raderad tid' } },
  invalid: { symbol: '!', label: { en: 'Invalid time', sv: 'Ogiltig tid' } },
  unknown: { symbol: '–', label: { en: 'Not available', sv: 'Uppgift saknas' } },
};
export const PALETTES = {
  dark: { overall: '#c59aff', personal: '#75dc94', timed: '#f6d65c', previous: '#bdc3ce', deleted: '#ffb3b3', invalid: '#ffb3b3', unknown: '#bdc3ce' },
  light: { overall: '#7335a6', personal: '#176b36', timed: '#745900', previous: '#525a67', deleted: '#ab2424', invalid: '#ab2424', unknown: '#525a67' },
};

export function number(value) {
  if (value === null || value === undefined || typeof value === 'boolean' || (typeof value === 'string' && !value.trim())) return null;
  if (!['number', 'string'].includes(typeof value)) return null;
  const result = Number(value);
  return Number.isFinite(result) ? result : null;
}
export function positiveInteger(value) {
  const result = number(value); return Number.isInteger(result) && result > 0 ? result : null;
}
export function seconds(value) {
  if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? value : null;
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (!/^\d+(?::\d{1,2}){0,2}(?:\.\d+)?$/.test(text)) return null;
  const parts = text.split(':').map(Number);
  if (parts.slice(1).some(part => part >= 60)) return null;
  const result = parts.reduce((total, part) => total * 60 + part, 0);
  return result > 0 ? result : null;
}
export function formatTime(value) {
  const time = seconds(value); if (time === null) return '—';
  const ms = Math.round(time * 1000), minutes = Math.floor(ms / 60000), remainder = ms % 60000;
  const tail = `${Math.floor(remainder / 1000).toString().padStart(minutes ? 2 : 1, '0')}.${(remainder % 1000).toString().padStart(3, '0')}`;
  return minutes ? `${minutes}:${tail}` : tail;
}

export function timingStatus(value) {
  if (value?.deleted === true) return 'deleted';
  if (value?.invalid === true) return 'invalid';
  if (seconds(value?.time) === null) return 'unknown';
  if (value?.previous_lap || value?.source === 'previous_lap') return 'previous';
  if (value?.overall_fastest === true) return 'overall';
  if (value?.personal_fastest === true) return 'personal';
  return 'timed';
}

export function lapChange(current, previous, currentLap, previousLap) {
  const a = seconds(current), b = seconds(previous);
  if (a === null || b === null) return null;
  const delta = Math.round((a - b) * 1000) / 1000;
  return { value: delta, symbol: delta < 0 ? '▼' : delta > 0 ? '▲' : '=', status: delta < 0 ? 'faster' : delta > 0 ? 'slower' : 'equal', comparison: 'previous_completed_lap', current_lap: currentLap ?? null, reference_lap: previousLap ?? null };
}
export function positionChange(current, reference, basis = 'grid') {
  const a = positiveInteger(current), b = positiveInteger(reference);
  if (a === null || b === null) return null;
  const gain = b - a;
  return { value: gain, symbol: gain > 0 ? '↑' : gain < 0 ? '↓' : '=', status: gain > 0 ? 'gain' : gain < 0 ? 'loss' : 'equal', comparison: basis };
}
export function formatDelta(value) {
  const delta = number(value); return delta === null ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(3)}`;
}

const emptySector = lap => ({ time: null, lap: lap ?? null, source: null, overall_fastest: false, personal_fastest: false, previous_lap: false });
export function readSectors(driver) {
  const current = driver?.sectors?.current;
  const zeroBased = current && Object.hasOwn(current, '0');
  return [1, 2, 3].map(n => {
    const raw = current?.[`sector_${n}`] ?? current?.[String(zeroBased ? n - 1 : n)];
    const detail = raw && typeof raw === 'object' ? raw : null;
    const time = seconds(detail ? detail.time : driver?.[`sector_${n}`]);
    return {
      time, lap: positiveInteger(detail?.lap ?? driver?.[`sector_${n}_lap`]),
      source: time === null ? null : String(detail?.source ?? driver?.[`sector_${n}_source`] ?? 'current'),
      overall_fastest: (detail?.overall_fastest ?? driver?.[`sector_${n}_overall_fastest`]) === true,
      personal_fastest: (detail?.personal_fastest ?? driver?.[`sector_${n}_personal_fastest`]) === true,
      deleted: detail?.deleted === true, invalid: detail?.invalid === true,
      supplied: detail !== null || Object.hasOwn(driver ?? {}, `sector_${n}`),
    };
  });
}

// Bounded cache per driver. The owner supplies a session/replay generation key;
// changing it discards prior-session sectors even when racing numbers are reused.
export class SectorStore {
  constructor() { this.context = null; this.drivers = new Map(); }
  reset(context = null) { this.context = context; this.drivers.clear(); }
  select(context, driver, mode = 'coherent') {
    if (context !== this.context) this.reset(context);
    const key = String(driver?.racing_number ?? driver?.tla ?? '');
    const direct = readSectors(driver);
    if (!key) return direct;
    const explicitLap = positiveInteger(driver?.sector_current_lap ?? driver?.sectors?.current_lap);
    const directLaps = direct.map(item => item.lap).filter(lap => lap !== null);
    const seenLap = directLaps.length ? Math.max(...directLaps) : explicitLap;
    let cache = this.drivers.get(key);
    if (!cache || (seenLap !== null && cache.seenLap !== null && seenLap < cache.seenLap)) {
      cache = { laps: new Map(), unscoped: [null, null, null], seenLap: null, selectedLap: null };
      this.drivers.set(key, cache);
    }
    const state = String(driver?.sector_state ?? driver?.sectors?.state ?? '').toLowerCase();
    if (seenLap !== null) cache.seenLap = seenLap;
    if (state === 's1_done' && direct[0].time !== null) cache.unscoped = [null, null, null];
    direct.forEach((item, index) => {
      if (!item.supplied) return;
      // A sector without a lap cannot safely inherit another sector's lap.
      const lap = item.lap ?? (directLaps.length === 0 ? explicitLap : null);
      if (lap !== null) {
        if (!cache.laps.has(lap)) cache.laps.set(lap, [null, null, null]);
        cache.laps.get(lap)[index] = { ...item, lap };
      } else cache.unscoped[index] = { ...item };
    });
    if (direct[0].time !== null && direct[0].lap !== null) cache.selectedLap = direct[0].lap;
    else if (cache.selectedLap === null && seenLap !== null) cache.selectedLap = seenLap;
    else if (state === 's1_done' && seenLap !== null) cache.selectedLap = seenLap;
    const laps = [...cache.laps.keys()].sort((a, b) => a - b);
    while (laps.length > 3) cache.laps.delete(laps.shift());
    // No driver count assumption; bound inactive identities in malformed streams.
    if (this.drivers.size > 200) this.drivers.delete(this.drivers.keys().next().value);
    const complete = positiveInteger(driver?.completed_laps);
    const finish = (item, lap) => {
      if (!item) return emptySector(lap);
      const previous = item.source === 'previous_lap' || (item.lap !== null && complete !== null && item.lap <= complete) || (state === 'lap_complete' && (seenLap === null || item.lap === seenLap));
      return { ...item, previous_lap: previous, source: previous ? 'previous_lap' : item.source };
    };
    if (mode === 'latest' && cache.laps.size) {
      return [0, 1, 2].map(index => {
        for (const lap of [...cache.laps.keys()].sort((a, b) => b - a)) {
          const item = cache.laps.get(lap)[index];
          if (item?.time !== null && item) return finish(item, lap);
        }
        return emptySector(null);
      });
    }
    const selected = cache.selectedLap !== null ? cache.laps.get(cache.selectedLap) : cache.unscoped;
    return (selected ?? [null, null, null]).map(item => finish(item, cache.selectedLap));
  }
}

function luminance(hex) {
  if (!/^#[0-9a-f]{6}$/i.test(hex)) throw new TypeError('Expected a six-digit hex color');
  const channels = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}
export function contrast(a, b) { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
export function ink(background) { return contrast(background, '#000000') >= contrast(background, '#ffffff') ? '#000000' : '#ffffff'; }
export function statusColors(status, mode = 'dark', custom = {}) {
  const background = custom[status] ?? PALETTES[mode]?.[status] ?? PALETTES.dark.unknown;
  return { background, color: ink(background) };
}
// Decorative appearance never modifies semantic timing/flag palettes.
export function cardAccent(appearance, teams = [], mode = 'dark') {
  const kind = appearance.accent_mode ?? 'style';
  const teamColor = teams.find(team => team.name === appearance.accent_team)?.color;
  const knownTeamColor = typeof teamColor === 'string' && /^#[0-9a-f]{6}$/i.test(teamColor) ? teamColor : null;
  const neutral = mode === 'light' ? '#778397' : '#637083';
  return {
    color: kind === 'team' ? knownTeamColor ?? neutral : kind === 'neutral' ? neutral : kind === 'f1' ? '#e10600' : appearance.accent,
    visible: kind === 'style' ? appearance.style === 'f1' : kind !== 'neutral',
    missingTeamColor: kind === 'team' && !knownTeamColor,
  };
}
export function logoDimensions(size = 'normal') {
  const [frame, image, request] = size === 'small' ? [24, 18, 48] : size === 'large' ? [40, 34, 72] : [32, 26, 48];
  return { frame, image, request };
}
export function safeImageUrl(value) {
  if (typeof value !== 'string' || !value.trim() || /[\u0000-\u0020\\]/.test(value)) return null;
  if (value.startsWith('/') && !value.startsWith('//')) return value;
  try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; } catch { return null; }
}


const COMPOUNDS = {
  SOFT: { letter: 'S', color: '#ff3b30', label: { en: 'Soft', sv: 'Mjukt' }, asset: 'soft_tyre.png' },
  MEDIUM: { letter: 'M', color: '#ffd60a', label: { en: 'Medium', sv: 'Medium' }, asset: 'medium_tyre.png' },
  HARD: { letter: 'H', color: '#e5e5e5', label: { en: 'Hard', sv: 'Hårt' }, asset: 'hard_tyre.png' },
  INTERMEDIATE: { letter: 'I', color: '#34c759', label: { en: 'Intermediate', sv: 'Intermediate' }, asset: 'intermediate_tyre.png' },
  WET: { letter: 'W', color: '#0a84ff', label: { en: 'Wet', sv: 'Regndäck' }, asset: 'wet_tyre.png' },
};
export function compoundMeta(value) {
  const raw = typeof value === 'string' ? value.trim().toUpperCase() : '';
  const key = ({ S: 'SOFT', M: 'MEDIUM', H: 'HARD', I: 'INTERMEDIATE', INTER: 'INTERMEDIATE', W: 'WET', 'FULL WET': 'WET', FULLWET: 'WET' })[raw] ?? raw;
  // Never invent a compound or silently make an unknown compound a hard tyre.
  return COMPOUNDS[key] ? { key, ...COMPOUNDS[key] } : { key: null, letter: '?', color: null, asset: null, label: { en: raw || 'Unknown compound', sv: raw || 'Okänd compound' } };
}
const TRACK_SIGNALS = {
  CLEAR: { symbol: '✓', color: '#238644', label: { en: 'Track clear', sv: 'Banan fri' } },
  YELLOW: { symbol: '⚑', color: '#f0c632', label: { en: 'Yellow flag', sv: 'Gul flagg' } },
  DOUBLE_YELLOW: { symbol: '⚑⚑', color: '#f0c632', label: { en: 'Double yellow flags', sv: 'Dubbla gula flaggor' } },
  RED: { symbol: '⚑', color: '#d93636', label: { en: 'Red flag', sv: 'Röd flagg' } },
  SC: { symbol: 'SC', color: '#f0c632', label: { en: 'Safety Car', sv: 'Safety Car' } },
  VSC: { symbol: 'VSC', color: '#f0c632', label: { en: 'Virtual Safety Car', sv: 'Virtuell Safety Car' } },
  BLUE: { symbol: '⚑', color: '#3978d5', label: { en: 'Blue flag', sv: 'Blå flagg' } },
  CHEQUERED: { symbol: '▦', color: '#ffffff', label: { en: 'Chequered flag', sv: 'Målflagg' } },
};
export function trackSignal(value) {
  const raw = typeof value === 'string' ? value.trim().toUpperCase().replaceAll(' ', '_') : '';
  const key = ({ GREEN: 'CLEAR', CHECKERED: 'CHEQUERED', SAFETY_CAR: 'SC' })[raw] ?? raw;
  return TRACK_SIGNALS[key] ? { key, ...TRACK_SIGNALS[key], ink: ink(TRACK_SIGNALS[key].color) } : null;
}
