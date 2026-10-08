const cacheSuffix = new URL(import.meta.url).search;
const localization = await import(`../localization/index.js${cacheSuffix}`);

const {
  LOCALES,
  languageCode,
  translate,
  translateLegacy,
  translatePlural,
} = localization;

export { languageCode, translate, translatePlural };

// Catalog entries still pass their source label and Swedish compatibility
// value. All keyed UI messages use the same function during the migration.
export const words = (language, keyOrEnglish, replacementsOrSwedish = keyOrEnglish) => {
  if (LOCALES.en[keyOrEnglish] !== undefined) {
    const replacements = replacementsOrSwedish
      && typeof replacementsOrSwedish === 'object'
      && !Array.isArray(replacementsOrSwedish)
      ? replacementsOrSwedish
      : {};
    return translate(language, keyOrEnglish, replacements);
  }
  return translateLegacy(language, keyOrEnglish, replacementsOrSwedish);
};
