const cacheKey = new URL(import.meta.url).searchParams.get('v');
const cacheSuffix = cacheKey ? `?v=${encodeURIComponent(cacheKey)}` : '';
const { registerF1CardMetadata } = await import(`./platform/card-registry.js${cacheSuffix}`);

registerF1CardMetadata();

await import(`./f1-sensor-live-data-card.js${cacheSuffix}`);
