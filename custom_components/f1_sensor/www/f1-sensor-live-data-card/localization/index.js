const cacheSuffix = new URL(import.meta.url).search;
const injectedLocales = new URL(import.meta.url).protocol === 'file:'
  ? globalThis.__F1_SENSOR_LOCALES__
  : undefined;

const localeUrl = language => {
  const url = new URL(`./locales/${language}.json`, import.meta.url);
  url.search = cacheSuffix;
  return url;
};

const loadMessages = async language => {
  if (injectedLocales?.[language]) return injectedLocales[language];
  const url = localeUrl(language);
  if (url.protocol === 'file:') {
    const { readFile } = await import('node:fs/promises');
    const fileUrl = new URL(url);
    fileUrl.search = '';
    return JSON.parse(await readFile(fileUrl, 'utf8'));
  }
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Could not load F1 Sensor ${language} translations (${response.status})`);
  }
  return response.json();
};

const availableLocaleCodes = async () => {
  if (injectedLocales) return Object.keys(injectedLocales);
  if (new URL(import.meta.url).protocol === 'file:') {
    const { readdir } = await import('node:fs/promises');
    return (await readdir(new URL('./locales/', import.meta.url)))
      .filter(filename => filename.endsWith('.json'))
      .map(filename => filename.slice(0, -5));
  }
  const manifestUrl = new URL('./available-locales.json', import.meta.url);
  manifestUrl.search = cacheSuffix;
  const response = await fetch(manifestUrl);
  if (!response.ok) throw new Error(`Could not load F1 Sensor locale manifest (${response.status})`);
  const languages = await response.json();
  if (!Array.isArray(languages) || languages.some(language => !/^[a-z]{2,3}$/.test(language))) {
    throw new Error('F1 Sensor locale manifest is invalid');
  }
  return languages;
};

const [{ LEGACY }, languages] = await Promise.all([
  import(`./legacy.js${cacheSuffix}`),
  availableLocaleCodes(),
]);
const localeEntries = await Promise.all(
  [...new Set(['en', ...languages])].sort().map(async language => [
    language,
    Object.freeze(await loadMessages(language)),
  ]),
);

export const LOCALES = Object.freeze(Object.fromEntries(localeEntries));

export const languageCode = language => String(language || 'en')
  .toLowerCase()
  .split('-', 1)[0];

const supportedLanguage = language => {
  const code = languageCode(language);
  return Object.hasOwn(LOCALES, code) ? code : 'en';
};

const interpolate = (template, replacements) => Object.entries(replacements).reduce(
  (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
  template,
);

export const translate = (language, key, replacements = {}) => {
  const code = supportedLanguage(language);
  const template = LOCALES[code][key] ?? LOCALES.en[key] ?? key;
  return interpolate(template, replacements);
};

export const translatePlural = (language, key, count, replacements = {}) => {
  const code = supportedLanguage(language);
  const category = new Intl.PluralRules(code).select(Number(count));
  const categoryKey = `${key}.${category}`;
  const fallbackKey = `${key}.other`;
  const resolvedKey = LOCALES[code][categoryKey] !== undefined
    || LOCALES.en[categoryKey] !== undefined
    ? categoryKey
    : fallbackKey;
  return translate(code, resolvedKey, { count, ...replacements });
};

const sourceKeyMap = prefix => new Map(
  Object.entries(LOCALES.en)
    .filter(([key]) => key.startsWith(prefix))
    .map(([key, value]) => [value, key]),
);

const PLATFORM_SOURCE_KEYS = sourceKeyMap('legacy.platform.');
const MODULAR_SOURCE_KEYS = Object.entries(LOCALES.en)
  .filter(([key]) => key.startsWith('legacy.modular.') || key.startsWith('modular.') || key.startsWith('legacy.platform.'))
  .reduce((keys, [key, value]) => keys.set(value, [...(keys.get(value) ?? []), key]), new Map());
const WIND_PATTERN = /^([\d.,]+ \S+) (N|NE|E|SE|S|SW|W|NW)([↓↙←↖↑↗→↘]?)$/;

const translatePattern = (language, value) => {
  const code = supportedLanguage(language);
  for (const [source, replacement] of LEGACY[code]?.patterns ?? []) {
    const pattern = new RegExp(source);
    if (pattern.test(value)) return value.replace(pattern, replacement);
  }
  const wind = WIND_PATTERN.exec(value);
  if (wind) {
    const [, speed, direction, arrow] = wind;
    const translatedDirection = LEGACY[code]?.windDirections?.[direction] ?? direction;
    return `${speed} ${translatedDirection}${arrow}`;
  }
  return value;
};

// Catalog metadata keeps only English source text. Resolve it through the
// English Weblate catalog so every target language remains file-owned.
export const translateSourceText = (language, english) => {
  const code = supportedLanguage(language);
  if (code === 'en') return english;
  const candidates = MODULAR_SOURCE_KEYS.get(english) ?? [];
  const key = candidates.find(candidate => LOCALES[code][candidate] !== undefined && LOCALES[code][candidate] !== english)
    ?? candidates.find(candidate => LOCALES[code][candidate] !== undefined)
    ?? candidates[0];
  if (key) return translate(code, key);
  return translatePattern(code, english);
};

// Legacy specialized cards render English text internally. Keep this bridge
// scoped to those cards until their backwards-compatible lifecycle ends.
export const translateLegacyText = (language, value) => {
  const code = supportedLanguage(language);
  if (code === 'en') return value;
  const key = PLATFORM_SOURCE_KEYS.get(value);
  if (key) return translate(code, key);
  return translatePattern(code, value);
};

export const cardStrings = language => {
  const code = supportedLanguage(language);
  return Object.fromEntries(
    Object.entries(LOCALES.en).filter(([key]) => (
      key.startsWith('card.')
      || key.startsWith('a11y.')
      || key.startsWith('track_map.')
      || key.startsWith('race_control.')
    )).map(([key, fallback]) => [key, LOCALES[code][key] ?? fallback]),
  );
};

export const legacyTextTranslations = language => {
  const code = supportedLanguage(language);
  return Object.fromEntries(
    [...PLATFORM_SOURCE_KEYS].map(([source, key]) => [source, LOCALES[code][key] ?? LOCALES.en[key]]),
  );
};
