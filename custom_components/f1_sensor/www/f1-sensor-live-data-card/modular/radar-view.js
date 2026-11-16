const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, css }, { words }, radar, { RADAR_CIRCUITS }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./i18n.js'), load('./radar-data.js'), load('./radar-circuits.js'),
]);

// Universal Blue (palette 2), reference colours from LibreWXR's published data.
// c917725f5cabf62aaeb8e87978498f8be9719761, colors/color_table.csv;
// public builtin palette hash 00affff8694d, checked 2026-11-12.
// These are sampled display dBZ values, not intervals or local rain-rate readings.
const INTENSITY_REFERENCES = [
  ['0', '#92887188'], ['5', '#cec087cc'], ['10', '#88ddee'], ['20', '#0077aa'],
  ['30', '#ffee00'], ['40', '#ff7700'], ['50', '#ee0000'], ['60', '#ffaaff'],
  ['70', '#ff44ff'], ['80+', '#aa00aa'],
];

class F1RadarView extends LitElement {
  static properties = { model: { attribute: false }, language: {}, module: { attribute: false },
    selectedId: { state: true }, confirmedContext: { state: true }, zoom: { state: true }, metadata: { state: true },
    frameIndex: { state: true }, displayFrame: { state: true }, loadingFrame: { state: true }, playing: { state: true }, status: { state: true },
    clock: { state: true }, baseImages: { state: true }, radarImages: { state: true } };
  static styles = css`
    :host{display:block;min-width:0;color:var(--f1-text,var(--primary-text-color));font:inherit}
    *{box-sizing:border-box}.shell{display:grid;gap:10px}.toolbar,.playback{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
    label{font-size:.86em;color:var(--f1-muted,var(--secondary-text-color))}select{flex:1;min-width:100px;max-width:100%}
    button,select{font:inherit;color:inherit;background:var(--f1-panel,var(--card-background-color));border:1px solid var(--f1-border,var(--divider-color));border-radius:8px;min-height:40px;padding:6px 10px}
    button{cursor:pointer}button:disabled{opacity:.45;cursor:default}button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid var(--f1-focus,var(--primary-color));outline-offset:2px}
    .map{position:relative;aspect-ratio:4/3;overflow:hidden;border:1px solid var(--f1-border,var(--divider-color));border-radius:10px;background:var(--f1-panel,var(--secondary-background-color))}
    .tile{position:absolute;max-width:none}.precipitation{opacity:.76}
    .circuit-outline{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:hidden}
    .track-casing,.track-line{fill:none;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}
    .track-casing{stroke:#101925;stroke-width:7}.track-line{stroke:#fff15a;stroke-width:3}
    .provisional .track-line{stroke-dasharray:6 4}
    .scale{position:absolute;left:12px;bottom:28px;font-size:.75em;color:#101925;border-bottom:3px solid #101925;border-left:2px solid #101925;border-right:2px solid #101925;text-align:center;background:#ffffffd9;line-height:1.6;white-space:nowrap}
    .map-attribution{position:absolute;right:0;bottom:0;z-index:1;max-width:100%;padding:2px 5px;border-radius:4px 0 0;background:#fffffff2;color:#101925;font-size:11px;line-height:1.5;text-align:right}.map-attribution a{color:inherit}.map-attribution a:focus-visible{outline:2px solid #0077aa;outline-offset:-1px}
    .place.outline-name{position:absolute;top:8px;left:50%;transform:translateX(-50%);background:#151c28e8;color:#fff;padding:3px 7px;border-radius:4px;max-width:90%;font-size:.78em;text-align:center}
    .frame-quality{display:flex;gap:5px 14px;flex-wrap:wrap}.relative{font-weight:650;font-size:.9em}.window{display:flex;justify-content:space-between;gap:8px}.window button{margin-left:auto;min-height:32px;padding:2px 8px;font-size:.9em}
    .legend{min-width:0}.legend-scale{list-style:none;display:grid;grid-template-columns:repeat(10,minmax(0,1fr));gap:3px;margin:5px 0 0;padding:0}.legend-scale li{text-align:center;min-width:0;font-variant-numeric:tabular-nums}.legend-swatch{display:block;height:10px;border-radius:2px;box-shadow:inset 0 0 0 1px #80808055}.legend-value{display:block;margin-top:2px;font-size:.9em}
    summary{cursor:pointer}summary:focus-visible{outline:3px solid var(--f1-focus,var(--primary-color));outline-offset:2px;border-radius:2px}details p{margin:5px 0 0}.data-quality .source{display:block;font-weight:600}.data-quality summary{margin-top:2px}
    .marker{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:16px;height:16px;border:3px solid #fff;border-radius:50%;background:#151c28;box-shadow:0 0 0 2px #151c28}
    .place{position:absolute;left:50%;top:calc(50% + 17px);transform:translateX(-50%);background:#151c28e8;color:#fff;padding:3px 7px;border-radius:4px;max-width:90%;font-size:.78em;text-align:center}
    .notice{position:absolute;inset:0;display:grid;place-content:center;text-align:center;gap:10px;padding:24px;background:var(--f1-panel,var(--card-background-color));color:var(--f1-muted,var(--secondary-text-color))}
    .notice button{justify-self:center}.clock{font-variant-numeric:tabular-nums;font-size:.9em}.badge{font-size:.75em;border:1px solid var(--f1-border,var(--divider-color));border-radius:999px;padding:3px 7px}
    input[type=range]{width:100%;min-height:30px;margin:0;accent-color:var(--primary-color,#54b8ff)}
    .notes,.attribution{font-size:.77em;color:var(--f1-muted,var(--secondary-text-color));line-height:1.5;margin:0}.notes p{margin:0 0 4px}.attribution a{color:inherit}.zoom{margin-left:auto;display:flex;gap:5px}
    @media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
  `;
  constructor() {
    super();
    this.model = {}; this.language = 'en'; this.zoom = radar.RADAR_DEFAULT_ZOOM; this.frameIndex = 0; this.confirmedContext = null;
    this.metadata = null; this.clock = Date.now(); this.playing = false; this.status = 'paused';
    this.baseImages = []; this.radarImages = []; this._visible = false; this._generation = 0;
    this._visibility = () => this._sync();
  }
  connectedCallback() {
    super.connectedCallback();
    document.addEventListener('visibilitychange', this._visibility);
    this._observer = new IntersectionObserver(entries => {
      this._visible = entries.some(entry => entry.isIntersecting);
      this._sync();
    });
    this._observer.observe(this);
  }
  disconnectedCallback() {
    document.removeEventListener('visibilitychange', this._visibility);
    this._observer?.disconnect(); this._visible = false; this._stop();
    super.disconnectedCallback();
  }
  willUpdate(changed) {
    if (changed.has('model')) {
      const previous = changed.get('model');
      if (this.model?.contextKey !== previous?.contextKey) this.confirmedContext = null;
      if (this.model?.selectionKey !== previous?.selectionKey || this.model?.selectedId !== previous?.selectedId) this.selectedId = undefined;
    }
    if (!this.showCircuitSelector) this.selectedId = undefined;
    if (changed.has('module') && this.module?.options?.zoom !== changed.get('module')?.options?.zoom) {
      this.zoom = radar.radarZoom(this.module?.options?.zoom ?? radar.RADAR_DEFAULT_ZOOM);
    }
  }
  updated(changed) {
    if (changed.has('model') || changed.has('module') || changed.has('confirmedContext') || changed.has('selectedId') || changed.has('zoom')) this._sync();
  }
  w(key, replacements = {}) { return words(this.language, `modular.radar_${key}`, replacements); }
  get showCircuitSelector() { return this.module?.options?.show_circuit_selector !== false; }
  get selection() {
    const requested = (this.showCircuitSelector ? this.selectedId : null) ?? this.model?.selectedId;
    const selection = radar.radarCircuit(this.model?.circuits, requested, RADAR_CIRCUITS);
    return { circuits: selection.circuits, selected: selection.selected?.id === requested ? selection.selected : null };
  }
  get currentAllowed() { return !this.model?.currentOnly || (typeof this.model?.contextKey === 'string' && this.confirmedContext === this.model.contextKey); }
  get active() { return this.isConnected && this._visible && !document.hidden && !this.model?.blocked && !this.model?.demo && this.currentAllowed && Boolean(this.selection.selected); }
  _clearImages(key) {
    for (const image of this[key]) URL.revokeObjectURL(image.url);
    this[key] = [];
  }
  _stop() {
    this._generation++; this._key = null; this.playing = false; this.loadingFrame = false; this.displayFrame = null;
    clearTimeout(this._playTimer); clearTimeout(this._refreshTimer); clearInterval(this._ageTimer);
    this._controller?.abort(); this._frameController?.abort(); this._lease?.release(); this._lease = null;
    this._clearImages('radarImages'); this._clearImages('baseImages');
    this.status = 'paused';
  }
  _sync() {
    if (!this.active) { if (this._key) this._stop(); return; }
    const circuit = this.selection.selected;
    const key = `${circuit.id}/${circuit.lat}/${circuit.lon}/${this.zoom}`;
    if (this._key === key) return;
    this._stop(); this._key = key; this._controller = new AbortController();
    this.clock = Date.now(); this._ageTimer = setInterval(() => { this.clock = Date.now(); }, 60000);
    this.status = 'loading'; this._tiles = radar.radarTiles(circuit, this.zoom);
    this._radarTiles = radar.radarTiles(circuit, this.zoom, radar.RADAR_NATIVE_ZOOM);
    const generation = this._generation;
    // OSM requires a genuine browser Referer. HA can default to no-referrer;
    // opt in to origin-only disclosure for this public basemap, with normal caching.
    this._images(this._tiles, radar.radarBaseUrl, this._controller.signal, 'strict-origin-when-cross-origin').then(images => {
      if (generation !== this._generation) { images.forEach(image => URL.revokeObjectURL(image.url)); return; }
      this.baseImages = images;
    }).catch(error => { if (generation === this._generation && error.name !== 'AbortError') this._fail(); });
    this._refresh(generation);
  }
  async _images(tiles, tileUrl, signal, referrerPolicy) {
    const result = [];
    let jobs = [];
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener('abort', abort, { once: true });
    const timeout = setTimeout(abort, 15000);
    try {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      jobs = tiles.map(async tile => {
        const url = tileUrl(tile);
        const response = await fetch(url, { signal: controller.signal, credentials: 'omit', ...(referrerPolicy ? { referrerPolicy } : {}) });
        if (!response.ok) throw new Error('Map tile unavailable');
        const blob = await response.blob();
        if (!blob.type.startsWith('image/')) throw new Error('Invalid map tile');
        if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
        const image = { ...tile, url: URL.createObjectURL(blob) };
        result.push(image);
        const decoder = new Image(); decoder.src = image.url;
        await decoder.decode();
        if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
        return image;
      });
      return await Promise.all(jobs);
    } catch (error) {
      controller.abort();
      await Promise.allSettled(jobs);
      result.forEach(image => URL.revokeObjectURL(image.url));
      if (!signal.aborted && error.name === 'AbortError') throw new Error('Map tile request timed out');
      throw error;
    } finally { clearTimeout(timeout); signal.removeEventListener('abort', abort); }
  }
  async _refresh(generation) {
    this._lease?.release(); const lease = radar.radarMetadataCache.acquire(); this._lease = lease;
    try {
      const metadata = await lease.promise;
      if (generation !== this._generation || !this.active) return;
      this.metadata = metadata;
      await this._showFrame(metadata.frames.findLastIndex(frame => frame.type === 'observed'));
      if (generation === this._generation && this.status !== 'error') this._refreshTimer = setTimeout(() => this._refresh(generation), radar.RADAR_REFRESH_MS);
    } catch (error) { if (generation === this._generation && error.name !== 'AbortError') this._fail(); }
    finally { lease.release(); if (this._lease === lease) this._lease = null; }
  }
  async _showFrame(index) {
    if (!this.active || !this.metadata?.frames[index]) return;
    clearTimeout(this._playTimer); this._frameController?.abort();
    this.loadingFrame = true; this.status = this.radarImages.length ? 'ready' : 'loading';
    const controller = new AbortController(); this._frameController = controller;
    const generation = this._generation;
    const frame = this.metadata.frames[index];
    try {
      const images = await this._images(this._radarTiles, tile => radar.radarTileUrl(frame, tile), controller.signal);
      if (generation !== this._generation || controller.signal.aborted) { images.forEach(image => URL.revokeObjectURL(image.url)); return; }
      this._clearImages('radarImages'); this.radarImages = images;
      this.frameIndex = index; this.displayFrame = frame; this.loadingFrame = false;
      this.status = 'ready'; this._playNext();
    } catch (error) { if (generation === this._generation && !controller.signal.aborted && error.name !== 'AbortError') this._fail(); }
  }
  _fail() {
    const key = this._key;
    this._stop(); this._key = key; this.status = 'error';
  }
  _playNext() {
    clearTimeout(this._playTimer);
    if (this.playing && this.active && this.status === 'ready' && !this.loadingFrame) this._playTimer = setTimeout(() => this._showFrame((this.frameIndex + 1) % this.metadata.frames.length), 900);
  }
  _togglePlay() { this.playing = !this.playing; this._playNext(); }
  _seek(event) { this.playing = false; this._showFrame(Number(event.target.value)); }
  _choose(event) { if (this.showCircuitSelector) this.selectedId = event.target.value; }
  _latest() { this.playing = false; this._showFrame(this.metadata?.frames.findLastIndex(frame => frame.type === 'observed')); }
  _relative(frame) {
    const minutes = Math.round((frame.time - this.metadata.latestTime) / 60);
    return minutes ? this.w(minutes < 0 ? 'minutes_before' : 'minutes_after', { minutes: Math.abs(minutes) }) : this.w('latest');
  }
  _timestamp(time) {
    try { return new Intl.DateTimeFormat(this.language, { hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }).format(new Date(time * 1000)); }
    catch { return new Date(time * 1000).toISOString().slice(11, 16) + ' UTC'; }
  }
  render() {
    const { circuits, selected } = this.selection;
    const showExplanation = this.module?.options?.show_explanation !== false;
    const frame = this.displayFrame;
    const path = selected ? radar.radarTrackPath(selected, this.zoom) : '';
    const scale = selected ? radar.radarScale(selected, this.zoom) : null;
    const age = this.metadata ? Math.max(0, Math.floor((this.clock / 1000 - this.metadata.latestTime) / 60)) : null;
    const reason = this.model?.blocked ? 'blocked' : this.model?.demo ? 'demo' : !selected ? 'no_circuit' : !this.currentAllowed ? 'current_only' : this.status;
    const ready = this.status === 'ready' && this.baseImages.length && reason === 'ready';
    return html`<div class="shell">
      <div class="toolbar">${this.showCircuitSelector ? html`<label for="circuit">${this.w('circuit')}</label><select id="circuit" .value=${selected?.id ?? ''} @change=${this._choose} ?disabled=${!circuits.length}>
        ${!selected ? html`<option value="">${this.w('no_circuit')}</option>` : ''}
        ${circuits.map(circuit => html`<option value=${circuit.id} ?selected=${circuit.id === selected?.id}>${circuit.name}</option>`)}
      </select>` : ''}<span class="zoom"><button @click=${() => { this.zoom = Math.max(radar.RADAR_MIN_ZOOM, this.zoom - 1); }} ?disabled=${this.zoom <= radar.RADAR_MIN_ZOOM} aria-label=${this.w('zoom_out')}>−</button><button @click=${() => { this.zoom = Math.min(radar.RADAR_MAX_ZOOM, this.zoom + 1); }} ?disabled=${this.zoom >= radar.RADAR_MAX_ZOOM} aria-label=${this.w('zoom_in')}>+</button></span></div>
      <div class="map" role="group" aria-label=${`${this.w('map_label')}: ${selected?.name ?? ''}`} aria-busy=${reason === 'loading'}>
        ${this.baseImages.map(image => html`<img class="tile" alt="" src=${image.url} style=${`left:${image.left}%;top:${image.top}%;width:${image.width}%;height:${image.height}%`}>`)}
        ${this.radarImages.map(image => html`<img class="tile precipitation" alt="" src=${image.url} style=${`left:${image.left}%;top:${image.top}%;width:${image.width}%;height:${image.height}%`}>`)}
        ${ready ? html`${path ? html`<svg class=${`circuit-outline${selected.outline.provisional ? ' provisional' : ''}`} viewBox="0 0 512 384" role="img" aria-label=${this.w('track_outline')}><path class="track-casing" d=${path}></path><path class="track-line" d=${path}></path></svg><span class="place outline-name">${selected.name}</span>` : html`<span class="marker"></span><span class="place">${selected.name}</span>`}<span class="scale" role="img" aria-label=${`${this.w('map_scale')}: ${scale.label}`} style=${`width:${scale.width}%`}>${scale.label}</span>` : html`<div class="notice" role="status"><span>${this.w(reason === 'ready' ? 'loading' : reason)}</span>${reason === 'error' ? html`<button @click=${() => { this._key = null; this._sync(); }}>${this.w('retry')}</button>` : ''}${reason === 'current_only' ? html`<button @click=${() => { this.confirmedContext = this.model.contextKey; }}>${this.w('show_current')}</button>` : ''}</div>`}
        <span class="map-attribution">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a></span>
      </div>
      ${ready ? html`<div class="legend notes" role="group" aria-label=${this.w('legend_title')}>
        <details><summary>${this.w('legend_title')}</summary><p>${this.w('legend_description')}</p></details>
        <ol class="legend-scale">${INTENSITY_REFERENCES.map(([value, color]) => html`<li><span class="legend-swatch" style=${`background:${color}`} aria-hidden="true"></span><span class="legend-value">${value}</span></li>`)}</ol>
      </div>` : ''}
      <div class="playback"><button @click=${this._togglePlay} ?disabled=${!ready} aria-label=${this.w(this.playing ? 'pause' : 'play')}>${this.w(this.playing ? 'pause' : 'play')}</button>
        ${frame && !['demo', 'blocked', 'current_only', 'no_circuit', 'paused', 'error'].includes(reason) ? html`<time class="clock" datetime=${new Date(frame.time * 1000).toISOString()}>${this._timestamp(frame.time)}</time><span class="badge">${this.w(frame.type)}</span><span class="relative">${this._relative(frame)}</span>` : ''}
        ${this.loadingFrame && frame ? html`<span class="notes" role="status">${this.w('loading')}</span>` : ''}
      </div>
      <input type="range" min="0" max=${Math.max(0, (this.metadata?.frames.length ?? 1) - 1)} .value=${String(this.frameIndex)} aria-label=${this.w('timeline')} aria-valuetext=${frame ? `${this._timestamp(frame.time)}, ${this._relative(frame)}` : ''} ?disabled=${!this.active || !this.metadata || this.status === 'error'} @input=${this._seek}>
      <div class="window notes">${showExplanation ? html`<span>${this.w('window')}</span>` : ''}<button @click=${this._latest} ?disabled=${!ready}>${this.w('latest_button')}</button></div>
      ${ready ? html`<div class="frame-quality notes"><span>${this.w('image_age', { minutes: age })}</span>${this.metadata.intervalMinutes ? html`<span>${this.w('image_interval', { minutes: this.metadata.intervalMinutes })}</span>` : ''}</div>` : ''}
      ${ready ? html`<div class="data-quality notes" role="note" aria-label=${this.w('quality_title')}>
        <span class="source">${this.w(frame?.type === 'forecast' ? 'quality_forecast' : 'quality_blend')}</span>
        <details><summary>${this.w('quality_warning')}</summary><p>${this.w('quality_description')}</p></details>
      </div>` : ''}
      ${showExplanation ? html`<div class="notes explanation"><p>${this.w('current_notice')}</p><p>${this.w('sources')}</p><p>${this.w('resolution_notice')}</p><p>${this.w('empty_notice')}</p></div>` : ''}
      ${selected && !path ? html`<p class="notes">${this.w('outline_missing')}</p>` : selected?.outline?.provisional ? html`<p class="notes">${this.w('outline_provisional')}</p>` : ''}
      <p class="attribution"><a href="https://librewxr.net/" target="_blank" rel="noopener noreferrer">LibreWXR</a> · <a href="https://github.com/JoshuaKimsey/LibreWXR#data-sources" target="_blank" rel="noopener noreferrer">${this.w('data_sources')}</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a> · Radar-DPC <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>${selected?.outline ? html` · ${this.w('outline_source')}: <a href=${selected.outline.sourceUrl} target="_blank" rel="noopener noreferrer">${selected.outline.sourceName}</a> (${selected.outline.license})` : ''}</p>
    </div>`;
  }
}
if (!customElements.get('f1-radar-view')) customElements.define('f1-radar-view', F1RadarView);
