const cacheKey = new URL(import.meta.url).searchParams.get('v');
const cacheSuffix = cacheKey ? `?v=${encodeURIComponent(cacheKey)}` : '';
const { registerF1CardMetadata } = await import(`./platform/card-registry.js${cacheSuffix}`);

const includeLegacy = new URL(import.meta.url).searchParams.get('legacy') !== '0';
registerF1CardMetadata(includeLegacy);

if (includeLegacy) await import(`./f1-sensor-live-data-card.js${cacheSuffix}`);
await import(`./modular/card.js${cacheSuffix}`);
await import(`./modular/editor.js${cacheSuffix}`);
if (includeLegacy) {
  const { installLegacyMigrationEditors } = await import(`./modular/migration-editor.js${cacheSuffix}`);
  installLegacyMigrationEditors();
}
