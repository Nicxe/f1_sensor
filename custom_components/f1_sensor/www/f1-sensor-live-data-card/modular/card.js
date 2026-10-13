const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, css, repeat }, { normalizeConfig, configWarnings, resolveSelection }, { MODULES, label, moduleTitle, moduleFocusKinds }, data, { SectorStore, safeImageUrl, cardAccent }, { watchEntries, watchRaceControl, watchGroup, watchAnalysis, watchTrackMap, watchMinisectors, HistoryResources, callEntityService }, { sharedStyles, translatePlural, words, dateTime }, { visibilityMet, visibilityMediaQueries, hasTimeVisibility }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./config.js'), load('./catalog.js'), load('./data.js'), load('./semantics.js'), load('./connection.js'), load('./view.js'), load('./visibility.js'),
]);
const { makeDemo } = await load('./demo.js');
// HA recreates the preview card on config changes; its host keeps editor-only choices.
// Weak keys release the choice when the native preview is removed. Nothing is saved.
const previewPreferences = new WeakMap();
const { ensureTypography } = await load('./typography.js');
await load('./viewing-controls.js');
const season = await load('./season-data.js');
const sessionData = await load('./session-data.js');
const analysisData = await load('./analysis-data.js');
const minisectorData = await load('./minisector-data.js');
const telemetryData = await load('./telemetry-data.js');
const { mapModel, mapExpiry } = await load('./map-data.js');
const { hasF1Action, dispatchF1CardAction } = await load('../platform/actions.js');

// Spread first layouts over frames; established cards keep their normal update path.
const initialRenders = new Map();
let initialRenderFrame = null;
function flushInitialRenders() {
  initialRenderFrame = null;
  for (const [card, resolve] of [...initialRenders].slice(0, 3)) {
    initialRenders.delete(card); resolve();
  }
  if (initialRenders.size) initialRenderFrame = requestAnimationFrame(flushInitialRenders);
}
function scheduleInitialRender(card) {
  return new Promise(resolve => {
    initialRenders.set(card, resolve);
    if (initialRenderFrame === null) initialRenderFrame = requestAnimationFrame(flushInitialRenders);
  });
}
function cancelInitialRender(card) {
  const resolve = initialRenders.get(card);
  if (!resolve) return;
  initialRenders.delete(card); resolve();
  if (!initialRenders.size && initialRenderFrame !== null) {
    cancelAnimationFrame(initialRenderFrame); initialRenderFrame = null;
  }
}

