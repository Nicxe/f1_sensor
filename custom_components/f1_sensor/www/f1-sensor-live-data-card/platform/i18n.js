const cacheSuffix = new URL(import.meta.url).search;
const localization = await import(`../localization/index.js${cacheSuffix}`);

const {
  LOCALES,
  cardStrings,
  legacyTextTranslations,
  translate,
  translateLegacyText,
} = localization;

export const STRINGS = Object.freeze({
  en: Object.freeze(cardStrings('en')),
  sv: Object.freeze(cardStrings('sv')),
  nl: Object.freeze(cardStrings('nl')),
});

export const FRONTEND_TEXT_TRANSLATIONS = Object.freeze({
  sv: Object.freeze(legacyTextTranslations('sv')),
  nl: Object.freeze(legacyTextTranslations('nl')),
});

const languageFor = hass => String(hass?.locale?.language || hass?.language || 'en')
  .toLowerCase()
  .split('-', 1)[0];

const interpolate = (template, replacements) => Object.entries(replacements).reduce(
  (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
  template,
);

export const f1Translate = (hass, key, fallback = key, replacements = {}) => {
  const language = languageFor(hass);
  if (LOCALES[language]?.[key] !== undefined || LOCALES.en[key] !== undefined) {
    return translate(language, key, replacements);
  }
  return interpolate(fallback, replacements);
};

export const f1FormatNumber = (hass, value, options = {}) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  if (typeof hass?.formatNumber === 'function') {
    try {
      return hass.formatNumber(number, options);
    } catch (_err) {
      // Fall back to Intl for older Home Assistant frontends.
    }
  }
  return new Intl.NumberFormat(hass?.locale?.language || undefined, options).format(number);
};

export const f1FormatDateTime = (hass, date, options = {}) => {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '--';
  const timeZone = hass?.locale?.time_zone || hass?.config?.time_zone;
  return new Intl.DateTimeFormat(hass?.locale?.language || undefined, {
    ...(timeZone ? { timeZone } : {}),
    ...options,
  }).format(date);
};

export const f1TranslateText = (hass, value) => translateLegacyText(languageFor(hass), value);

export const localizeF1RenderRoot = (hass, root) => {
  if (!root || languageFor(hass) === 'en') return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    if (['SCRIPT', 'STYLE'].includes(node.parentElement?.tagName)) continue;
    const value = node.textContent;
    const trimmed = value?.trim();
    if (!trimmed) continue;
    const translated = f1TranslateText(hass, trimmed);
    if (translated !== trimmed) node.textContent = value.replace(trimmed, translated);
  }
  root.querySelectorAll?.('[aria-label], [title], [placeholder]').forEach(element => {
    for (const attribute of ['aria-label', 'title', 'placeholder']) {
      const value = element.getAttribute(attribute);
      if (value) element.setAttribute(attribute, f1TranslateText(hass, value));
    }
  });
};

export const installF1FrontendLocalization = ElementClass => {
  if (!ElementClass || ElementClass.prototype.__f1LocalizationInstalled) return;
  ElementClass.prototype.__f1LocalizationInstalled = true;
  const originalUpdated = ElementClass.prototype.updated;
  ElementClass.prototype.updated = function (...args) {
    originalUpdated?.apply(this, args);
    localizeF1RenderRoot(this.hass, this.renderRoot);
  };
};
