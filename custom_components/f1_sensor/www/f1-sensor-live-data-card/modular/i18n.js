const cacheSuffix = new URL(import.meta.url).search;
const localization = await import(`../localization/index.js${cacheSuffix}`);

const {
  LOCALES,
  languageCode,
  translate,
  translateSourceText,
  translatePlural,
} = localization;

export { languageCode, translate, translatePlural };

// Keyed UI text and catalog source text share one Weblate-backed path.
export const words = (language, keyOrEnglish, replacements = {}) => {
  if (LOCALES.en[keyOrEnglish] !== undefined) {
    const values = replacements
      && typeof replacements === 'object'
      && !Array.isArray(replacements)
      ? replacements
      : {};
    return translate(language, keyOrEnglish, values);
  }
  return translateSourceText(language, keyOrEnglish);
};