export class F1SensorCard extends LitElement {
  static properties = { hass: { attribute: false }, config: { attribute: false }, preview: { type: Boolean }, previewData: { attribute: false }, revision: { state: true }, frozen: { state: true }, tab: { state: true } };
  static styles = [sharedStyles, css`
    :where(ha-card) {
      --f1-card-padding:var(--_f1-card-padding,20px); --f1-minimal-padding:var(--_f1-minimal-padding,12px);
      --f1-module-gap:var(--_f1-module-gap,26px); --f1-section-space:var(--_f1-section-space,20px);
      --f1-cell-padding:var(--_f1-cell-padding,10px 12px); --f1-item-padding:var(--_f1-item-padding,9px);
      --f1-heading-font:var(--_f1-heading-font,inherit); --f1-heading-transform:var(--_f1-heading-transform,none);
      --f1-module-heading-size:var(--_f1-module-heading-size,1.1em); --f1-surface:var(--_f1-surface,transparent);
      --f1-text:var(--_f1-text,var(--primary-text-color,#e9edf3)); --f1-muted:var(--_f1-muted,var(--secondary-text-color,#b9c1ce));
      --f1-border:var(--_f1-border,#6c7480); --f1-divider:var(--_f1-divider,rgba(127,127,127,.25));
      --f1-panel:var(--_f1-panel,rgba(127,127,127,.07)); --f1-focus:var(--_f1-focus,#56aaff);
      --f1-row-alternate:var(--_f1-row-alternate,transparent); --f1-accent:var(--_f1-accent,#e10600);
      --f1-numerals:var(--_f1-numerals,tabular-nums); --f1-card-radius:var(--_f1-card-radius,var(--ha-card-border-radius,14px));
      display:block; padding:var(--f1-card-padding); border:1px solid var(--f1-border); border-radius:var(--f1-card-radius); background:var(--f1-surface); color:var(--f1-text); overflow:hidden;
    }
    ha-card[data-style=minimal] { border-color:transparent; box-shadow:none; padding:var(--f1-minimal-padding,12px); }
    ha-card[data-surface=framed] { border:1px solid var(--f1-border); box-shadow:none; }
    ha-card[data-surface=soft] { border:1px solid var(--f1-divider); box-shadow:none; }
    ha-card[data-surface=flat] { border:0; box-shadow:none; }
    ha-card[data-accent=true] { border-top:3px solid var(--f1-accent); }
    header { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:var(--f1-section-space,20px); }
    .heading strong { font-family:var(--f1-heading-font,inherit); font-size:1.25em; letter-spacing:-.02em; }
    ha-card[data-font=f1] .heading strong { font-family:'F1 Barlow Condensed',sans-serif; text-transform:uppercase; font-size:1.65em; letter-spacing:.025em; }
    .heading small { display:block; color:var(--f1-muted); }
    .heading button { border:0; padding:0 8px; margin-left:-8px; text-align:left; }
    .action-alternatives { margin-bottom:16px; }
    .action-alternatives summary { min-height:44px; cursor:pointer; display:flex; align-items:center; }
    .tools { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
    select { max-width:100%; min-height:44px; padding:8px; border:1px solid var(--f1-border); background:var(--f1-surface); border-radius:8px; }
    .modules { display:grid; gap:var(--f1-module-gap,26px); }
    .modules > f1-module-view { border-top:1px solid var(--f1-divider); padding-top:var(--f1-section-space,20px); }
    .modules > f1-module-view:first-child { border-top:0; padding-top:0; }
    ha-card[data-layout=columns] { container:f1-modules / inline-size; }
    .modules[data-layout=columns] {
      --_f1-available-columns:1;
      --_f1-layout-columns:min(var(--_f1-max-columns),var(--_f1-available-columns));
      grid-template-columns:repeat(var(--_f1-layout-columns),minmax(0,1fr));
      grid-auto-flow:row; align-items:start;
    }
    .modules[data-layout=columns] > f1-module-view {
      grid-column:span min(var(--_f1-module-span,1),var(--_f1-layout-columns));
      min-width:0; border-top:0; padding-top:0;
    }
    .modules[data-layout=columns] > f1-module-view[data-column-span=full] { grid-column:1 / -1; }
    @container f1-modules (min-width:38rem) { .modules[data-layout=columns] { --_f1-available-columns:2; } }
    @container f1-modules (min-width:58rem) { .modules[data-layout=columns] { --_f1-available-columns:3; } }
    @container f1-modules (min-width:78rem) { .modules[data-layout=columns] { --_f1-available-columns:4; } }
    nav { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:20px; }
    .frozen { padding:10px 12px; margin-bottom:16px; border:1px solid currentColor; border-radius:8px; }
    .connection-status { padding:10px 12px; margin:0 0 16px; border:1px solid currentColor; border-radius:8px; }
    .preview-tools { display:flex; flex-wrap:wrap; gap:12px; padding-bottom:16px; margin-bottom:16px; border-bottom:1px solid var(--f1-divider); }
    .preview-tools label { flex:1 1 160px; min-width:0; }
    .preview-tools label span { display:block; margin-bottom:4px; font-size:.85em; }
    .preview-tools select { width:100%; }
    .preview-tools p { flex-basis:100%; margin:0; font-size:.85em; color:var(--f1-muted); }
    .demo { font-size:.85em; padding:6px 0 12px; font-weight:650; }
    @media(max-width:360px) { :where(ha-card) { --f1-card-padding:14px; } }
  `];
  constructor() {
    super(); this.entries = []; this.revision = 0; this.frozen = false; this.tab = ''; this.focus = {}; this.groupContext = {};
    this.sampleKey = '';
    this.savedSources = new data.RetainedSources();
    this.history = new HistoryResources(() => { this.revision++; });
    this.telemetry = new HistoryResources(() => { this.revision++; }); this.telemetryRequests = new Map();
    this.viewingRequest = null; this.raceControlRequest = null; this.replayRequests = new Map(); this.sectors = new SectorStore(); this.choices = new Map(); this.moduleNodes = new Map(); this.minisectorResources = new Map(); this.eventState = { data: [], status: 'loading' }; this.analysisState = { data: null, status: 'loading' }; this.mapState = { data: null, status: 'loading' };
  }
  get sourceHass() { return this.sample?.hass ?? this.hass; }
  get modelPreview() { return this.sample?.preview ?? this.previewData; }
  isEditorPreview() {
    if (!this.preview) return false;
    // HA also sets preview while arranging saved dashboard cards. Only the
    // card-edit dialog gets sample controls; inspect ancestry without changing HA's DOM.
    for (let node = this; node; node = node.parentNode ?? node.host) {
      if (node.localName === 'hui-dialog-edit-card') return true;
    }
    return false;
  }
  syncPreview() {
    this.editorPreview = this.isEditorPreview();
    const owner = this.parentElement ?? this;
    this.previewOptions = this.editorPreview ? previewPreferences.get(owner) ?? { source: 'actual', scene: 'race' } : null;
    if (this.editorPreview) previewPreferences.set(owner, this.previewOptions);
    if (this.previewOptions) {
      if (this.previewOptions.connection !== this.hass?.connection) this.previewOptions.entries = [];
      this.previewOptions.connection = this.hass?.connection;
      if (this.entries.length && this.connection === this.hass?.connection) this.previewOptions.entries = this.entries;
    }
    const language = this.hass?.locale?.language ?? this.hass?.language ?? 'en';
    const key = this.previewOptions?.source === 'sample' ? JSON.stringify([this.previewOptions.scene, language, this.config?.f1_entry_id]) : '';
    if (key !== this.sampleKey) {
      this.stopSources(); this.choices.clear(); this.retainedRoster = null;
      this.focus = { driver: this.config?.context.driver, team: this.config?.context.team };
      this.sampleKey = key;
      this.sample = key ? makeDemo(this.previewOptions.scene, language, this.config?.f1_entry_id) : null;
    }
    if (this.sample) {
      // Use the user's locale and theme, but never mix real and sample entity states.
      this.sample.hass = { ...this.sample.hass, locale: this.hass?.locale ?? this.sample.hass.locale,
        config: this.hass?.config ?? this.sample.hass.config, themes: this.hass?.themes ?? this.sample.hass.themes, user: this.hass?.user };
      const entries = this.previewOptions.entries ?? [];
      const entry = this.config?.f1_entry_id ? entries.find(item => item.entry_id === this.config.f1_entry_id) : entries.length === 1 ? entries[0] : null;
      this.sample.preview.accentTeams = data.accentTeams(this.hass, entry);
    }
  }
  changePreview(key, value) {
    this.previewOptions[key] = value;
    this.requestUpdate();
  }
  previewControls() {
    if (!this.editorPreview) return '';
    const source = this.previewOptions?.source ?? 'actual', scene = this.previewOptions?.scene ?? 'race';
    return html`<div class="preview-tools" role="group" aria-label=${this.w('modular.preview_settings')}>
      <label><span>${this.w('modular.preview_data')}</span><select aria-label=${this.w('modular.preview_data')} .value=${source} @change=${event => this.changePreview('source', event.target.value)}>
        <option value="actual" .selected=${source === 'actual'}>${this.w('modular.actual_data')}</option><option value="sample" .selected=${source === 'sample'}>${this.w('modular.sample_data')}</option>
      </select></label>
      ${source === 'sample' ? html`<label><span>${this.w('modular.sample_session')}</span><select aria-label=${this.w('modular.sample_session')} .value=${scene} @change=${event => this.changePreview('scene', event.target.value)}>
        ${[['before', this.w('modular.before_a_session')], ['practice', this.w('modular.practice')], ['qualifying', this.w('modular.qualifying')], ['sprint_qualifying', this.w('modular.sprint_qualifying')], ['sprint', 'Sprint'], ['race', 'Race'], ['ended', this.w('modular.finished')], ['replay', 'Replay'], ['missing', this.w('modular.missing_data')]].map(([value, title]) => html`<option value=${value} .selected=${scene === value}>${title}</option>`)}
      </select></label>` : ''}
      ${this.config.layout === 'columns' ? html`<p>${this.w('modular.home_assistant_limits_the_preview_width_check_the_full_column_layout_on_your_dashboard')}</p>` : ''}
    </div>`;
  }
  setConfig(config) { this.cancelActions(); this.choices?.clear(); this.config = normalizeConfig(config); this.syncVisibilityListeners(); }
  static getStubConfig() { return normalizeConfig({ modules: [] }); }
  static async getConfigElement() { await load('./editor.js'); return document.createElement('f1-sensor-card-editor'); }
  async getCardSize() {
    await this.updateComplete;
    const height = this.renderRoot?.querySelector('ha-card')?.getBoundingClientRect().height ?? 0;
    return height > 0 ? Math.max(1, Math.ceil(height / 50))
      : 2 + (this.config?.modules?.filter(module => module.enabled && (!this.sourceHass || this.moduleVisible(module))).length ?? 1) * 4;
  }
  getGridOptions() {
    // Keep automatic height by default. HA also clamps saved numeric rows to
    // this measured minimum, so an old two-row setting cannot overlap content.
    return { columns: 12, min_columns: 6, min_rows: this.minimumGridRows ?? 2 };
  }
  syncCardSize() {
    if (!this.isConnected) return;
    // em-based grid lengths belong to HA's wrapper, not the card typography.
    const gridFont = getComputedStyle(this.parentElement ?? this).fontSize;
    if (this.sizeProbe) this.sizeProbe.style.fontSize = gridFont;
    const card = this.renderRoot?.querySelector('ha-card');
    if (this.sizeTarget === card && this.sizeObserver && this.sizeProbe?.parentNode === this.renderRoot) return;
    this.sizeObserver?.disconnect();
    this.sizeTarget = card;
    if (!card) return;
    if (!this.sizeProbe) {
      // Resolve HA's actual grid lengths in CSS, including rem/calc themes.
      // This invisible probe takes no space and never sets the card's height.
      this.sizeProbe = document.createElement('span');
      this.sizeProbe.setAttribute('aria-hidden', 'true');
      this.sizeProbe.style.cssText = 'all:initial;position:absolute;display:block;visibility:hidden;pointer-events:none;contain:strict;font:inherit;top:0;left:0;width:var(--row-height,var(--ha-section-grid-row-height,56px));height:var(--row-gap,var(--ha-section-grid-row-gap,8px));';
      this.sizeProbe.style.fontSize = gridFont;
    }
    // Lit replaces the loading template after entry discovery.
    if (this.sizeProbe.parentNode !== this.renderRoot) this.renderRoot.append(this.sizeProbe);
    if (typeof ResizeObserver !== 'undefined') {
      this.sizeObserver ??= new ResizeObserver(() => this.updateCardSize());
      this.sizeObserver.observe(card, { box: 'border-box' });
      this.sizeObserver.observe(this.sizeProbe);
    }
    this.updateCardSize();
  }
  updateCardSize() {
    if (!this.isConnected || !this.sizeTarget) return;
    const height = Math.ceil(this.sizeTarget.getBoundingClientRect().height);
    if (height <= 0) return;
    const metrics = this.sizeProbe.getBoundingClientRect();
    const rowHeight = metrics.width > 0 ? metrics.width : 56;
    const gap = Math.max(0, metrics.height);
    const minimum = Math.max(2, Math.ceil((height + gap) / (rowHeight + gap)));
    if (height === this.measuredHeight && minimum === this.minimumGridRows) return;
    this.measuredHeight = height; this.minimumGridRows = minimum;
    this.dispatchEvent(new Event('card-updated', { bubbles: true, composed: true }));
    this.dispatchEvent(new Event('iron-resize', { bubbles: true, composed: true }));
  }
  async scheduleUpdate() {
    // Shared HA pushes can dirty many cards in the same microtask. Give each
    // card a browser task so one dashboard update cannot monopolize input.
    if (this.isConnected && !this.moduleNodes.size) await scheduleInitialRender(this);
    else await new Promise(resolve => setTimeout(resolve, 0));
    return super.scheduleUpdate();
  }
  connectedCallback() {
    super.connectedCallback();
    this.media = window.matchMedia('(prefers-color-scheme: dark)');
    this.themeChanged = () => { this.revision++; };
    this.media.addEventListener('change', this.themeChanged);
    this.syncVisibilityListeners();
    this.requestUpdate();
  }
  disconnectedCallback() {
    super.disconnectedCallback(); cancelInitialRender(this); clearInterval(this.clock); clearTimeout(this.mapAgeTimer);
    this.sizeObserver?.disconnect(); this.sizeTarget = null;
    this.cancelActions(); this.replayRequests.clear(); this.viewingRequest = null; this.raceControlRequest = null;
    this.media?.removeEventListener('change', this.themeChanged);
    this.clearVisibilityMedia();
    this.stopSources();
  }
  clearVisibilityMedia() {
    for (const [query, listener] of this.visibilityMedia ?? []) query.removeEventListener('change', listener);
    this.visibilityMedia = new Map();
  }
  syncVisibilityListeners() {
    clearInterval(this.clock); this.clearVisibilityMedia();
    if (!this.isConnected || !this.config) return;
    const conditions = this.config.modules.flatMap(module => module.visibility);
    this.clock = setInterval(() => { this.revision++; }, hasTimeVisibility(conditions) ? 1_000 : 30_000);
    for (const source of visibilityMediaQueries(conditions)) {
      let query;
      try { query = window.matchMedia(source); } catch { continue; }
      const listener = () => { this.revision++; };
      query.addEventListener('change', listener); this.visibilityMedia.set(query, listener);
    }
  }
  moduleVisible(module) { return visibilityMet(module.visibility, this.sourceHass); }
  stopSources() {
    this.savedSources.clear();
    this.frozen = false; this.frozenModels = null; this.frozenFocus = null; this.frozenRoster = null; this.frozenGeneration = null;
    this.history.close(); this.telemetry.close(); this.telemetryRequests.clear(); this.telemetryContext = '';
    this.stopEntries?.(); this.stopEvents?.(); this.stopAnalysis?.(); this.stopMap?.(); this.group?.close();
    for (const resource of this.minisectorResources.values()) resource.stop?.();
    this.minisectorResources.clear();
    this.stopEntries = this.stopEvents = this.stopAnalysis = this.stopMap = this.group = null; this.mapKey = ''; this.mapState = { data: null, status: 'loading' }; this.analysisKey = ''; this.analysisState = { data: null, status: 'loading' };
    this.connection = null; this.eventKey = ''; this.groupKey = ''; this.groupContext = {}; this.sectors.reset();
  }
  get language() { return this.sourceHass?.locale?.language ?? this.sourceHass?.language ?? 'en'; }
  w(en, sv) { return words(this.language, en, sv); }
  get entry() {
    const entries = this.modelPreview?.entries ?? this.entries;
    return this.config?.f1_entry_id ? entries.find(entry => entry.entry_id === this.config.f1_entry_id) : entries.length === 1 ? entries[0] : null;
  }
  get settings() {
    const saved = this.config.appearance;
    const appearance = { ...saved, font: saved.font === 'auto' ? saved.style === 'f1' ? 'f1' : 'system' : saved.font };
    const mode = appearance.mode === 'auto' ? (this.sourceHass?.themes?.darkMode ?? this.media?.matches ?? true) ? 'dark' : 'light' : appearance.mode;
    const timePreference = this.sourceHass?.locale?.time_zone;
    const timezone = timePreference === 'local' ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : timePreference && timePreference !== 'server' ? timePreference : this.sourceHass?.config?.time_zone ?? 'UTC';
    return { appearance, accessibility: this.config.accessibility, mode, language: this.language, timezone, timeFormat: this.sourceHass?.locale?.time_format };
  }
  willUpdate(changed) {
    this.syncPreview();
    if (!this.sourceHass || !this.config || !this.isConnected) return;
    this.savedSources.update(this.sourceHass, this.entry, this.config, Boolean(this.modelPreview));
    if (this.settings.appearance.font === 'f1') ensureTypography();
    const activeModule = this.shadowRoot?.activeElement;
    this.focusRestore = activeModule?.localName === 'f1-module-view' && activeModule.shadowRoot?.activeElement?.dataset?.focus
      ? { module: activeModule.module.id, control: activeModule.shadowRoot.activeElement.dataset.focus } : null;
    if (changed.has('config')) { this.focus = { driver: this.config.context.driver, team: this.config.context.team }; this.frozen = false; }
    if (this.frozen && data.spoilerState(this.sourceHass, this.entry, this.config.context.spoilers) !== 'clear') { this.frozen = false; this.sectors.reset(); this.frozenModels = null; }
    if (!this.frozen) { this.frozenModels = null; this.frozenFocus = null; this.frozenRoster = null; this.frozenGeneration = null; }
    if (this.modelPreview) { if (this.connection) this.stopSources(); return; }
    if (this.connection !== this.sourceHass.connection) {
      this.stopSources(); this.entries = []; this.connection = this.sourceHass.connection;
      if (this.connection) this.stopEntries = watchEntries(this.sourceHass, state => { this.discovery = state; if (state.data) this.entries = state.data; this.revision++; });
    }
    const entry = this.entry;
    if (this.viewingRequest && (this.viewingRequest.entryId !== entry?.entry_id || this.viewingRequest.connection !== this.sourceHass.connection)) this.viewingRequest = null;
    const usable = module => module.enabled && this.moduleVisible(module) && this.moduleSessionState(module).available && module.when.includes(this.moduleSessionState(module).phase);
    const historyQueries = entry && data.spoilerState(this.sourceHass, entry, this.config.context.spoilers) === 'clear'
      ? this.config.modules.filter(module => usable(module) && module.type === 'archive').flatMap(module => season.archivePlan({ ...module, selection: resolveSelection(this.config.context, module, this.groupContext), options: { ...module.options, ...this.choices.get(module.id) } }, entry.entry_id, query => this.history.read(query)).requests) : [];
    this.history.sync(this.sourceHass, historyQueries);
    const replay = data.replayModel(this.sourceHass, entry);
    const telemetryContext = replay.loaded && entry && data.spoilerState(this.sourceHass, entry, this.config.context.spoilers) === 'clear' ? JSON.stringify([entry.entry_id, replay.sessionId]) : '';
    if (telemetryContext !== this.telemetryContext) { this.telemetryRequests.clear(); this.telemetryContext = telemetryContext; }
    for (const id of this.telemetryRequests.keys()) if (!this.config.modules.some(module => module.id === id && usable(module) && module.type === 'telemetry')) this.telemetryRequests.delete(id);
    const telemetryQueries = telemetryContext ? this.config.modules.filter(module => usable(module) && module.type === 'telemetry').flatMap(module => {
      const plan = telemetryData.telemetryPlan({ ...module, options: { ...module.options, ...this.choices.get(module.id) } }, entry, replay, query => this.telemetry.read(query), this.telemetryRequests.get(module.id));
      if (!plan.activeCompare) this.telemetryRequests.delete(module.id);
      return plan.requests;
    }) : [];
    this.telemetry.sync(this.sourceHass, telemetryQueries);
    const address = { entry: entry?.entry_id, dashboard: this.locationParts()[0], view: this.locationParts()[1], name: this.config.context.group };
    const groupKey = this.config.context.scope === 'group' && entry ? JSON.stringify(address) : '';
    if (groupKey !== this.groupKey) {
      this.group?.close(); this.group = null; this.groupKey = groupKey;
      if (groupKey) this.group = watchGroup(this.connection, address, value => {
        this.groupContext = value;
        if (this.config.context.share.includes('focus')) this.focus = { ...this.focus, ...Object.fromEntries(['driver', 'team'].filter(key => typeof value[key] === 'string').map(key => [key, value[key]])) };
        this.revision++;
      });
    }
    const mapKey = entry && this.config.modules.some(module => usable(module) && module.type === 'map') && data.spoilerState(this.sourceHass, entry, this.config.context.spoilers) === 'clear' ? entry.entry_id : '';
    if (mapKey !== this.mapKey) {
      this.stopMap?.(); this.stopMap = null; this.mapKey = mapKey; this.mapState = { data: null, status: 'loading' };
      if (mapKey) this.stopMap = watchTrackMap(this.sourceHass, mapKey, state => { this.mapState = state; this.revision++; });
    }
    const analysisKey = entry && this.config.modules.some(module => usable(module) && MODULES[module.type]?.stream === 'analysis') && data.spoilerState(this.sourceHass, entry, this.config.context.spoilers) === 'clear' ? entry.entry_id : '';
    if (analysisKey !== this.analysisKey) {
      this.stopAnalysis?.(); this.stopAnalysis = null; this.analysisKey = analysisKey; this.analysisState = { data: null, status: 'loading' };
      if (analysisKey) this.stopAnalysis = watchAnalysis(this.sourceHass, analysisKey, state => { this.analysisState = state; this.revision++; });
    }
    const minisectorContexts = new Map();
    if (entry && data.spoilerState(this.sourceHass, entry, this.config.context.spoilers) === 'clear') {
      for (const module of this.config.modules.filter(module => usable(module) && minisectorData.usesMinisectors(module, this.moduleNodes.get(module.id)?.timingExpanded?.length > 0))) {
        const context = minisectorData.minisectorContext(this.sourceHass, entry, resolveSelection(this.config.context, module, this.groupContext));
        if (context) minisectorContexts.set(context.key, context);
      }
    }
    for (const [key, resource] of this.minisectorResources) if (!minisectorContexts.has(key)) { resource.stop?.(); this.minisectorResources.delete(key); }
    for (const [key, context] of minisectorContexts) {
      if (this.minisectorResources.has(key)) continue;
      const resource = { context, state: { status: 'loading', data: null } };
      this.minisectorResources.set(key, resource);
      resource.stop = watchMinisectors(this.sourceHass, context, state => { resource.state = state; this.revision++; });
    }
    const eventKey = entry && this.config.modules.some(module => usable(module) && module.type === 'race_control') && data.spoilerState(this.sourceHass, entry, this.config.context.spoilers) === 'clear' ? entry.entities?.race_control : '';
    if (eventKey !== this.eventKey) {
      this.stopEvents?.(); this.stopEvents = null; this.eventKey = eventKey; this.eventState = { status: 'loading', data: [] };
      if (eventKey) this.stopEvents = watchRaceControl(this.sourceHass, eventKey, state => { this.eventState = state; this.revision++; });
    }
  }
  updated() {
    this.syncUserStyles();
    this.syncCardSize();
    clearTimeout(this.mapAgeTimer);
    const expiry = !this.modelPreview && !this.frozen && this.mapKey ? mapExpiry(this.mapState.data?.snapshot) : null;
    const remaining = expiry === null ? null : expiry - Date.now();
    if (this.isConnected && remaining > 0) this.mapAgeTimer = setTimeout(() => { this.revision++; }, Math.min(remaining, 2_147_483_647));
    if (!this.focusRestore) return;
    const module = this.moduleNodes.get(this.focusRestore.module);
    const button = [...(module?.shadowRoot?.querySelectorAll('[data-focus]') ?? [])].find(node => node.dataset.focus === this.focusRestore.control);
    if (button && module.shadowRoot.activeElement !== button && !module.hidden) button.focus({ preventScroll: true });
  }
  syncUserStyles() {
    const source = this.config?.styles;
    let style = this.renderRoot?.querySelector('style[data-f1-user-styles]');
    if (!source) { style?.remove(); return; }
    if (!style) {
      style = document.createElement('style');
      style.setAttribute('data-f1-user-styles', '');
      this.renderRoot.append(style);
    }
    if (style.textContent !== source) style.textContent = source;
  }
  locationParts() {
    const parts = window.location.pathname.split('/').filter(Boolean);
    return [parts[0] ?? 'lovelace', parts[1] ?? '0'];
  }
  moduleSessionState(module) {
    const selection = resolveSelection(this.config.context, module, this.groupContext);
    const state = data.selectionState(this.sourceHass, this.entry, selection);
    if (state.archive && module.type !== 'archive') return { ...state, available: false, reason: 'archive_module_required' };
    return state;
  }
  cancelActions() { clearTimeout(this.holdTimer); clearTimeout(this.tapTimer); this.held = false; }
  _handleCardAction(action = 'tap') {
    if (this.preview || this.modelPreview || !this.isConnected) return false;
    return dispatchF1CardAction(this, action);
  }
  actionDown(event) {
    if (event.button !== 0 || !hasF1Action(this, 'hold')) return;
    this.held = false;
    this.holdTimer = setTimeout(() => { this.held = true; this._handleCardAction('hold'); }, 500);
  }
  actionRelease() { clearTimeout(this.holdTimer); }
  actionClick(event) {
    this.actionRelease();
    if (this.held) { this.held = false; return; }
    if (event.detail === 0 || !hasF1Action(this, 'double_tap')) { clearTimeout(this.tapTimer); this._handleCardAction('tap'); return; }
    clearTimeout(this.tapTimer);
    this.tapTimer = setTimeout(() => this._handleCardAction('tap'), 250);
  }
  actionDouble(event) { event.preventDefault(); this.cancelActions(); this._handleCardAction('double_tap'); }
  actionHeading() {
    const title = html`<strong part="card-title">${this.config.title}</strong>`;
    return hasF1Action(this, 'tap') ? html`<button data-f1-card-action aria-label=${`${this.config.title} · ${this.w('modular.card_action')}`}
      @pointerdown=${this.actionDown} @pointerup=${this.actionRelease} @pointerleave=${this.actionRelease} @pointercancel=${this.cancelActions}
      @click=${this.actionClick} @dblclick=${this.actionDouble}>${title}</button>` : title;
  }
  actionAlternatives() {
    const actions = [...(this.config.appearance.show_header ? [] : [['tap', this.w('modular.tap_action')]]), ['hold', this.w('modular.hold_action')], ['double_tap', this.w('modular.double_tap_action')]].filter(([key]) => hasF1Action(this, key));
    return actions.length ? html`<details class="action-alternatives" part="action-alternatives"><summary>${this.w('modular.card_actions')}</summary><div class="tools" part="action-toolbar">${actions.map(([key, text]) => html`<button @click=${() => this._handleCardAction(key)}>${text}</button>`)}</div></details>` : '';
  }
  chooseDriver(event) {
    this.frozen = false;
    this.focus = { ...this.focus, driver: event.target.value };
    if (!this.preview && !this.modelPreview && this.config.context.share.includes('focus')) this.group?.publish({ driver: event.target.value });
    this.revision++;
  }
  chooseGroupSelection(event) {
    if (this.preview || this.modelPreview || !this.group || !this.config.context.share.includes('selection')) return;
    let selection;
    try { selection = JSON.parse(event.target.value); } catch { return; }
    this.group.publish({ selection }); this.frozen = false; this.revision++;
  }
  freeze() {
    if (!this.frozen) {
      this.savedSources.update(this.sourceHass, this.entry, this.config, Boolean(this.modelPreview));
      this.frozenModels = this.buildModels(); this.frozenAt = this.modelPreview?.now ?? Date.now();
      this.frozenFocus = { ...this.focus };
      this.frozenGeneration = this.savedSources.viewGeneration;
      const roster = data.source(this.sourceHass, this.entry, 'driver_list');
      this.frozenRoster = structuredClone(roster.status === 'available' ? roster : this.retainedRoster ?? roster);
    }
    this.frozen = !this.frozen;
  }
  async viewingAction(event) {
    event.stopPropagation();
    const detail = event.detail, entry = this.entry, hass = this.sourceHass;
    if (!detail || !entry || !this.config.context.viewing_controls || this.preview || this.modelPreview || this.frozen || !this.isConnected || detail.connection !== hass?.connection || this.viewingRequest?.pending) return;
    const command = data.viewingCommand(hass, entry, detail.action, detail.value, detail.context, this.config.context.spoilers);
    if (!command) return;
    const request = { action: detail.action, entryId: entry.entry_id, connection: hass.connection, pending: true, error: false, busy: false };
    this.viewingRequest = request; this.revision++;
    try { request.busy = !await callEntityService(hass, command, detail.action === 'delay' || detail.action.startsWith('calibration_') ? `live-delay:${entry.entry_id}` : undefined); }
    catch { request.error = true; }
    finally {
      if (this.isConnected && this.viewingRequest === request) { request.pending = false; this.revision++; }
    }
  }
  async replayAction(event) {
    event.stopPropagation();
    const detail = event.detail, entry = this.entry;
    if (!detail || typeof detail.module !== 'string') return;
    if (this.preview || this.modelPreview || this.frozen || !this.isConnected || !entry || typeof this.sourceHass?.callService !== 'function' || this.replayRequests.get(entry.entry_id)?.pending) return;
    const module = this.config.modules.find(item => item.id === detail.module);
    const command = data.replayCommand(this.sourceHass, entry, module, detail.action, detail.value, detail.context);
    if (!command) return;
    const request = { pending: true, error: false, busy: false };
    this.replayRequests.set(entry.entry_id, request); this.revision++;
    try { request.busy = !await callEntityService(this.sourceHass, command, `replay:${entry.entry_id}`); }
    catch { request.error = true; }
    finally {
      if (this.isConnected && this.replayRequests.get(entry.entry_id) === request) { request.pending = false; this.revision++; }
    }
  }
  async raceControlAction(event) {
    event.stopPropagation();
    const detail = event.detail, entry = this.entry, hass = this.sourceHass;
    if (!detail || typeof detail.module !== 'string' || detail.action !== 'clear' || this.preview || this.modelPreview || this.frozen || !this.isConnected || !entry || typeof hass?.callService !== 'function' || data.spoilerState(hass, entry, this.config.context.spoilers) !== 'clear' || this.raceControlRequest?.pending) return;
    const module = this.config.modules.find(item => item.id === detail.module && item.type === 'race_control' && item.enabled);
    const entityId = entry.entities?.race_control;
    if (!module || module.options.presentation !== 'list' || !module.options.show_clear_button || typeof entityId !== 'string' || !entityId.startsWith('sensor.')) return;
    const request = { pending: true, error: false, busy: false };
    this.raceControlRequest = request; this.revision++;
    try {
      request.busy = !await callEntityService(hass, { domain: 'f1_sensor', service: 'clear_race_control_log', data: { entity_id: entityId } }, `race-control:${entry.entry_id}`);
      if (!request.busy && this.raceControlRequest === request) this.eventState = { ...this.eventState, data: [] };
    } catch { request.error = true; }
    finally {
      if (this.isConnected && this.raceControlRequest === request) { request.pending = false; this.revision++; }
    }
  }
  telemetryAction(event) {
    event.stopPropagation();
    const detail = event.detail, entry = this.entry;
    if (!detail || this.preview || this.modelPreview || this.frozen || !this.isConnected || !entry || data.spoilerState(this.sourceHass, entry, this.config.context.spoilers) !== 'clear') return;
    const saved = this.config.modules.find(module => module.id === detail.module && module.type === 'telemetry' && module.enabled);
    if (!saved) return;
    const module = { ...saved, options: { ...saved.options, ...this.choices.get(saved.id) } }, replay = data.replayModel(this.sourceHass, entry);
    if (!replay.loaded || replay.sessionId !== detail.sessionId) return;
    const plan = telemetryData.telemetryPlan(module, entry, replay, query => this.telemetry.read(query), this.telemetryRequests.get(saved.id));
    if (event.type === 'f1-telemetry-selection') {
      if (!Array.isArray(detail.selected) || detail.selected.length > 4 || detail.selected.some(id => typeof id !== 'string') || plan.selectionChanged && detail.selected.length) return;
      const selected = telemetryData.canonicalSelections(detail.selected).map(item => `${item.driver_number}:${item.lap_number}`);
      if (selected.length !== detail.selected.length || selected.some(id => !plan.drivers.some(driver => driver.id === id.split(':')[0] && driver.laps.includes(Number(id.split(':')[1]))))) return;
      this.choices.set(saved.id, { ...this.choices.get(saved.id), selected, session_id: replay.sessionId });
      this.telemetryRequests.delete(saved.id);
    } else if (event.type === 'f1-telemetry-retry') this.telemetry.retry([plan.catalogQuery].filter(Boolean));
    else if (event.type === 'f1-telemetry-compare' && plan.compareQuery) {
      this.telemetryRequests.set(saved.id, plan.compareQuery); this.telemetry.retry([plan.compareQuery]);
    }
    this.revision++;
  }
  missingMessage(status) {
    return status === 'disabled' ? this.w('modular.enable_this_entity_in_f1_sensor_to_see_its_data')
      : status === 'missing' ? this.w('modular.this_data_source_is_not_available_in_this_installation')
        : this.w('modular.no_session_data_is_currently_available_your_settings_are_kept');
  }
  minisectorState(module) {
    if (this.modelPreview?.minisectors) return this.modelPreview.minisectors;
    const selection = resolveSelection(this.config.context, module, this.groupContext);
    const context = minisectorData.minisectorContext(this.sourceHass, this.entry, selection);
    if (!context) return { status: 'unavailable', reason: 'session_unavailable', drivers: {} };
    const shared = this.minisectorResources.get(context.key)?.state;
    if (!shared) return { status: 'loading', reason: null, drivers: {} };
    if (shared.data) return { ...shared.data, transportStatus: shared.status, transportError: shared.error ?? null };
    return { status: shared.status, reason: shared.status === 'error' ? 'subscription_unavailable' : null, drivers: {}, transportError: shared.error ?? null };
  }
  minisectorMessage(state) {
    if (state.status === 'loading' || state.transportStatus === 'refreshing') return this.w('modular.minisectors_waiting_for_status_data');
    if (state.reason === 'spoiler_protected') return this.w('modular.minisectors_hidden_by_spoiler_protection');
    if (state.reason === 'session_unavailable') return this.w('modular.minisectors_selected_session_unavailable');
    if (state.reason === 'source_inactive') return this.w('modular.minisectors_waiting_for_active_source');
    return this.w('modular.minisectors_unavailable_timing_continues');
  }
  clockDescription(clock) {
    if (clock.notApplicable) return this.w('modular.available_for_race_sessions');
    if (clock.value === null) return clock.contextMismatch ? this.w('modular.clock_belongs_to_another_session_or_qualifying_part') : clock.phase === 'idle' ? this.w('modular.session_clock_has_not_started') : this.missingMessage(clock.source.status);
    if (clock.cap) return [this.w('modular.from_race_start_includes_session_interruptions'), ['paused', 'seeking'].includes(clock.replay) ? this.w('modular.replay_paused') : null].filter(Boolean).join(' · ');
    const phases = { running: ['Running', 'Pågår'], paused: ['Paused', 'Pausad'], finished: ['Finished', 'Avslutad'], overtime: ['Time expired', 'Tiden har löpt ut'] };
    const qualities = { official: ['Official clock', 'Officiell klocka'], official_no_heartbeat: ['Clock without heartbeat confirmation', 'Klocka utan bekräftande heartbeat'], sessiondata_fallback: ['Estimated from session events', 'Beräknad från sessionshändelser'] };
    return [phases[clock.phase] ? this.w(...phases[clock.phase]) : this.w('modular.clock_status_unknown'), qualities[clock.quality] ? this.w(...qualities[clock.quality]) : this.w('modular.clock_source_uncertain'), clock.part ? `${this.w('modular.part')} ${clock.part}` : null].filter(Boolean).join(' · ');
  }
  buildModels() {
    const entry = this.entry, settings = this.settings, session = data.sessionContext(this.sourceHass, entry);
    const protection = data.spoilerState(this.sourceHass, entry, this.config.context.spoilers);
    const hiddenMessage = protection === 'protected' ? this.w('modular.spoiler_protection_is_active') : this.w('modular.spoiler_status_cannot_be_verified_refresh_f1_sensor_before_showing_sensitive_data');
    const models = new Map(); this.retainedRoster = null;
    for (const module of this.config.modules) {
      const definition = MODULES[module.type];
      const focus = module.focus_mode === 'independent' ? {} : this.focus;
      const model = { title: moduleTitle(module, this.language) };
      if (!this.moduleVisible(module)) { model.hidden = true; models.set(module.id, model); continue; }
      const selection = resolveSelection(this.config.context, module, this.groupContext), sessionState = this.moduleSessionState(module);
      const effective = data.resolveWeatherModule(this.sourceHass, entry, { ...module, selection, options: { ...module.options, ...this.choices.get(module.id) } });
      const sensitive = definition?.spoiler || ['timing', 'race_control'].includes(module.type) || module.type === 'weather' && effective.options.content === 'track_conditions';
      if (sensitive && protection !== 'clear') {
        const placeholder = protection === 'protected' && typeof module.options?.spoiler_placeholder === 'string' ? module.options.spoiler_placeholder.trim() : '';
        model.blocked = placeholder || hiddenMessage; models.set(module.id, model); continue;
      }
      if (!module.when.includes(sessionState.phase)) { model.hidden = true; models.set(module.id, model); continue; }
      if (!sessionState.available) {
        model.blocked = sessionState.reason === 'archive_module_required'
          ? this.w('modular.this_module_cannot_read_an_archived_session_use_an_archive_module_for_this_pinned')
          : this.w('modular.the_pinned_session_is_not_available_from_the_selected_source_the_saved_identity_has');
        model.hidden = module.unavailable === 'hide'; models.set(module.id, model); continue;
      }
      if (module.type === 'weather' && effective.options.content === 'track_conditions' && !this.modelPreview && this.savedSources.weatherAwaitingObservation(this.sourceHass, entry)) {
        model.blocked = this.w('modular.waiting_for_a_new_track_weather_update_after_the_session_or_playback_context_changed');
        model.hidden = module.unavailable === 'hide'; models.set(module.id, model); continue;
      }
      const saved = this.savedSources.select(this.sourceHass, entry, effective, definition, Boolean(this.modelPreview));
      const viewHass = saved.hass, moduleSession = data.sessionContext(viewHass, entry);
      if (module.type === 'results') {
        Object.assign(model, season.resultsModel(viewHass, entry, effective, focus));
        if (effective.options.show_session_type_badge !== false && model.context?.session) model.badge = model.context.session;
      }
      if (module.type === 'standings') {
        Object.assign(model, season.standingsModel(viewHass, entry, effective, focus));
        if (effective.options.show_mode_badge !== false) model.badge = this.w('modular.published_standings');
        if (model.projection.requested) {
          if (model.projection.available) model.notice = this.w('modular.projected_columns_follow_the_current_session_published_positions_and_points_stay_separate');
          else {
            const auth = data.source(viewHass, entry, 'f1tv_token_status');
            const authNeedsAttention = auth.status === 'available' && ['expired', 'invalid', 'rejected', 'refresh_failed'].includes(String(auth.state).toLowerCase());
            if (authNeedsAttention) model.notice = this.w('modular.f1tv_access_needs_attention_so_live_championship_projections_are_hidden_published_standings_remain_available');
            else if (effective.options.show_availability_notice !== false) model.notice = this.w('modular.projection_unavailable_live_projections_need_f1tv_access_and_a_supported_race_feed_archived_replay');
          }
        }
      }
      if (module.type === 'archive') {
        Object.assign(model, season.archiveModel(effective, entry?.entry_id, query => this.modelPreview ? this.modelPreview.history?.(query) ?? { status: 'ready', data: { payload: null } } : this.history.read(query), this.modelPreview?.now ?? Date.now()));
        const archiveLabel = this.w('modular.historical_data');
        model.badge = effective.options.show_session_type_badge !== false && model.session?.name ? `${archiveLabel} · ${model.session.name}` : archiveLabel;
        model.notice = effective.options.content === 'lap_position'
          ? this.w('modular.positions_are_recorded_when_each_driver_completes_a_lap_they_are_not_simultaneous_track')
          : effective.options.content === 'lap_time' ? this.w('modular.published_race_laps_may_include_pit_laps_and_neutralisations_sector_times_telemetry_and_clean') : null;
      }
      if (module.type === 'progression') Object.assign(model, season.progressionModel(viewHass, entry, effective, focus));
      if (module.type === 'replay') {
        Object.assign(model, data.replayModel(viewHass, entry));
        model.request = this.replayRequests.get(entry?.entry_id);
      }
      if (module.type === 'telemetry') {
        const demo = this.modelPreview;
        const selected = demo ? { ...effective, options: { ...effective.options, selected: ['4:2', '16:2'], session_id: 'demo-replay' } } : effective;
        const read = query => demo ? demo.telemetry?.(query) ?? { status: 'ready', data: null } : this.telemetry.read(query);
        const requested = demo ? telemetryData.telemetryPlan(selected, entry, data.replayModel(viewHass, entry), read).compareQuery : this.telemetryRequests.get(module.id);
        Object.assign(model, telemetryData.telemetryModel(viewHass, entry, selected, read, requested));
        model.badge = this.w('modular.recorded_replay');
        model.readonly = Boolean(this.preview || demo || this.frozen);
      }
      if (module.type === 'lap_chart') {
        Object.assign(model, data.lapChartModel(viewHass, entry, effective, focus));
        model.title = module.options.metric === 'lap_change' ? this.w('modular.lap_changes') : this.w('modular.recorded_lap_times');
        if (model.invalidRange) model.blocked = this.w('modular.the_first_lap_is_after_the_last_lap_adjust_the_lap_range_in_the');
        model.notice = module.options.metric === 'lap_change'
          ? this.w('modular.each_change_compares_the_same_driver_with_their_preceding_lap_negative_values_mean_a')
          : this.w('modular.recorded_laps_may_include_pit_laps_neutralisations_and_different_qualifying_parts_this_view_does');
      }
      if (module.type === 'documents') Object.assign(model, season.documentsModel(viewHass, entry, effective));
      if (module.type === 'map') {
        const driverPositions = data.source(viewHass, entry, 'driver_positions');
        Object.assign(model, mapModel(this.modelPreview?.map ?? this.mapState.data?.snapshot, effective, focus, this.modelPreview?.now ?? Date.now(), driverPositions.status === 'available' ? data.array(driverPositions.attributes.drivers) : []));
        const laps = data.source(viewHass, entry, 'race_lap_count'), trackStatus = data.source(viewHass, entry, 'track_status');
        const currentLap = Number(laps.state), totalLaps = Number(laps.attributes.total_laps);
        model.lap = laps.status === 'available' && Number.isInteger(currentLap) && currentLap >= 0 ? currentLap : null;
        model.totalLaps = Number.isInteger(totalLaps) && totalLaps > 0 ? totalLaps : null;
        model.trackStatus = trackStatus.status === 'available' ? trackStatus.state : null;
        if (model.pending) model.blocked = this.mapState.status === 'error' ? this.w('modular.map_data_is_unavailable_check_the_selected_f1_sensor_installation') : this.w('modular.waiting_for_map_data');
        if (!this.modelPreview && ['error', 'disconnected', 'refreshing'].includes(this.mapState.status) && !model.pending) {
          if (module.unavailable === 'retain') { model.freshness.stale = true; model.rows = model.rows.map(row => ({ ...row, stale: true })); }
          else model.blocked = this.w('modular.map_connection_interrupted_your_settings_are_kept');
        }
        if (model.blocked && module.unavailable === 'hide' && !this.modelPreview) model.hidden = true;
      }
      if (definition?.stream === 'analysis') {
        const adapter = module.type === 'strategy' ? analysisData.strategyModel : module.type === 'battles' ? analysisData.battlesModel : analysisData.timelineModel;
        Object.assign(model, adapter(this.modelPreview?.analysis ?? this.analysisState.data, effective, focus));
        if (model.pending) model.blocked = this.analysisState.status === 'error'
          ? this.w('modular.session_analysis_is_unavailable_check_that_this_f1_sensor_installation_has_its_analysis_features')
          : this.w('modular.waiting_for_session_analysis');
        if (model.context) { model.context.updated = this.modelPreview ? new Date(this.modelPreview.now).toISOString() : this.analysisState.received_at; model.context.updatedKind = 'received'; }
        if (!this.modelPreview && ['disconnected', 'error', 'refreshing'].includes(this.analysisState.status) && !model.pending) {
          if (module.unavailable === 'retain') model.notice = this.w('modular.saved_analysis_connection_interrupted_events_may_be_incomplete');
          else model.blocked = this.w('modular.analysis_connection_interrupted_your_settings_are_kept');
        }
        if (model.blocked && module.unavailable === 'hide' && !this.modelPreview) model.hidden = true;
        if (module.fields.includes('analysis_quality')) model.notice = [model.notice, this.w('modular.evidence_score_measures_support_not_probability')].filter(Boolean).join(' ');
      }
      if (module.type === 'battles' && !model.pending) {
        model.badge = this.w('modular.local_estimate');
        model.emptyMessage = model.capability === 'waiting_for_positions' ? this.w('modular.waiting_for_usable_position_observations') : this.w('modular.no_matching_observations_for_this_session');
        model.explanation = [model.explanation, this.w('modular.these_observations_come_from_timing_analysis_a_position_exchange_does_not_always_mean_an')].filter(Boolean).join(' ');
        if (model.active && model.threshold !== null) model.explanation += this.w('modular.the_analysis_uses_a_threshold_s_gap_threshold_and_repeated_observations', { threshold: model.threshold });
      }
      if (module.type === 'strategy' && !model.pending) {
        model.badge = this.w('modular.local_estimate');
        if (model.qualityFiltered) model.emptyMessage = this.w('modular.no_estimates_meet_the_selected_evidence_and_sample_requirements');
        if (model.comparison === 'teammates') model.explanation = [model.explanation, this.w('modular.teammate_medians_can_cover_different_laps_tyre_compounds_fuel_loads_and_traffic')].filter(Boolean).join(' ');
        if (model.comparison === 'crossover') model.explanation = [model.explanation, this.w('modular.the_crossover_is_an_estimate_within_the_observed_tyre_age_range_across_all_drivers')].filter(Boolean).join(' ');
        if (model.comparison === 'pit_outcomes') model.explanation = [model.explanation, this.w('modular.pit_cycle_outcomes_compare_teammate_positions_before_and_after_nearby_stops_the_observed_order')].filter(Boolean).join(' ');
        if (model.capability === 'waiting_for_clean_laps') model.emptyMessage = this.w('modular.waiting_for_usable_clean_laps_pace_estimates_will_appear_when_enough_recorded_lap_data');
        model.explanation = [model.explanation, this.w('modular.pace_and_degradation_use_recorded_clean_laps_they_are_local_estimates_not_official_strategy')].filter(Boolean).join(' ');
        if (module.fields.includes('strategy_pit_loss')) model.explanation += this.w('modular.stint_change_loss_compares_the_first_lap_of_a_stint_with_the_preceding_stint');
      }
      if (module.type === 'tyres') {
        Object.assign(model, sessionData.tyresModel(viewHass, entry, effective, focus));
        if (model.waiting) model.notice = this.w('modular.waiting_for_compound_information_from_timingappdata_lap_counts_alone_do_not_identify_a_tyre');
        if (model.statistics && !model.waiting) model.notice = this.w('modular.recorded_laps_across_all_drivers_and_stints_differences_include_fuel_track_conditions_and_traffic');
      }
      if (module.type === 'pit_stops') {
        Object.assign(model, sessionData.pitStopsModel(viewHass, entry, effective, focus));
        if (model.source.status !== 'available') {
          const auth = data.source(viewHass, entry, 'f1tv_token_status');
          const authNeedsAttention = auth.status === 'available' && ['expired', 'invalid', 'rejected', 'refresh_failed'].includes(String(auth.state).toLowerCase());
          if (authNeedsAttention) model.capabilityMessage = this.w('modular.f1tv_access_needs_attention_so_live_pit_stop_data_is_hidden_replay_data_remains');
          else if (module.options.show_availability_notice !== false) model.capabilityMessage = this.w('modular.pit_stop_timing_needs_f1tv_access_and_a_supported_feed_or_an_archived_replay');
        }
        if (module.fields.includes('pit_delta')) model.notice = this.w('modular.estimated_lap_loss_the_longer_of_the_in_out_laps_minus_the_median_reference');
      }
      if (module.type === 'incidents') {
        Object.assign(model, sessionData.incidentsModel(viewHass, entry, effective, focus));
        if (model.summary) model.notice = this.w('modular.only_drivers_with_recorded_track_limit_data_are_listed_a_missing_driver_is_not');
      }
      if (module.type === 'timing') {
        const minisectors = minisectorData.usesMinisectors(module, this.moduleNodes.get(module.id)?.timingExpanded?.length > 0) ? this.minisectorState(effective) : null;
        Object.assign(model, data.timingRows(viewHass, entry, moduleSession, this.sectors, module, focus, minisectors));
        model.context = { meeting: moduleSession.meeting, session: moduleSession.name, key: moduleSession.key, source: 'TimingData', updated: model.source.updated_at, updatedKind: 'ha_state' };
        model.selectionGeneration = this.savedSources.viewGeneration;
        if (model.currentPart && ['qualifying', 'sprint_qualifying'].includes(model.sessionKind)) model.badge = `${model.sessionKind === 'sprint_qualifying' ? 'SQ' : 'Q'}${model.currentPart}`;
        if (model.fields.some(id => /^q[123]_/.test(id)) && !['qualifying', 'sprint_qualifying'].includes(model.sessionKind)) model.notice = this.w('modular.q_sq_columns_are_available_during_qualifying_sessions_other_columns_continue_to_show_their');
        if (minisectors && minisectors.status !== 'ready') model.notice = [model.notice, this.minisectorMessage(minisectors)].filter(Boolean).join(' ');
      }
      if (module.type === 'minisectors') {
        const minisectors = this.minisectorState(effective);
        Object.assign(model, data.timingRows(viewHass, entry, moduleSession, this.sectors, module, focus, minisectors));
        model.context = { meeting: moduleSession.meeting, session: moduleSession.name, key: moduleSession.key, source: 'TimingData status segments', updated: minisectors.generated_at, updatedKind: 'received' };
        model.minisectorStatus = minisectors.status;
        if (minisectors.status !== 'ready') {
          model.blocked = this.minisectorMessage(minisectors);
          if (module.unavailable === 'hide' && !this.modelPreview) model.hidden = true;
        } else if (minisectors.transportStatus && minisectors.transportStatus !== 'ready') model.notice = this.w('modular.minisectors_connection_interrupted_retained');
      }
      if (module.type === 'calendar') {
        Object.assign(model, data.scheduleRows(viewHass, entry, module, this.modelPreview?.now ?? Date.now()));
        model.rows = model.rows.map(row => {
          const zone = module.options.timezone === 'utc' ? 'UTC' : module.options.timezone === 'circuit' ? row.timezone : settings.timezone;
          const displayZone = zone ?? settings.timezone;
          return { ...row, display_timezone: displayZone, timezone_label: displayZone ?? this.w('modular.circuit_zone_unavailable_home_time'),
            track_timezone: module.options.show_track_time && row.timezone && row.timezone !== displayZone ? row.timezone : null };
        });
      }
      if (module.type === 'weather') {
        const weather = data.weatherValues(viewHass, entry, effective); Object.assign(model, weather);
        if (weather.track) {
          model.badge = weather.replay ? this.w('modular.recorded_replay') : this.w('modular.track_observations');
          model.explanation = this.w('modular.the_measurement_time_is_not_exposed_by_this_source_the_home_assistant_update_time');
        } else {
          if (weather.forecast) model.badge = this.w('modular.forecast');
          model.explanation = this.w('modular.current_circuit_weather_and_the_forecast_nearest_race_start_an_observation_time_and_precipitation');
        }
        if (weather.automatic) {
          if (!weather.track) model.badge = this.w('modular.current_weather');
          const selectionExplanation = weather.track ? this.w('modular.automatic_source_track_observations_missing_measurements_are_not_replaced_with_forecast_values') : this.w('modular.automatic_source_current_weather_track_observations_require_a_confirmed_active_session_and_usable_measurements');
          model.explanation = [model.explanation, selectionExplanation].filter(Boolean).join(' ');
        }
        model.explanationTitle = this.w('modular.about_the_weather_data');
        model.items = module.fields.filter(id => weather.values[id]).map(id => { const item = weather.values[id]; return { id, ...item,
          detail: weather.mixed ? item.estimated ? this.w('modular.forecast_near_race_start') : this.w('modular.current_circuit_weather') : null }; });
        if (model.source.status !== 'available') model.capabilityMessage = weather.track ? this.w('modular.track_weather_observations_are_not_available_for_this_session') : this.w('modular.circuit_weather_is_currently_unavailable');
      }
      if (module.type === 'overview') {
        const event = data.overviewEvent(viewHass, entry, selection), track = data.source(viewHass, entry, 'track_status'), laps = data.source(viewHass, entry, 'race_lap_count');
        const attrs = event.attributes, start = Date.parse(attrs.race_start_utc ?? attrs.race_start), remaining = start - (this.modelPreview?.now ?? Date.now());
        const countdown = event.replay ? this.w('modular.not_available_for_replay')
          : !Number.isFinite(remaining) ? '—' : remaining <= 0 ? this.w('modular.scheduled_start_passed') : [
            translatePlural(this.language, 'modular.day_count', Math.floor(remaining / 86400000)),
            translatePlural(this.language, 'modular.hour_count', Math.floor(remaining % 86400000 / 3600000)),
          ].join(' ');
        const clocks = Object.fromEntries(['session_time_elapsed', 'session_time_remaining', 'race_time_to_three_hour_limit'].map(key => [key, data.sessionClock(viewHass, entry, key, session)]));
        const currentLap = Number(laps.state), totalLaps = Number(laps.attributes.total_laps);
        const lapProgress = laps.status === 'available' && Number.isInteger(currentLap) && currentLap >= 0 ? `${currentLap}${Number.isInteger(totalLaps) && totalLaps > 0 ? ` / ${totalLaps}` : ''}` : null;
        const values = { ...Object.fromEntries(Object.entries(clocks).map(([key, clock]) => [key, protection === 'clear' ? clock.value : hiddenMessage])), meeting: attrs.race_name, circuit: attrs.circuit_name, country: attrs.circuit_country, countdown,
          circuit_map: { url: safeImageUrl(attrs.circuit_map_url), circuit: attrs.circuit_name, locality: attrs.circuit_locality, country: attrs.circuit_country, season: attrs.season },
          circuit_history: { defending_winner: attrs.defending_winner, defending_pole_sitter: attrs.defending_pole_sitter, races_held_here: attrs.races_held_here, first_f1_race_here: attrs.first_f1_race_here, last_year_podium: attrs.last_year_podium, last_5_winners: attrs.last_5_winners, top_5_driver_wins_here: attrs.top_5_driver_wins_here, top_5_constructor_wins_here: attrs.top_5_constructor_wins_here, dnf_rate_last_5: attrs.dnf_rate_last_5, pole_to_win_conversion_last_5: attrs.pole_to_win_conversion_last_5 },
          session: session.name ?? this.w('modular.between_sessions'), session_status: ['unavailable', 'unknown'].includes(session.status) ? null : session.status, lap_progress: protection === 'clear' ? lapProgress : hiddenMessage, track_status: protection === 'clear' ? track.status === 'available' ? track.state : null : hiddenMessage };
        model.items = module.fields.filter(id => Object.hasOwn(values, id)).map(id => ({ id, value: values[id], flag: id === 'meeting' ? safeImageUrl(attrs.country_flag_url) : null, country: attrs.circuit_country,
          detail: clocks[id] ? protection === 'clear' ? this.clockDescription(clocks[id]) : null : id === 'track_status' && protection === 'clear' && track.status !== 'available' ? this.missingMessage(track.status) : null }));
        if (event.replay && !event.context_available) model.notice = this.w('modular.waiting_for_event_information_from_the_loaded_replay');
        else if (event.replay && !event.calendar_match) model.notice = this.w('modular.the_replay_event_is_not_available_in_the_loaded_season_calendar_replay_provided_details');
      }
      if (module.type === 'race_control') {
        const current = data.source(viewHass, entry, 'race_control'); model.source = current;
        const currentMessage = module.options.presentation === 'latest_message' && current.attributes.message ? [current.attributes] : [];
        let rows = data.mergeEvents(this.modelPreview?.events ?? this.eventState.data, currentMessage);
        model.rows = data.filterRaceControl(rows, viewHass, entry, module, focus);
        model.raceControlContext = JSON.stringify([entry.entry_id, current.entity_id ?? '', current.attributes.session_id ?? current.attributes.session_name ?? '']);
        if (!this.modelPreview && ['disconnected', 'error', 'refreshing'].includes(this.eventState.status)) model.notice = this.w('modular.connection_interrupted_saved_messages_may_be_incomplete');
      }
      if (model.source && ['missing', 'disabled', 'unavailable', 'unknown'].includes(model.source.status)) {
        if (['missing', 'disabled'].includes(model.source.status) || module.unavailable !== 'retain' || (!model.rows?.length && !model.items?.length && !model.series?.length)) model.blocked = model.source.status === 'disabled' ? this.missingMessage('disabled') : model.capabilityMessage ?? this.missingMessage(model.source.status);
        else model.notice = this.w('modular.saved_data_source_currently_unavailable');
        if (module.unavailable === 'hide' && !this.modelPreview) model.hidden = true;
      }
      if (saved.retained) {
        model.retained = true;
        this.retainedRoster ??= data.source(viewHass, entry, 'driver_list');
        model.notice = [...new Set([model.notice, this.w('modular.saved_data_source_currently_unavailable')].filter(Boolean))].join(' ');
      }
      model.timeInfo = data.modelTimestamp(model, this.modelPreview?.now ?? Date.now());
      // A connected HA socket does not prove upstream freshness. An explicitly
      // disconnected socket does prove that live updates cannot reach this card.
      if (!this.modelPreview && this.sourceHass.connection?.connected === false && !['archive', 'replay', 'telemetry'].includes(module.type)) {
        if (module.unavailable !== 'retain') model.blocked = this.w('modular.home_assistant_is_disconnected_data_returns_after_reconnection_your_settings_are_kept');
        if (module.unavailable === 'hide') model.hidden = true;
      }
      models.set(module.id, model);
    }
    return models;
  }
  render() {
    if (!this.config || !this.sourceHass) return html``;
    const settings = this.settings, dark = settings.mode === 'dark', high = settings.accessibility.high_contrast;
    const haStyle = settings.appearance.style === 'ha' && settings.appearance.mode === 'auto' && !high;
    const background = haStyle ? 'var(--ha-card-background,var(--card-background-color))' : high ? dark ? '#000000' : '#ffffff' : dark ? '#141920' : '#ffffff';
    const text = haStyle ? 'var(--primary-text-color)' : dark ? '#f1f4f8' : '#1a2533';
    const muted = haStyle ? 'var(--secondary-text-color)' : high ? text : dark ? '#bdc6d4' : '#536174';
    const density = settings.appearance.density;
    const spacing = density === 'compact' ? [16, 10, 16, 14, '5px 9px', '5px'] : density === 'spacious' ? [24, 16, 32, 24, '15px 16px', '14px'] : [20, 12, 26, 20, '10px 12px', '9px'];
    const typography = settings.appearance.font === 'f1';
    const accent = cardAccent(settings.appearance, this.modelPreview?.accentTeams ?? data.accentTeams(this.sourceHass, this.entry), settings.mode);
    const radius = settings.appearance.surface === 'framed' ? '8px' : settings.appearance.surface === 'soft' ? '20px' : settings.appearance.surface === 'flat' ? '0' : 'var(--ha-card-border-radius,14px)';
    const style = `--_f1-card-padding:${spacing[0]}px;--_f1-minimal-padding:${spacing[1]}px;--_f1-module-gap:${spacing[2]}px;--_f1-section-space:${spacing[3]}px;--_f1-cell-padding:${spacing[4]};--_f1-item-padding:${spacing[5]};--_f1-heading-font:${typography ? "'F1 Barlow Condensed',sans-serif" : 'var(--ha-font-family-heading,var(--ha-font-family-body,inherit))'};--_f1-heading-transform:${typography ? 'uppercase' : 'none'};--_f1-module-heading-size:${typography ? '1.3em' : '1.1em'};--_f1-surface:${background};--_f1-text:${text};--_f1-muted:${muted};--_f1-border:${dark ? '#637083' : '#778397'};--_f1-divider:${dark ? '#354150' : '#cbd1da'};--_f1-panel:${dark ? '#1b2430' : '#f1f4f8'};--_f1-focus:${dark ? '#7ebfff' : '#005db5'};--_f1-row-alternate:${settings.appearance.surface === 'soft' ? 'var(--f1-panel)' : 'transparent'};--_f1-accent:${accent.color};--_f1-numerals:${settings.appearance.numbers === 'tabular' ? 'tabular-nums' : 'normal'};--_f1-card-radius:${radius}`;
    if (!this.entry) return html`<ha-card part="card" data-style=${settings.appearance.style} data-font=${settings.appearance.font} data-surface=${settings.appearance.surface} data-accent=${String(accent.visible)} role="group" aria-label=${this.config.title} style=${style}>${this.previewControls()}${settings.appearance.show_header ? html`<header class="heading" part="header">${this.actionHeading()}</header>` : ''}<div class="empty" part="empty-state">${this.discovery?.status === 'error' ? this.discovery.error : (this.modelPreview?.entries ?? this.entries).length > 1 ? this.w('modular.choose_an_f1_sensor_installation_in_the_editor') : this.w('modular.waiting_for_f1_sensor')}</div>${this.actionAlternatives()}</ha-card>`;
    const models = this.frozen ? this.frozenModels : this.buildModels();
    const protection = data.spoilerState(this.sourceHass, this.entry, this.config.context.spoilers);
    const modules = this.config.modules.filter(module => module.enabled && this.moduleVisible(module) && !models.get(module.id)?.hidden);
    const active = modules.some(module => module.id === this.tab) ? this.tab : modules[0]?.id;
    const hasDriverFocus = modules.some(module => moduleFocusKinds(module).includes('driver'));
    const currentRoster = this.frozen ? this.frozenRoster : data.source(this.sourceHass, this.entry, 'driver_list');
    const roster = currentRoster.status === 'available' ? currentRoster : this.retainedRoster ?? currentRoster;
    const drivers = hasDriverFocus && roster.status === 'available' ? data.array(roster.attributes.drivers).filter(item => item && typeof item === 'object') : [];
    const focusedDriver = (this.frozen ? this.frozenFocus : this.focus)?.driver ?? '';
    const groupSelections = [[{ mode: 'follow', source: 'auto' }, this.w('modular.group_automatic_session')], [{ mode: 'follow', source: 'live' }, this.w('modular.group_live_session')], [{ mode: 'follow', source: 'replay' }, this.w('modular.group_loaded_replay')]];
    if (this.config.context.selection.mode === 'pinned') groupSelections.push([this.config.context.selection, this.w('modular.group_this_pinned_session')]);
    const selectedGroup = this.groupContext.selection ?? (this.config.context.selection.mode === 'follow' ? this.config.context.selection : { mode: 'follow', source: 'auto' });
    if (!groupSelections.some(([selection]) => JSON.stringify(selection) === JSON.stringify(selectedGroup))) groupSelections.push([selectedGroup, this.w('modular.group_shared_pinned_session')]);
    const groupSelection = JSON.stringify(selectedGroup);
    const nodes = modules.map(module => {
      let node = this.moduleNodes.get(module.id);
      if (!node) {
        node = document.createElement('f1-module-view');
        node.addEventListener('f1-replay-action', event => this.replayAction(event));
        node.addEventListener('f1-race-control-action', event => this.raceControlAction(event));
        node.addEventListener('f1-driver-details-change', () => { this.revision++; });
        for (const type of ['selection', 'compare', 'retry']) node.addEventListener(`f1-telemetry-${type}`, event => this.telemetryAction(event));
        node.addEventListener('f1-module-choice', event => {
          event.stopPropagation();
          if (!this.config.modules.some(item => item.id === event.detail.module)) return;
          const saved = this.config.modules.find(item => item.id === event.detail.module);
          if (saved.type === 'archive' && event.detail.key === 'retry') {
            if (!this.modelPreview && !this.preview && data.spoilerState(this.sourceHass, this.entry, this.config.context.spoilers) === 'clear') this.history.retry(season.archivePlan({ ...saved, options: { ...saved.options, ...this.choices.get(saved.id) } }, this.entry.entry_id, query => this.history.read(query)).requests);
            return;
          }
          const reset = saved.type !== 'archive' ? {} : event.detail.key === 'year' ? { round: '', session_key: '', selected: [] } : event.detail.key === 'round' ? { session_key: '', selected: [] } : event.detail.key === 'session_key' ? { selected: [] } : {};
          this.choices.set(event.detail.module, { ...this.choices.get(event.detail.module), ...reset, [event.detail.key]: event.detail.value });
          this.frozen = false; this.revision++;
        });
        this.moduleNodes.set(module.id, node);
      }
      node.module = models.get(module.id)?.fields ? { ...module, fields: models.get(module.id).fields } : module; node.model = ['replay', 'telemetry', 'race_control'].includes(module.type) ? { ...models.get(module.id), readonly: Boolean(this.preview || this.modelPreview || this.frozen), frozen: this.frozen, ...(module.type === 'race_control' ? { request: this.raceControlRequest } : {}) } : models.get(module.id); node.settings = settings;
      node.hidden = this.config.layout === 'tabs' && active !== module.id;
      node.id = `module-${module.id}`;
      node.dataset.moduleType = module.type;
      node.dataset.moduleId = module.id;
      node.dataset.columnSpan = String(module.column_span);
      node.style.setProperty('--_f1-module-span', String(module.column_span === 'full' ? 1 : module.column_span));
      node.setAttribute('part', 'module');
      return node;
    });
    for (const id of this.moduleNodes.keys()) if (!this.config.modules.some(module => module.id === id)) this.moduleNodes.delete(id);
    return html`<ha-card data-layout=${this.config.layout} part="card" data-style=${settings.appearance.style} data-font=${settings.appearance.font} data-surface=${settings.appearance.surface} data-accent=${String(accent.visible)} role="group" aria-label=${this.config.title} style=${style}>
      ${this.previewControls()}
      ${this.modelPreview ? html`<p class="demo">${this.w('modular.demo_sample_data')}</p>` : ''}
      <header part="header">${settings.appearance.show_header ? html`<div class="heading" part="title">${this.actionHeading()}<small>${this.w('modular.your_formula_1_view')}</small></div>` : ''}
        <div class="tools" part="toolbar">${this.config.context.show_focus_control && drivers.length ? html`<label><span class="sr">${this.w('modular.driver_focus')}</span><select .value=${focusedDriver} @change=${this.chooseDriver}><option value="" .selected=${!focusedDriver}>${this.w('modular.all_drivers')}</option>${repeat(drivers, driver => String(driver.racing_number), driver => html`<option value=${String(driver.racing_number)} .selected=${focusedDriver === String(driver.racing_number)}>${driver.tla ?? driver.racing_number}</option>`)}</select></label>` : ''}
        ${this.group && this.config.context.share.includes('selection') ? html`<label><span class="sr">${this.w('modular.shared_session_selection')}</span><select .value=${groupSelection} @change=${this.chooseGroupSelection}>${groupSelections.map(([selection, title]) => html`<option value=${JSON.stringify(selection)}>${title}</option>`)}</select></label>` : ''}
        ${this.config.context.show_freeze_control ? html`<button @click=${this.freeze} aria-pressed=${String(this.frozen)}>${this.frozen ? this.w('modular.resume') : this.w('modular.freeze_view')}</button>` : ''}</div>
      </header>
      ${this.actionAlternatives()}
      ${!this.modelPreview && this.sourceHass.connection?.connected === false ? html`<p class="connection-status" part="connection-status" role="status">${this.w('modular.disconnected_from_home_assistant_any_visible_values_are_saved_snapshots_live_updates_resume_after')}</p>` : ''}
      ${this.config.context.viewing_controls ? html`<f1-viewing-controls part="viewing-controls" .model=${data.viewingModel(this.sourceHass, this.entry, this.config.context.spoilers)} .settings=${settings} .connection=${this.sourceHass.connection} .readonly=${Boolean(this.preview || this.modelPreview || this.frozen)} .localHidden=${this.config.context.spoilers === 'hide'} .request=${this.viewingRequest?.entryId === this.entry.entry_id && this.viewingRequest.connection === this.sourceHass.connection ? this.viewingRequest : null} @f1-viewing-action=${this.viewingAction}></f1-viewing-controls>` : ''}
      <div aria-live=${settings.accessibility.announce ? 'polite' : 'off'} aria-atomic="true">${this.frozen ? html`<p class="frozen">${this.w('modular.reading_snapshot')} · ${dateTime(this.frozenAt, settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' })} · ${this.w('modular.only_this_card_is_paused')}${this.frozenGeneration !== this.savedSources.viewGeneration ? html`<br>${this.w('modular.session_or_playback_settings_have_changed_this_snapshot_keeps_its_original_context_resume_to')}` : ''}${this.focus.driver !== this.frozenFocus?.driver || this.focus.team !== this.frozenFocus?.team ? html`<br>${this.w('modular.group_focus_has_changed_resume_to_follow_it')}` : ''}</p>` : ''}</div>
      ${this.config.layout === 'tabs' ? html`<nav part="tabs" aria-label=${this.w('modular.modules')}>${modules.map(module => html`<button aria-pressed=${String(active === module.id)} aria-controls=${`module-${module.id}`} @click=${() => { this.tab = module.id; }}>${module.title || models.get(module.id).title}</button>`)}</nav>` : ''}
      ${nodes.length ? html`<div class="modules" part="modules" data-layout=${this.config.layout} style=${`--_f1-max-columns:${this.config.columns}`}>${nodes}</div>` : this.emptyCard()}
      ${configWarnings(this.config).length ? html`<p class="muted">${this.w('modular.some_settings_need_a_newer_card_version_they_are_preserved_in_the_editor')}</p>` : ''}
    </ha-card>`;
  }
  emptyCard() { return html`<div class="empty" part="empty-state">${this.config.modules.length ? this.w('modular.no_modules_are_visible_under_the_current_conditions') : this.w('modular.add_your_first_module_in_the_editor')}</div>`; }
}
if (!customElements.get('f1-sensor-card')) customElements.define('f1-sensor-card', F1SensorCard);
