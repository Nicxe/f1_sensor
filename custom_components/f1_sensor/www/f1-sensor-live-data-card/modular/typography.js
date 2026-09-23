let requested = false;
export function ensureTypography() {
  if (requested || !globalThis.FontFace || !document.fonts) return;
  requested = true;
  const url = new URL('../fonts/barlow-condensed-latin-700-normal.woff2', import.meta.url);
  const version = new URL(import.meta.url).searchParams.get('v');
  if (version) url.searchParams.set('v', version);
  const face = new FontFace('F1 Barlow Condensed', `url("${url.href}")`, { weight: '700', display: 'swap' });
  document.fonts.add(face);
  face.load().catch(() => { document.fonts.delete(face); });
}
