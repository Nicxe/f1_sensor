// Shared, existing team identity and logo selection used by both card generations.
const TEAM_LOGO_URLS = {
  Alpine: 'https://media.formula1.com/image/upload/c_lfill,w_48/q_auto/v1740000000/common/f1/2025/alpine/2025alpinelogowhite.webp',
  'Aston Martin': 'https://media.formula1.com/image/upload/c_lfill,w_48/q_auto/v1740000000/common/f1/2025/astonmartin/2025astonmartinlogowhite.webp',
  Audi: 'https://media.formula1.com/image/upload/c_lfill,w_48/q_auto/v1740000000/common/f1/2026/audi/2026audilogowhite.webp',
  Cadillac: 'https://media.formula1.com/image/upload/c_lfill,w_48/q_auto/v1740000000/common/f1/2026/cadillac/2026cadillaclogowhite.webp',
  Ferrari: 'https://media.formula1.com/image/upload/c_lfill,w_48/q_auto/v1740000000/common/f1/2025/ferrari/2025ferrarilogolight.webp',
  Haas: 'https://media.formula1.com/image/upload/c_lfill,w_48/q_auto/v1740000000/common/f1/2025/haas/2025haaslogowhite.webp',
  'Kick Sauber': 'https://media.formula1.com/image/upload/c_fit,h_64/q_auto/v1740000000/common/f1/2025/kicksauber/2025kicksauberlogowhite.webp',
  McLaren: 'https://media.formula1.com/image/upload/c_lfill,w_48/q_auto/v1740000000/common/f1/2025/mclaren/2025mclarenlogowhite.webp',
  Mercedes: 'https://media.formula1.com/image/upload/c_lfill,w_48/q_auto/v1740000000/common/f1/2025/mercedes/2025mercedeslogowhite.webp',
  'Racing Bulls': 'https://media.formula1.com/image/upload/c_lfill,w_48/q_auto/v1740000000/common/f1/2025/racingbulls/2025racingbullslogowhite.webp',
  'Red Bull Racing': 'https://media.formula1.com/image/upload/c_lfill,w_48/q_auto/v1740000000/common/f1/2025/redbullracing/2025redbullracinglogowhite.webp',
  Williams: 'https://media.formula1.com/image/upload/c_lfill,w_48/q_auto/v1740000000/common/f1/2025/williams/2025williamslogowhite.webp',
};

const TEAM_LOGO_ALIASES = {
  alpine: 'Alpine',
  'aston martin': 'Aston Martin',
  astonmartin: 'Aston Martin',
  audi: 'Audi',
  cadillac: 'Cadillac',
  'cadillac f1': 'Cadillac',
  'cadillac f1 team': 'Cadillac',
  'cadillac ferrari': 'Cadillac',
  'cadillac formula 1 team': 'Cadillac',
  'general motors cadillac': 'Cadillac',
  ferrari: 'Ferrari',
  haas: 'Haas',
  mclaren: 'McLaren',
  mercedes: 'Mercedes',
  'mercedes-amg': 'Mercedes',
  'mercedes amg': 'Mercedes',
  'mercedes-amg petronas': 'Mercedes',
  'mercedes amg petronas': 'Mercedes',
  'mercedes-amg petronas f1 team': 'Mercedes',
  'mercedes amg petronas f1 team': 'Mercedes',
  'racing bulls': 'Racing Bulls',
  'visa cash app rb': 'Racing Bulls',
  'visa cash app rb f1 team': 'Racing Bulls',
  'rb f1 team': 'Racing Bulls',
  'rb': 'Racing Bulls',
  'kick sauber': 'Kick Sauber',
  'stake f1 team kick sauber': 'Kick Sauber',
  sauber: 'Kick Sauber',
  'red bull racing': 'Red Bull Racing',
  'red bull': 'Red Bull Racing',
  'oracle red bull racing': 'Red Bull Racing',
  'red bull racing honda': 'Red Bull Racing',
  'red bull racing honda rbpt': 'Red Bull Racing',
  'scuderia ferrari': 'Ferrari',
  'scuderia ferrari hp': 'Ferrari',
  'mclaren f1 team': 'McLaren',
  'aston martin aramco': 'Aston Martin',
  'aston martin aramco f1 team': 'Aston Martin',
  'bwt alpine f1 team': 'Alpine',
  'alpine f1 team': 'Alpine',
  'williams racing': 'Williams',
  'haas f1 team': 'Haas',
  'stake': 'Kick Sauber',
  'stake f1 team': 'Kick Sauber',
  'alphatauri': 'Racing Bulls',
  'scuderia alphatauri': 'Racing Bulls',
  'toro rosso': 'Racing Bulls',
  'alfa romeo': 'Kick Sauber',
  'alfa romeo f1 team': 'Kick Sauber',
  'renault': 'Alpine',
  'renault f1 team': 'Alpine',
  'force india': 'Aston Martin',
  'racing point': 'Aston Martin',
  williams: 'Williams',
};

const TEAM_LOGO_FORCE_WHITE = new Set(['Mercedes', 'Aston Martin', 'Audi', 'Cadillac']);

const toColorLogoUrl = (url) => {
  if (!url) return null;
  if (url.includes('logowhite')) return url.replace('logowhite', 'logo');
  if (url.includes('logolight')) return url.replace('logolight', 'logo');
  return url;
};

const normalizeTeamName = (team) => {
  if (!team) return null;
  const cleaned = String(team).toLowerCase().replace(/\s+/g, ' ').trim();
  if (TEAM_LOGO_ALIASES[cleaned]) return TEAM_LOGO_ALIASES[cleaned];
  const stripped = cleaned.replace(/[^a-z0-9 ]/g, '').trim();
  return TEAM_LOGO_ALIASES[stripped] || null;
};

const getTeamLogoUrl = (team, size = 28, variant = 'white') => {
  const key = normalizeTeamName(team);
  if (!key) return null;
  const base = TEAM_LOGO_URLS[key];
  if (!base) return null;
  const url = variant === 'color' ? toColorLogoUrl(base) : base;
  if (/w_\d+/.test(url)) {
    return url.replace(/w_\d+/, `w_${size}`);
  }
  if (/h_\d+/.test(url)) {
    return url.replace(/h_\d+/, `h_${Math.round(size * 1.2)}`);
  }
  return url;
};

const getTeamLogoMeta = (team, size = 28, style = 'color', preferColor = false) => {
  const key = normalizeTeamName(team);
  const whiteUrl = getTeamLogoUrl(team, size, 'white');
  if (!whiteUrl) return null;
  if (style === 'white' || (!preferColor && key && TEAM_LOGO_FORCE_WHITE.has(key))) {
    return { src: whiteUrl, fallback: null };
  }
  const colorUrl = getTeamLogoUrl(team, size, 'color');
  if (colorUrl && colorUrl !== whiteUrl) {
    return { src: colorUrl, fallback: whiteUrl };
  }
  return { src: whiteUrl, fallback: null };
};

const handleTeamLogoError = (ev) => {
  const img = ev.target;
  if (!img || !img.dataset) return;
  const fallback = img.dataset.fallback;
  if (fallback && img.src !== fallback) {
    img.src = fallback;
    return;
  }
  img.style.display = 'none';
};


export { normalizeTeamName, getTeamLogoMeta, handleTeamLogoError };
