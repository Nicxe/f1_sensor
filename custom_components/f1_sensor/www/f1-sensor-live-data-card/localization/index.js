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

const [englishMessages, swedishMessages, dutchMessages, { LEGACY }] = await Promise.all([
  loadMessages('en'),
  loadMessages('sv'),
  loadMessages('nl'),
  import(`./legacy.js${cacheSuffix}`),
]);

export const LOCALES = Object.freeze({
  en: Object.freeze(englishMessages),
  sv: Object.freeze(swedishMessages),
  nl: Object.freeze(dutchMessages),
});

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

const MODULAR_SOURCE_KEYS = new Map([
  ...sourceKeyMap('legacy.modular.'),
  ...sourceKeyMap('modular.'),
]);
const PLATFORM_SOURCE_KEYS = sourceKeyMap('legacy.platform.');
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

// Compatibility for catalog labels that still carry their English source text.
// New UI messages must call translate() with a stable key instead.
export const translateLegacy = (language, english, swedish = english) => {
  const code = supportedLanguage(language);
  if (code === 'en') return english;
  if (code === 'sv' && swedish !== english) return swedish;
  const key = MODULAR_SOURCE_KEYS.get(english);
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
    Object.entries(LOCALES[code]).filter(([key]) => (
      key.startsWith('card.')
      || key.startsWith('a11y.')
      || key.startsWith('track_map.')
      || key.startsWith('race_control.')
    )),
  );
};

export const legacyTextTranslations = language => {
  const code = supportedLanguage(language);
  return Object.fromEntries(
    [...PLATFORM_SOURCE_KEYS].map(([source, key]) => [source, LOCALES[code][key]]),
  );
};
