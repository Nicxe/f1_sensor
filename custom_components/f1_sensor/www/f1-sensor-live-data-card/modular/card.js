const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, css, repeat }, { normalizeConfig, configWarnings, resolveSelection }, { MODULES, label, moduleTitle, moduleFocusKinds }, data, { SectorStore, safeImageUrl, cardAccent }, { watchEntries, watchRaceControl, watchGroup, watchAnalysis, watchTrackMap, HistoryResources, callEntityService }, { sharedStyles, words, dateTime }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./config.js'), load('./catalog.js'), load('./data.js'), load('./semantics.js'), load('./connection.js'), load('./view.js'),
]);
const { ensureTypography } = await load('./typography.js');
await load('./viewing-controls.js');
const season = await load('./season-data.js');
const sessionData = await load('./session-data.js');
const analysisData = await load('./analysis-data.js');
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
    nav { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:20px; }
    .frozen { padding:10px 12px; margin-bottom:16px; border:1px solid currentColor; border-radius:8px; }
    .connection-status { padding:10px 12px; margin:0 0 16px; border:1px solid currentColor; border-radius:8px; }
    .demo { font-size:.85em; padding:6px 0 12px; font-weight:650; }
    @media(max-width:360px) { :where(ha-card) { --f1-card-padding:14px; } }
  `];
  constructor() {
    super(); this.entries = []; this.revision = 0; this.frozen = false; this.tab = ''; this.focus = {}; this.groupContext = {};
    this.savedSources = new data.RetainedSources();
    this.history = new HistoryResources(() => { this.revision++; });
    this.telemetry = new HistoryResources(() => { this.revision++; }); this.telemetryRequests = new Map();
    this.viewingRequest = null; this.raceControlRequest = null; this.replayRequests = new Map(); this.sectors = new SectorStore(); this.choices = new Map(); this.moduleNodes = new Map(); this.eventState = { data: [], status: 'loading' }; this.analysisState = { data: null, status: 'loading' }; this.mapState = { data: null, status: 'loading' };
  }
  setConfig(config) { this.cancelActions(); this.choices?.clear(); this.config = normalizeConfig(config); }
  static getStubConfig() { return normalizeConfig({}); }
  static async getConfigElement() { await load('./editor.js'); return document.createElement('f1-sensor-card-editor'); }
  getCardSize() { return 2 + (this.config?.modules?.filter(module => module.enabled).length ?? 1) * 4; }
  getGridOptions() { return { columns: 12, min_columns: 6, min_rows: 2 }; }
  async scheduleUpdate() {
    // Shared HA pushes can dirty many cards in the same microtask. Give each
    // card a browser task so one dashboard update cannot monopolize input.
    if (this.isConnected && !this.moduleNodes.size) await scheduleInitialRender(this);
    else await new Promise(resolve => setTimeout(resolve, 0));
    return super.scheduleUpdate();
  }
  connectedCallback() {
    super.connectedCallback();
    this.clock = setInterval(() => { this.revision++; }, 30_000);
    this.media = window.matchMedia('(prefers-color-scheme: dark)');
    this.themeChanged = () => { this.revision++; };
    this.media.addEventListener('change', this.themeChanged);
    this.requestUpdate();
  }
  disconnectedCallback() {
    super.disconnectedCallback(); cancelInitialRender(this); clearInterval(this.clock); clearTimeout(this.mapAgeTimer);
    this.cancelActions(); this.replayRequests.clear(); this.viewingRequest = null; this.raceControlRequest = null;
    this.media?.removeEventListener('change', this.themeChanged);
    this.stopSources();
  }
  stopSources() {
    this.savedSources.clear();
    this.frozen = false; this.frozenModels = null; this.frozenFocus = null; this.frozenRoster = null; this.frozenGeneration = null;
    this.history.close(); this.telemetry.close(); this.telemetryRequests.clear(); this.telemetryContext = '';
    this.stopEntries?.(); this.stopEvents?.(); this.stopAnalysis?.(); this.stopMap?.(); this.group?.close();
    this.stopEntries = this.stopEvents = this.stopAnalysis = this.stopMap = this.group = null; this.mapKey = ''; this.mapState = { data: null, status: 'loading' }; this.analysisKey = ''; this.analysisState = { data: null, status: 'loading' };
    this.connection = null; this.eventKey = ''; this.groupKey = ''; this.groupContext = {}; this.sectors.reset();
  }
  get language() { return this.hass?.locale?.language ?? this.hass?.language ?? 'en'; }
  w(en, sv) { return words(this.language, en, sv); }
  get entry() {
    const entries = this.previewData?.entries ?? this.entries;
    return this.config?.f1_entry_id ? entries.find(entry => entry.entry_id === this.config.f1_entry_id) : entries.length === 1 ? entries[0] : null;
  }
  get settings() {
    const saved = this.config.appearance;
    const appearance = { ...saved, font: saved.font === 'auto' ? saved.style === 'f1' ? 'f1' : 'system' : saved.font };
    const mode = appearance.mode === 'auto' ? (this.hass?.themes?.darkMode ?? this.media?.matches ?? true) ? 'dark' : 'light' : appearance.mode;
    const timePreference = this.hass?.locale?.time_zone;
    const timezone = timePreference === 'local' ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : timePreference && timePreference !== 'server' ? timePreference : this.hass?.config?.time_zone ?? 'UTC';
    return { appearance, accessibility: this.config.accessibility, mode, language: this.language, timezone, timeFormat: this.hass?.locale?.time_format };
  }
  willUpdate(changed) {
    if (!this.hass || !this.config || !this.isConnected) return;
    this.savedSources.update(this.hass, this.entry, this.config, Boolean(this.previewData));
    if (this.settings.appearance.font === 'f1') ensureTypography();
    const activeModule = this.shadowRoot?.activeElement;
    this.focusRestore = activeModule?.localName === 'f1-module-view' && activeModule.shadowRoot?.activeElement?.dataset?.focus
      ? { module: activeModule.module.id, control: activeModule.shadowRoot.activeElement.dataset.focus } : null;
    if (changed.has('config')) { this.focus = { driver: this.config.context.driver, team: this.config.context.team }; this.frozen = false; }
    if (this.frozen && data.spoilerState(this.hass, this.entry, this.config.context.spoilers) !== 'clear') { this.frozen = false; this.sectors.reset(); this.frozenModels = null; }
    if (!this.frozen) { this.frozenModels = null; this.frozenFocus = null; this.frozenRoster = null; this.frozenGeneration = null; }
    if (this.previewData) { if (this.connection) this.stopSources(); return; }
    if (this.connection !== this.hass.connection) {
      this.stopSources(); this.entries = []; this.connection = this.hass.connection;
      if (this.connection) this.stopEntries = watchEntries(this.hass, state => { this.discovery = state; if (state.data) this.entries = state.data; this.revision++; });
    }
    const entry = this.entry;
    if (this.viewingRequest && (this.viewingRequest.entryId !== entry?.entry_id || this.viewingRequest.connection !== this.hass.connection)) this.viewingRequest = null;
    const usable = module => module.enabled && this.moduleSessionState(module).available && module.when.includes(this.moduleSessionState(module).phase);
    const historyQueries = entry && data.spoilerState(this.hass, entry, this.config.context.spoilers) === 'clear'
      ? this.config.modules.filter(module => usable(module) && module.type === 'archive').flatMap(module => season.archivePlan({ ...module, selection: resolveSelection(this.config.context, module, this.groupContext), options: { ...module.options, ...this.choices.get(module.id) } }, entry.entry_id, query => this.history.read(query)).requests) : [];
    this.history.sync(this.hass, historyQueries);
    const replay = data.replayModel(this.hass, entry);
    const telemetryContext = replay.loaded && entry && data.spoilerState(this.hass, entry, this.config.context.spoilers) === 'clear' ? JSON.stringify([entry.entry_id, replay.sessionId]) : '';
    if (telemetryContext !== this.telemetryContext) { this.telemetryRequests.clear(); this.telemetryContext = telemetryContext; }
    for (const id of this.telemetryRequests.keys()) if (!this.config.modules.some(module => module.id === id && usable(module) && module.type === 'telemetry')) this.telemetryRequests.delete(id);
    const telemetryQueries = telemetryContext ? this.config.modules.filter(module => usable(module) && module.type === 'telemetry').flatMap(module => {
      const plan = telemetryData.telemetryPlan({ ...module, options: { ...module.options, ...this.choices.get(module.id) } }, entry, replay, query => this.telemetry.read(query), this.telemetryRequests.get(module.id));
      if (!plan.activeCompare) this.telemetryRequests.delete(module.id);
      return plan.requests;
    }) : [];
    this.telemetry.sync(this.hass, telemetryQueries);
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
    const mapKey = entry && this.config.modules.some(module => usable(module) && module.type === 'map') && data.spoilerState(this.hass, entry, this.config.context.spoilers) === 'clear' ? entry.entry_id : '';
    if (mapKey !== this.mapKey) {
      this.stopMap?.(); this.stopMap = null; this.mapKey = mapKey; this.mapState = { data: null, status: 'loading' };
      if (mapKey) this.stopMap = watchTrackMap(this.hass, mapKey, state => { this.mapState = state; this.revision++; });
    }
    const analysisKey = entry && this.config.modules.some(module => usable(module) && MODULES[module.type]?.stream === 'analysis') && data.spoilerState(this.hass, entry, this.config.context.spoilers) === 'clear' ? entry.entry_id : '';
    if (analysisKey !== this.analysisKey) {
      this.stopAnalysis?.(); this.stopAnalysis = null; this.analysisKey = analysisKey; this.analysisState = { data: null, status: 'loading' };
      if (analysisKey) this.stopAnalysis = watchAnalysis(this.hass, analysisKey, state => { this.analysisState = state; this.revision++; });
    }
    const eventKey = entry && this.config.modules.some(module => usable(module) && module.type === 'race_control') && data.spoilerState(this.hass, entry, this.config.context.spoilers) === 'clear' ? entry.entities?.race_control : '';
    if (eventKey !== this.eventKey) {
      this.stopEvents?.(); this.stopEvents = null; this.eventKey = eventKey; this.eventState = { status: 'loading', data: [] };
      if (eventKey) this.stopEvents = watchRaceControl(this.hass, eventKey, state => { this.eventState = state; this.revision++; });
    }
  }
  updated() {
    this.syncUserStyles();
    clearTimeout(this.mapAgeTimer);
    const expiry = !this.previewData && !this.frozen && this.mapKey ? mapExpiry(this.mapState.data?.snapshot) : null;
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
    const state = data.selectionState(this.hass, this.entry, selection);
    if (state.archive && module.type !== 'archive') return { ...state, available: false, reason: 'archive_module_required' };
    return state;
  }
  cancelActions() { clearTimeout(this.holdTimer); clearTimeout(this.tapTimer); this.held = false; }
  _handleCardAction(action = 'tap') {
    if (this.preview || this.previewData || !this.isConnected) return false;
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
    return hasF1Action(this, 'tap') ? html`<button data-f1-card-action aria-label=${`${this.config.title} · ${this.w('card action', 'kortåtgärd')}`}
      @pointerdown=${this.actionDown} @pointerup=${this.actionRelease} @pointerleave=${this.actionRelease} @pointercancel=${this.cancelActions}
      @click=${this.actionClick} @dblclick=${this.actionDouble}>${title}</button>` : title;
  }
  actionAlternatives() {
    const actions = [...(this.config.appearance.show_header ? [] : [['tap', this.w('Tap action', 'Åtgärd vid tryck')]]), ['hold', this.w('Hold action', 'Åtgärd vid långtryck')], ['double_tap', this.w('Double tap action', 'Åtgärd vid dubbeltryck')]].filter(([key]) => hasF1Action(this, key));
    return actions.length ? html`<details class="action-alternatives" part="action-alternatives"><summary>${this.w('Card actions', 'Kortåtgärder')}</summary><div class="tools" part="action-toolbar">${actions.map(([key, text]) => html`<button @click=${() => this._handleCardAction(key)}>${text}</button>`)}</div></details>` : '';
  }
  chooseDriver(event) {
    this.frozen = false;
    this.focus = { ...this.focus, driver: event.target.value };
    if (this.config.context.share.includes('focus')) this.group?.publish({ driver: event.target.value });
    this.revision++;
  }
  chooseGroupSelection(event) {
    if (!this.group || !this.config.context.share.includes('selection')) return;
    let selection;
    try { selection = JSON.parse(event.target.value); } catch { return; }
    this.group.publish({ selection }); this.frozen = false; this.revision++;
  }
  freeze() {
    if (!this.frozen) {
      this.savedSources.update(this.hass, this.entry, this.config, Boolean(this.previewData));
      this.frozenModels = this.buildModels(); this.frozenAt = this.previewData?.now ?? Date.now();
      this.frozenFocus = { ...this.focus };
      this.frozenGeneration = this.savedSources.viewGeneration;
      const roster = data.source(this.hass, this.entry, 'driver_list');
      this.frozenRoster = structuredClone(roster.status === 'available' ? roster : this.retainedRoster ?? roster);
    }
    this.frozen = !this.frozen;
  }
  async viewingAction(event) {
    event.stopPropagation();
    const detail = event.detail, entry = this.entry, hass = this.hass;
    if (!detail || !entry || !this.config.context.viewing_controls || this.preview || this.previewData || this.frozen || !this.isConnected || detail.connection !== hass?.connection || this.viewingRequest?.pending) return;
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
    if (this.preview || this.previewData || this.frozen || !this.isConnected || !entry || typeof this.hass?.callService !== 'function' || this.replayRequests.get(entry.entry_id)?.pending) return;
    const module = this.config.modules.find(item => item.id === detail.module);
    const command = data.replayCommand(this.hass, entry, module, detail.action, detail.value, detail.context);
    if (!command) return;
    const request = { pending: true, error: false, busy: false };
    this.replayRequests.set(entry.entry_id, request); this.revision++;
    try { request.busy = !await callEntityService(this.hass, command, `replay:${entry.entry_id}`); }
    catch { request.error = true; }
    finally {
      if (this.isConnected && this.replayRequests.get(entry.entry_id) === request) { request.pending = false; this.revision++; }
    }
  }
  async raceControlAction(event) {
    event.stopPropagation();
    const detail = event.detail, entry = this.entry, hass = this.hass;
    if (!detail || typeof detail.module !== 'string' || detail.action !== 'clear' || this.preview || this.previewData || this.frozen || !this.isConnected || !entry || typeof hass?.callService !== 'function' || data.spoilerState(hass, entry, this.config.context.spoilers) !== 'clear' || this.raceControlRequest?.pending) return;
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
    if (!detail || this.preview || this.previewData || this.frozen || !this.isConnected || !entry || data.spoilerState(this.hass, entry, this.config.context.spoilers) !== 'clear') return;
    const saved = this.config.modules.find(module => module.id === detail.module && module.type === 'telemetry' && module.enabled);
    if (!saved) return;
    const module = { ...saved, options: { ...saved.options, ...this.choices.get(saved.id) } }, replay = data.replayModel(this.hass, entry);
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
    return status === 'disabled' ? this.w('Enable this entity in F1 Sensor to see its data.', 'Aktivera den här entiteten i F1 Sensor för att se dess data.')
      : status === 'missing' ? this.w('This data source is not available in this installation.', 'Den här datakällan finns inte tillgänglig i installationen.')
        : this.w('No session data is currently available. Your settings are kept.', 'Sessionsdata är inte tillgängliga just nu. Dina inställningar finns kvar.');
  }
  clockDescription(clock) {
    if (clock.notApplicable) return this.w('Available for race sessions.', 'Tillgänglig under racesessioner.');
    if (clock.value === null) return clock.contextMismatch ? this.w('Clock belongs to another session or qualifying part.', 'Klockan hör till en annan session eller kvaldel.') : clock.phase === 'idle' ? this.w('Session clock has not started.', 'Sessionsklockan har inte startat.') : this.missingMessage(clock.source.status);
    if (clock.cap) return [this.w('From race start · includes session interruptions', 'Från racestart · inkluderar sessionsavbrott'), ['paused', 'seeking'].includes(clock.replay) ? this.w('Replay paused', 'Replay pausad') : null].filter(Boolean).join(' · ');
    const phases = { running: ['Running', 'Pågår'], paused: ['Paused', 'Pausad'], finished: ['Finished', 'Avslutad'], overtime: ['Time expired', 'Tiden har löpt ut'] };
    const qualities = { official: ['Official clock', 'Officiell klocka'], official_no_heartbeat: ['Clock without heartbeat confirmation', 'Klocka utan bekräftande heartbeat'], sessiondata_fallback: ['Estimated from session events', 'Beräknad från sessionshändelser'] };
    return [phases[clock.phase] ? this.w(...phases[clock.phase]) : this.w('Clock status unknown', 'Klockstatus okänd'), qualities[clock.quality] ? this.w(...qualities[clock.quality]) : this.w('Clock source uncertain', 'Klockans källa är osäker'), clock.part ? `${this.w('Part', 'Del')} ${clock.part}` : null].filter(Boolean).join(' · ');
  }
  buildModels() {
    const entry = this.entry, settings = this.settings, session = data.sessionContext(this.hass, entry);
    const protection = data.spoilerState(this.hass, entry, this.config.context.spoilers);
    const hiddenMessage = protection === 'protected' ? this.w('Spoiler protection is active.', 'Spoilerskyddet är aktivt.') : this.w('Spoiler status cannot be verified. Refresh F1 Sensor before showing sensitive data.', 'Spoilerskyddets status kan inte kontrolleras. Uppdatera F1 Sensor innan känsliga uppgifter visas.');
    const models = new Map(); this.retainedRoster = null;
    for (const module of this.config.modules) {
      const definition = MODULES[module.type];
      const focus = module.focus_mode === 'independent' ? {} : this.focus;
      const model = { title: moduleTitle(module, this.language) };
      const selection = resolveSelection(this.config.context, module, this.groupContext), sessionState = this.moduleSessionState(module);
      const effective = data.resolveWeatherModule(this.hass, entry, { ...module, selection, options: { ...module.options, ...this.choices.get(module.id) } });
      const sensitive = definition?.spoiler || ['timing', 'race_control'].includes(module.type) || module.type === 'weather' && effective.options.content === 'track_conditions';
      if (sensitive && protection !== 'clear') {
        const placeholder = protection === 'protected' && typeof module.options?.spoiler_placeholder === 'string' ? module.options.spoiler_placeholder.trim() : '';
        model.blocked = placeholder || hiddenMessage; models.set(module.id, model); continue;
      }
      if (!module.when.includes(sessionState.phase)) { model.hidden = true; models.set(module.id, model); continue; }
      if (!sessionState.available) {
        model.blocked = sessionState.reason === 'archive_module_required'
          ? this.w('This module cannot read an archived session. Use an Archive module for this pinned selection.', 'Den här modulen kan inte läsa en arkiverad session. Använd en arkivmodul för det låsta urvalet.')
          : this.w('The pinned session is not available from the selected source. The saved identity has been kept.', 'Den låsta sessionen är inte tillgänglig från den valda källan. Den sparade identiteten har behållits.');
        model.hidden = module.unavailable === 'hide'; models.set(module.id, model); continue;
      }
      if (module.type === 'weather' && effective.options.content === 'track_conditions' && !this.previewData && this.savedSources.weatherAwaitingObservation(this.hass, entry)) {
        model.blocked = this.w('Waiting for a new track weather update after the session or playback context changed.', 'Inväntar en ny uppdatering av banvädret efter ändrad session eller uppspelning.');
        model.hidden = module.unavailable === 'hide'; models.set(module.id, model); continue;
      }
      const saved = this.savedSources.select(this.hass, entry, effective, definition, Boolean(this.previewData));
      const viewHass = saved.hass, moduleSession = data.sessionContext(viewHass, entry);
      if (module.type === 'results') {
        Object.assign(model, season.resultsModel(viewHass, entry, effective, focus));
        if (effective.options.show_session_type_badge !== false && model.context?.session) model.badge = model.context.session;
      }
      if (module.type === 'standings') {
        Object.assign(model, season.standingsModel(viewHass, entry, effective, focus));
        if (effective.options.show_mode_badge !== false) model.badge = this.w('Published standings', 'Publicerad ställning');
        if (model.projection.requested) {
          if (model.projection.available) model.notice = this.w('Projected columns follow the current session. Published positions and points stay separate.', 'Prognoskolumner följer aktuell session. Publicerade placeringar och poäng visas separat.');
          else {
            const auth = data.source(viewHass, entry, 'f1tv_token_status');
            const authNeedsAttention = auth.status === 'available' && ['expired', 'invalid', 'rejected', 'refresh_failed'].includes(String(auth.state).toLowerCase());
            if (authNeedsAttention) model.notice = this.w('F1TV access needs attention, so live championship projections are hidden. Published standings remain available.', 'F1TV-åtkomsten behöver åtgärdas, så liveprognoser för mästerskapet är dolda. Publicerad ställning finns fortfarande tillgänglig.');
            else if (effective.options.show_availability_notice !== false) model.notice = this.w('Projection unavailable. Live projections need F1TV access and a supported race feed; archived replay can also supply them.', 'Prognos saknas. Liveprognoser behöver F1TV-åtkomst och en racekälla med stöd; arkiverad replay kan också ge dessa data.');
          }
        }
      }
      if (module.type === 'archive') {
        Object.assign(model, season.archiveModel(effective, entry?.entry_id, query => this.previewData ? this.previewData.history?.(query) ?? { status: 'ready', data: { payload: null } } : this.history.read(query), this.previewData?.now ?? Date.now()));
        const archiveLabel = this.w('Historical data', 'Historiska data');
        model.badge = effective.options.show_session_type_badge !== false && model.session?.name ? `${archiveLabel} · ${model.session.name}` : archiveLabel;
        model.notice = effective.options.content === 'lap_position'
          ? this.w('Positions are recorded when each driver completes a lap. They are not simultaneous track positions and do not identify overtakes.', 'Placering registreras när varje förare avslutar ett varv. Uppgifterna visar inte samtidiga banpositioner eller identifierade omkörningar.')
          : effective.options.content === 'lap_time' ? this.w('Published race laps may include pit laps and neutralisations. Sector times, telemetry and clean-lap flags are unavailable in this archive.', 'Publicerade racevarv kan omfatta depåvarv och neutraliseringar. Sektortider, telemetri och markeringar för rena varv saknas i arkivet.') : null;
      }
      if (module.type === 'progression') Object.assign(model, season.progressionModel(viewHass, entry, effective, focus));
      if (module.type === 'replay') {
        Object.assign(model, data.replayModel(viewHass, entry));
        model.request = this.replayRequests.get(entry?.entry_id);
      }
      if (module.type === 'telemetry') {
        const demo = this.previewData;
        const selected = demo ? { ...effective, options: { ...effective.options, selected: ['4:2', '16:2'], session_id: 'demo-replay' } } : effective;
        const read = query => demo ? demo.telemetry?.(query) ?? { status: 'ready', data: null } : this.telemetry.read(query);
        const requested = demo ? telemetryData.telemetryPlan(selected, entry, data.replayModel(viewHass, entry), read).compareQuery : this.telemetryRequests.get(module.id);
        Object.assign(model, telemetryData.telemetryModel(viewHass, entry, selected, read, requested));
        model.badge = this.w('Recorded replay', 'Inspelad replay');
        model.readonly = Boolean(this.preview || demo || this.frozen);
      }
      if (module.type === 'lap_chart') {
        Object.assign(model, data.lapChartModel(viewHass, entry, effective, focus));
        model.title = module.options.metric === 'lap_change' ? this.w('Lap changes', 'Varvförändringar') : this.w('Recorded lap times', 'Registrerade varvtider');
        if (model.invalidRange) model.blocked = this.w('The first lap is after the last lap. Adjust the lap range in the editor.', 'Första varvet är efter det sista. Ändra varvintervallet i editorn.');
        model.notice = module.options.metric === 'lap_change'
          ? this.w('Each change compares the same driver with their preceding lap. Negative values mean a faster lap. A missing preceding lap leaves a gap.', 'Varje förändring jämför samma förare med föregående varv. Negativa värden betyder ett snabbare varv. Ett saknat föregående varv lämnar ett glapp.')
          : this.w('Recorded laps may include pit laps, neutralisations and different qualifying parts. This view does not assume a complete session history.', 'Registrerade varv kan omfatta depåvarv, neutraliseringar och olika kvaldelar. Vyn förutsätter inte en fullständig sessionshistorik.');
      }
      if (module.type === 'documents') Object.assign(model, season.documentsModel(viewHass, entry, effective));
      if (module.type === 'map') {
        Object.assign(model, mapModel(this.previewData?.map ?? this.mapState.data?.snapshot, effective, focus, this.previewData?.now ?? Date.now()));
        const laps = data.source(viewHass, entry, 'race_lap_count'), trackStatus = data.source(viewHass, entry, 'track_status');
        const currentLap = Number(laps.state), totalLaps = Number(laps.attributes.total_laps);
        model.lap = laps.status === 'available' && Number.isInteger(currentLap) && currentLap >= 0 ? currentLap : null;
        model.totalLaps = Number.isInteger(totalLaps) && totalLaps > 0 ? totalLaps : null;
        model.trackStatus = trackStatus.status === 'available' ? trackStatus.state : null;
        if (model.pending) model.blocked = this.mapState.status === 'error' ? this.w('Map data is unavailable. Check the selected F1 Sensor installation.', 'Kartdata saknas. Kontrollera vald F1 Sensor-installation.') : this.w('Waiting for map data…', 'Inväntar kartdata…');
        if (!this.previewData && ['error', 'disconnected', 'refreshing'].includes(this.mapState.status) && !model.pending) {
          if (module.unavailable === 'retain') { model.freshness.stale = true; model.rows = model.rows.map(row => ({ ...row, stale: true })); }
          else model.blocked = this.w('Map connection interrupted. Your settings are kept.', 'Kartans anslutning är avbruten. Dina inställningar finns kvar.');
        }
        if (model.blocked && module.unavailable === 'hide' && !this.previewData) model.hidden = true;
      }
      if (definition?.stream === 'analysis') {
        const adapter = module.type === 'strategy' ? analysisData.strategyModel : module.type === 'battles' ? analysisData.battlesModel : analysisData.timelineModel;
        Object.assign(model, adapter(this.previewData?.analysis ?? this.analysisState.data, effective, focus));
        if (model.pending) model.blocked = this.analysisState.status === 'error'
          ? this.w('Session analysis is unavailable. Check that this F1 Sensor installation has its analysis features loaded.', 'Sessionsanalys saknas. Kontrollera att denna F1 Sensor-installation har laddat analysfunktionerna.')
          : this.w('Waiting for session analysis…', 'Inväntar sessionsanalys…');
        if (model.context) { model.context.updated = this.previewData ? new Date(this.previewData.now).toISOString() : this.analysisState.received_at; model.context.updatedKind = 'received'; }
        if (!this.previewData && ['disconnected', 'error', 'refreshing'].includes(this.analysisState.status) && !model.pending) {
          if (module.unavailable === 'retain') model.notice = this.w('Saved analysis · connection interrupted. Events may be incomplete.', 'Sparad analys · anslutningen avbruten. Händelser kan saknas.');
          else model.blocked = this.w('Analysis connection interrupted. Your settings are kept.', 'Analysanslutningen är avbruten. Dina inställningar finns kvar.');
        }
        if (model.blocked && module.unavailable === 'hide' && !this.previewData) model.hidden = true;
        if (module.fields.includes('analysis_quality')) model.notice = [model.notice, this.w('Evidence score measures support, not probability.', 'Underlagspoäng mäter stöd, inte sannolikhet.')].filter(Boolean).join(' ');
      }
      if (module.type === 'battles' && !model.pending) {
        model.badge = this.w('Local estimate', 'Lokal uppskattning');
        model.emptyMessage = model.capability === 'waiting_for_positions' ? this.w('Waiting for usable position observations.', 'Inväntar användbara positionsobservationer.') : this.w('No matching observations for this session.', 'Inga matchande observationer för sessionen.');
        model.explanation = [model.explanation, this.w('These observations come from timing analysis. A position exchange does not always mean an on-track overtake. History follows the recorded order; event timestamps are not supplied.', 'Observationerna bygger på timinganalys. Ett positionsbyte innebär inte alltid en omkörning på banan. Historiken följer registreringsordningen; händelsetider saknas i underlaget.')].filter(Boolean).join(' ');
        if (model.active && model.threshold !== null) model.explanation += this.w(` The analysis uses a ${model.threshold} s gap threshold and repeated observations.`, ` Analysen använder gränsen ${model.threshold} s och upprepade observationer.`);
      }
      if (module.type === 'strategy' && !model.pending) {
        model.badge = this.w('Local estimate', 'Lokal uppskattning');
        if (model.qualityFiltered) model.emptyMessage = this.w('No estimates meet the selected evidence and sample requirements.', 'Inga uppskattningar uppfyller valda krav på underlag och antal varv.');
        if (model.comparison === 'teammates') model.explanation = [model.explanation, this.w('Teammate medians can cover different laps, tyre compounds, fuel loads and traffic.', 'Teamkamraternas medianer kan avse olika varv, däckblandningar, bränslemängd och trafik.')].filter(Boolean).join(' ');
        if (model.comparison === 'crossover') model.explanation = [model.explanation, this.w('The crossover is an estimate within the observed tyre-age range across all drivers. It is not a recommended pit-stop lap.', 'Skärningen är en uppskattning inom observerat däckåldersintervall för alla förare. Den är inte ett rekommenderat depåvarv.')].filter(Boolean).join(' ');
        if (model.comparison === 'pit_outcomes') model.explanation = [model.explanation, this.w('Pit-cycle outcomes compare teammate positions before and after nearby stops. The observed order does not prove that strategy caused the change.', 'Depåutfallen jämför teamkamraters placering före och efter närliggande stopp. Ordningen bevisar inte att strategin orsakade förändringen.')].filter(Boolean).join(' ');
        if (model.capability === 'waiting_for_clean_laps') model.emptyMessage = this.w('Waiting for usable clean laps. Pace estimates will appear when enough recorded lap data is available.', 'Inväntar användbara rena varv. Tempouppskattningar visas när det finns tillräckligt med registrerad varvdata.');
        model.explanation = [model.explanation, this.w('Pace and degradation use recorded clean laps. They are local estimates, not official strategy or a fuel-corrected prediction.', 'Tempo och försämring bygger på registrerade rena varv. Det är lokala uppskattningar, inte officiell strategi eller en bränslekorrigerad prognos.')].filter(Boolean).join(' ');
        if (module.fields.includes('strategy_pit_loss')) model.explanation += this.w(' Stint-change loss compares the first lap of a stint with the preceding stint’s clean pace.', ' Förlust vid stintbyte jämför stintens första varv med föregående stints rena tempo.');
      }
      if (module.type === 'tyres') {
        Object.assign(model, sessionData.tyresModel(viewHass, entry, effective, focus));
        if (model.waiting) model.notice = this.w('Waiting for compound information from TimingAppData. Lap counts alone do not identify a tyre.', 'Inväntar däckblandning från TimingAppData. Antalet varv identifierar inte ett däck.');
        if (model.statistics && !model.waiting) model.notice = this.w('Recorded laps across all drivers and stints. Differences include fuel, track conditions and traffic; this is not a controlled tyre comparison.', 'Registrerade varv från alla förare och stintar. Skillnader påverkas av bränsle, banförhållanden och trafik; jämförelsen är inte ett kontrollerat däcktest.');
      }
      if (module.type === 'pit_stops') {
        Object.assign(model, sessionData.pitStopsModel(viewHass, entry, effective, focus));
        if (model.source.status !== 'available') {
          const auth = data.source(viewHass, entry, 'f1tv_token_status');
          const authNeedsAttention = auth.status === 'available' && ['expired', 'invalid', 'rejected', 'refresh_failed'].includes(String(auth.state).toLowerCase());
          if (authNeedsAttention) model.capabilityMessage = this.w('F1TV access needs attention, so live pit stop data is hidden. Replay data remains available.', 'F1TV-åtkomsten behöver åtgärdas, så liveuppgifter om depåstopp är dolda. Replaydata finns fortfarande tillgängliga.');
          else if (module.options.show_availability_notice !== false) model.capabilityMessage = this.w('Pit stop timing needs F1TV access and a supported feed, or an archived replay containing PitStopSeries.', 'Tider för depåstopp kräver F1TV-åtkomst och en källa med stöd, eller arkiverad replay med PitStopSeries.');
        }
        if (module.fields.includes('pit_delta')) model.notice = this.w('Estimated lap loss: the longer of the in/out laps minus the median reference lap. It can include traffic and other delays. It is separate from stationary time and pit lane time.', 'Beräknad varvförlust: det längre av in-/utvarven minus medianen för referensvarven. Trafik och andra fördröjningar kan ingå. Värdet är separat från stillastående tid och tid i depåområdet.');
      }
      if (module.type === 'incidents') {
        Object.assign(model, sessionData.incidentsModel(viewHass, entry, effective, focus));
        if (model.summary) model.notice = this.w('Only drivers with recorded track-limit data are listed. A missing driver is not evidence of zero violations.', 'Endast förare med registrerade track limits-uppgifter visas. En saknad förare innebär inte att antalet överträdelser är noll.');
      }
      if (module.type === 'timing') {
        Object.assign(model, data.timingRows(viewHass, entry, moduleSession, this.sectors, module, focus));
        model.context = { meeting: moduleSession.meeting, session: moduleSession.name, key: moduleSession.key, source: 'TimingData', updated: model.source.updated_at, updatedKind: 'ha_state' };
        if (model.currentPart && ['qualifying', 'sprint_qualifying'].includes(model.sessionKind)) model.badge = `${model.sessionKind === 'sprint_qualifying' ? 'SQ' : 'Q'}${model.currentPart}`;
        if (model.fields.some(id => /^q[123]_/.test(id)) && !['qualifying', 'sprint_qualifying'].includes(model.sessionKind)) model.notice = this.w('Q/SQ columns are available during qualifying sessions. Other columns continue to show their own data.', 'Q/SQ-kolumner finns under kvalsessioner. Övriga kolumner visar fortsatt sina egna data.');
      }
      if (module.type === 'calendar') {
        Object.assign(model, data.scheduleRows(viewHass, entry, module, this.previewData?.now ?? Date.now()));
        model.rows = model.rows.map(row => {
          const zone = module.options.timezone === 'utc' ? 'UTC' : module.options.timezone === 'circuit' ? row.timezone : settings.timezone;
          const displayZone = zone ?? settings.timezone;
          return { ...row, display_timezone: displayZone, timezone_label: displayZone ?? this.w('Circuit zone unavailable · home time', 'Banans tidszon saknas · hemmatid'),
            track_timezone: module.options.show_track_time && row.timezone && row.timezone !== displayZone ? row.timezone : null };
        });
      }
      if (module.type === 'weather') {
        const weather = data.weatherValues(viewHass, entry, effective); Object.assign(model, weather);
        if (weather.track) {
          model.badge = weather.replay ? this.w('Recorded replay', 'Inspelad replay') : this.w('Track observations', 'Banobservationer');
          model.explanation = this.w('The measurement time is not exposed by this source. The Home Assistant update time does not establish the age of the observation. The rain indicator reports detection of rain; it does not measure water on the track.', 'Källan visar inte mättidpunkten. Uppdateringstiden i Home Assistant anger inte observationens ålder. Regnindikatorn visar om regn registrerats; den mäter inte vatten på banan.');
        } else {
          if (weather.forecast) model.badge = this.w('Forecast', 'Prognos');
          model.explanation = this.w('Current circuit weather and the forecast nearest race start. An observation time and precipitation interval are not supplied here.', 'Aktuellt banväder och prognosen närmast racestart. Observationstid och nederbördsintervall anges inte här.');
        }
        if (weather.automatic) {
          if (!weather.track) model.badge = this.w('Current weather', 'Aktuellt väder');
          const selectionExplanation = weather.track ? this.w('Automatic source: track observations. Missing measurements are not replaced with forecast values.', 'Automatisk källa: banobservationer. Saknade mätvärden ersätts inte med prognosvärden.') : this.w('Automatic source: current weather. Track observations require a confirmed active session and usable measurements.', 'Automatisk källa: aktuellt väder. Banobservationer kräver bekräftad aktiv session och användbara mätvärden.');
          model.explanation = [model.explanation, selectionExplanation].filter(Boolean).join(' ');
        }
        model.explanationTitle = this.w('About the weather data', 'Om väderuppgifterna');
        model.items = module.fields.filter(id => weather.values[id]).map(id => { const item = weather.values[id]; return { id, ...item,
          detail: weather.mixed ? item.estimated ? this.w('Forecast near race start', 'Prognos nära racestart') : this.w('Current circuit weather', 'Aktuellt väder vid banan') : null }; });
        if (model.source.status !== 'available') model.capabilityMessage = weather.track ? this.w('Track weather observations are not available for this session.', 'Väderobservationer från banan saknas för den här sessionen.') : this.w('Circuit weather is currently unavailable.', 'Väderuppgifter för banan är inte tillgängliga just nu.');
      }
      if (module.type === 'overview') {
        const next = data.source(viewHass, entry, 'next_race'), track = data.source(viewHass, entry, 'track_status'), laps = data.source(viewHass, entry, 'race_lap_count');
        const attrs = next.attributes, start = Date.parse(attrs.race_start_utc ?? attrs.race_start), remaining = start - (this.previewData?.now ?? Date.now());
        const countdown = !Number.isFinite(remaining) ? '—' : remaining <= 0 ? this.w('Scheduled start passed', 'Schemalagd start passerad') : `${Math.floor(remaining / 86400000)} ${this.w('days', 'dagar')} ${Math.floor(remaining % 86400000 / 3600000)} ${this.w('hours', 'timmar')}`;
        const clocks = Object.fromEntries(['session_time_elapsed', 'session_time_remaining', 'race_time_to_three_hour_limit'].map(key => [key, data.sessionClock(viewHass, entry, key, session)]));
        const currentLap = Number(laps.state), totalLaps = Number(laps.attributes.total_laps);
        const lapProgress = laps.status === 'available' && Number.isInteger(currentLap) && currentLap >= 0 ? `${currentLap}${Number.isInteger(totalLaps) && totalLaps > 0 ? ` / ${totalLaps}` : ''}` : null;
        const values = { ...Object.fromEntries(Object.entries(clocks).map(([key, clock]) => [key, protection === 'clear' ? clock.value : hiddenMessage])), meeting: attrs.race_name, circuit: attrs.circuit_name, country: attrs.circuit_country, countdown,
          circuit_map: { url: safeImageUrl(attrs.circuit_map_url), circuit: attrs.circuit_name, locality: attrs.circuit_locality, country: attrs.circuit_country, season: attrs.season },
          circuit_history: { defending_winner: attrs.defending_winner, defending_pole_sitter: attrs.defending_pole_sitter, races_held_here: attrs.races_held_here, first_f1_race_here: attrs.first_f1_race_here, last_year_podium: attrs.last_year_podium, last_5_winners: attrs.last_5_winners, top_5_driver_wins_here: attrs.top_5_driver_wins_here, top_5_constructor_wins_here: attrs.top_5_constructor_wins_here, dnf_rate_last_5: attrs.dnf_rate_last_5, pole_to_win_conversion_last_5: attrs.pole_to_win_conversion_last_5 },
          session: session.name ?? this.w('Between sessions', 'Mellan sessioner'), session_status: ['unavailable', 'unknown'].includes(session.status) ? null : session.status, lap_progress: protection === 'clear' ? lapProgress : hiddenMessage, track_status: protection === 'clear' ? track.status === 'available' ? track.state : null : hiddenMessage };
        model.items = module.fields.filter(id => Object.hasOwn(values, id)).map(id => ({ id, value: values[id], flag: id === 'meeting' ? safeImageUrl(attrs.country_flag_url) : null, country: attrs.circuit_country,
          detail: clocks[id] ? protection === 'clear' ? this.clockDescription(clocks[id]) : null : id === 'track_status' && protection === 'clear' && track.status !== 'available' ? this.missingMessage(track.status) : null }));
      }
      if (module.type === 'race_control') {
        const current = data.source(viewHass, entry, 'race_control'); model.source = current;
        const currentMessage = module.options.presentation === 'latest_message' && current.attributes.message ? [current.attributes] : [];
        let rows = data.mergeEvents(this.previewData?.events ?? this.eventState.data, currentMessage);
        model.rows = data.filterRaceControl(rows, viewHass, entry, module, focus);
        model.raceControlContext = JSON.stringify([entry.entry_id, current.entity_id ?? '', current.attributes.session_id ?? current.attributes.session_name ?? '']);
        if (!this.previewData && ['disconnected', 'error', 'refreshing'].includes(this.eventState.status)) model.notice = this.w('Connection interrupted · saved messages may be incomplete.', 'Anslutningen är avbruten · sparade meddelanden kan vara ofullständiga.');
      }
      if (model.source && ['missing', 'disabled', 'unavailable', 'unknown'].includes(model.source.status)) {
        if (['missing', 'disabled'].includes(model.source.status) || module.unavailable !== 'retain' || (!model.rows?.length && !model.items?.length && !model.series?.length)) model.blocked = model.source.status === 'disabled' ? this.missingMessage('disabled') : model.capabilityMessage ?? this.missingMessage(model.source.status);
        else model.notice = this.w('Saved data · source currently unavailable.', 'Sparad data · källan är inte tillgänglig just nu.');
        if (module.unavailable === 'hide' && !this.previewData) model.hidden = true;
      }
      if (saved.retained) {
        model.retained = true;
        this.retainedRoster ??= data.source(viewHass, entry, 'driver_list');
        model.notice = [...new Set([model.notice, this.w('Saved data · source currently unavailable.', 'Sparad data · källan är inte tillgänglig just nu.')].filter(Boolean))].join(' ');
      }
      model.timeInfo = data.modelTimestamp(model, this.previewData?.now ?? Date.now());
      // A connected HA socket does not prove upstream freshness. An explicitly
      // disconnected socket does prove that live updates cannot reach this card.
      if (!this.previewData && this.hass.connection?.connected === false && !['archive', 'replay', 'telemetry'].includes(module.type)) {
        if (module.unavailable !== 'retain') model.blocked = this.w('Home Assistant is disconnected. Data returns after reconnection; your settings are kept.', 'Home Assistant är frånkopplad. Data återkommer efter anslutning; dina inställningar finns kvar.');
        if (module.unavailable === 'hide') model.hidden = true;
      }
      models.set(module.id, model);
    }
    return models;
  }
  render() {
    if (!this.config || !this.hass) return html``;
    const settings = this.settings, dark = settings.mode === 'dark', high = settings.accessibility.high_contrast;
    const haStyle = settings.appearance.style === 'ha' && settings.appearance.mode === 'auto' && !high;
    const background = haStyle ? 'var(--ha-card-background,var(--card-background-color))' : high ? dark ? '#000000' : '#ffffff' : dark ? '#141920' : '#ffffff';
    const text = haStyle ? 'var(--primary-text-color)' : dark ? '#f1f4f8' : '#1a2533';
    const muted = haStyle ? 'var(--secondary-text-color)' : high ? text : dark ? '#bdc6d4' : '#536174';
    const density = settings.appearance.density;
    const spacing = density === 'compact' ? [16, 10, 16, 14, '5px 9px', '5px'] : density === 'spacious' ? [24, 16, 32, 24, '15px 16px', '14px'] : [20, 12, 26, 20, '10px 12px', '9px'];
    const typography = settings.appearance.font === 'f1';
    const accent = cardAccent(settings.appearance, this.previewData?.accentTeams ?? data.accentTeams(this.hass, this.entry), settings.mode);
    const radius = settings.appearance.surface === 'framed' ? '8px' : settings.appearance.surface === 'soft' ? '20px' : settings.appearance.surface === 'flat' ? '0' : 'var(--ha-card-border-radius,14px)';
    const style = `--_f1-card-padding:${spacing[0]}px;--_f1-minimal-padding:${spacing[1]}px;--_f1-module-gap:${spacing[2]}px;--_f1-section-space:${spacing[3]}px;--_f1-cell-padding:${spacing[4]};--_f1-item-padding:${spacing[5]};--_f1-heading-font:${typography ? "'F1 Barlow Condensed',sans-serif" : 'var(--ha-font-family-heading,var(--ha-font-family-body,inherit))'};--_f1-heading-transform:${typography ? 'uppercase' : 'none'};--_f1-module-heading-size:${typography ? '1.3em' : '1.1em'};--_f1-surface:${background};--_f1-text:${text};--_f1-muted:${muted};--_f1-border:${dark ? '#637083' : '#778397'};--_f1-divider:${dark ? '#354150' : '#cbd1da'};--_f1-panel:${dark ? '#1b2430' : '#f1f4f8'};--_f1-focus:${dark ? '#7ebfff' : '#005db5'};--_f1-row-alternate:${settings.appearance.surface === 'soft' ? 'var(--f1-panel)' : 'transparent'};--_f1-accent:${accent.color};--_f1-numerals:${settings.appearance.numbers === 'tabular' ? 'tabular-nums' : 'normal'};--_f1-card-radius:${radius}`;
    if (!this.entry) return html`<ha-card part="card" data-style=${settings.appearance.style} data-font=${settings.appearance.font} data-surface=${settings.appearance.surface} data-accent=${String(accent.visible)} role="group" aria-label=${this.config.title} style=${style}>${settings.appearance.show_header ? html`<header class="heading" part="header">${this.actionHeading()}</header>` : ''}<div class="empty" part="empty-state">${this.discovery?.status === 'error' ? this.discovery.error : (this.previewData?.entries ?? this.entries).length > 1 ? this.w('Choose an F1 Sensor installation in the editor.', 'Välj en F1 Sensor-installation i editorn.') : this.w('Waiting for F1 Sensor…', 'Väntar på F1 Sensor…')}</div>${this.actionAlternatives()}</ha-card>`;
    const models = this.frozen ? this.frozenModels : this.buildModels();
    const protection = data.spoilerState(this.hass, this.entry, this.config.context.spoilers);
    const modules = this.config.modules.filter(module => module.enabled && !models.get(module.id)?.hidden);
    const active = modules.some(module => module.id === this.tab) ? this.tab : modules[0]?.id;
    const hasDriverFocus = modules.some(module => moduleFocusKinds(module).includes('driver'));
    const currentRoster = this.frozen ? this.frozenRoster : data.source(this.hass, this.entry, 'driver_list');
    const roster = currentRoster.status === 'available' ? currentRoster : this.retainedRoster ?? currentRoster;
    const drivers = hasDriverFocus && roster.status === 'available' ? data.array(roster.attributes.drivers).filter(item => item && typeof item === 'object') : [];
    const focusedDriver = (this.frozen ? this.frozenFocus : this.focus)?.driver ?? '';
    const groupSelections = [[{ mode: 'follow', source: 'auto' }, this.w('Group: automatic session', 'Grupp: automatisk session')], [{ mode: 'follow', source: 'live' }, this.w('Group: live session', 'Grupp: livesession')], [{ mode: 'follow', source: 'replay' }, this.w('Group: loaded replay', 'Grupp: laddad replay')]];
    if (this.config.context.selection.mode === 'pinned') groupSelections.push([this.config.context.selection, this.w('Group: this pinned session', 'Grupp: denna låsta session')]);
    const selectedGroup = this.groupContext.selection ?? (this.config.context.selection.mode === 'follow' ? this.config.context.selection : { mode: 'follow', source: 'auto' });
    if (!groupSelections.some(([selection]) => JSON.stringify(selection) === JSON.stringify(selectedGroup))) groupSelections.push([selectedGroup, this.w('Group: shared pinned session', 'Grupp: delad låst session')]);
    const groupSelection = JSON.stringify(selectedGroup);
    const nodes = modules.map(module => {
      let node = this.moduleNodes.get(module.id);
      if (!node) {
        node = document.createElement('f1-module-view');
        node.addEventListener('f1-replay-action', event => this.replayAction(event));
        node.addEventListener('f1-race-control-action', event => this.raceControlAction(event));
        for (const type of ['selection', 'compare', 'retry']) node.addEventListener(`f1-telemetry-${type}`, event => this.telemetryAction(event));
        node.addEventListener('f1-module-choice', event => {
          event.stopPropagation();
          if (!this.config.modules.some(item => item.id === event.detail.module)) return;
          const saved = this.config.modules.find(item => item.id === event.detail.module);
          if (saved.type === 'archive' && event.detail.key === 'retry') {
            if (!this.previewData && !this.preview && data.spoilerState(this.hass, this.entry, this.config.context.spoilers) === 'clear') this.history.retry(season.archivePlan({ ...saved, options: { ...saved.options, ...this.choices.get(saved.id) } }, this.entry.entry_id, query => this.history.read(query)).requests);
            return;
          }
          const reset = saved.type !== 'archive' ? {} : event.detail.key === 'year' ? { round: '', session_key: '', selected: [] } : event.detail.key === 'round' ? { session_key: '', selected: [] } : event.detail.key === 'session_key' ? { selected: [] } : {};
          this.choices.set(event.detail.module, { ...this.choices.get(event.detail.module), ...reset, [event.detail.key]: event.detail.value });
          this.frozen = false; this.revision++;
        });
        this.moduleNodes.set(module.id, node);
      }
      node.module = models.get(module.id)?.fields ? { ...module, fields: models.get(module.id).fields } : module; node.model = ['replay', 'telemetry', 'race_control'].includes(module.type) ? { ...models.get(module.id), readonly: Boolean(this.preview || this.previewData || this.frozen), frozen: this.frozen, ...(module.type === 'race_control' ? { request: this.raceControlRequest } : {}) } : models.get(module.id); node.settings = settings;
      node.hidden = this.config.layout === 'tabs' && active !== module.id;
      node.id = `module-${module.id}`;
      node.dataset.moduleType = module.type;
      node.dataset.moduleId = module.id;
      node.setAttribute('part', 'module');
      return node;
    });
    for (const id of this.moduleNodes.keys()) if (!this.config.modules.some(module => module.id === id)) this.moduleNodes.delete(id);
    return html`<ha-card part="card" data-style=${settings.appearance.style} data-font=${settings.appearance.font} data-surface=${settings.appearance.surface} data-accent=${String(accent.visible)} role="group" aria-label=${this.config.title} style=${style}>
      ${this.previewData ? html`<p class="demo">${this.w('DEMO · sample data', 'DEMO · exempeldata')}</p>` : ''}
      <header part="header">${settings.appearance.show_header ? html`<div class="heading" part="title">${this.actionHeading()}<small>${this.w('Your Formula 1 view', 'Din Formel 1-vy')}</small></div>` : ''}
        <div class="tools" part="toolbar">${this.config.context.show_focus_control && drivers.length ? html`<label><span class="sr">${this.w('Driver focus', 'Förarfokus')}</span><select .value=${focusedDriver} @change=${this.chooseDriver}><option value="" .selected=${!focusedDriver}>${this.w('All drivers', 'Alla förare')}</option>${repeat(drivers, driver => String(driver.racing_number), driver => html`<option value=${String(driver.racing_number)} .selected=${focusedDriver === String(driver.racing_number)}>${driver.tla ?? driver.racing_number}</option>`)}</select></label>` : ''}
        ${this.group && this.config.context.share.includes('selection') ? html`<label><span class="sr">${this.w('Shared session selection', 'Delat sessionsurval')}</span><select .value=${groupSelection} @change=${this.chooseGroupSelection}>${groupSelections.map(([selection, title]) => html`<option value=${JSON.stringify(selection)}>${title}</option>`)}</select></label>` : ''}
        ${this.config.context.show_freeze_control ? html`<button @click=${this.freeze} aria-pressed=${String(this.frozen)}>${this.frozen ? this.w('Resume', 'Fortsätt') : this.w('Freeze view', 'Frys vyn')}</button>` : ''}</div>
      </header>
      ${this.actionAlternatives()}
      ${!this.previewData && this.hass.connection?.connected === false ? html`<p class="connection-status" part="connection-status" role="status">${this.w('Disconnected from Home Assistant · any visible values are saved snapshots. Live updates resume after reconnection.', 'Frånkopplad från Home Assistant · värden som visas är sparade ögonblicksbilder. Liveuppdateringar återkommer efter anslutning.')}</p>` : ''}
      ${this.config.context.viewing_controls ? html`<f1-viewing-controls part="viewing-controls" .model=${data.viewingModel(this.hass, this.entry, this.config.context.spoilers)} .settings=${settings} .connection=${this.hass.connection} .readonly=${Boolean(this.preview || this.previewData || this.frozen)} .localHidden=${this.config.context.spoilers === 'hide'} .request=${this.viewingRequest?.entryId === this.entry.entry_id && this.viewingRequest.connection === this.hass.connection ? this.viewingRequest : null} @f1-viewing-action=${this.viewingAction}></f1-viewing-controls>` : ''}
      <div aria-live=${settings.accessibility.announce ? 'polite' : 'off'} aria-atomic="true">${this.frozen ? html`<p class="frozen">${this.w('Reading snapshot', 'Fryst läsvy')} · ${dateTime(this.frozenAt, settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' })} · ${this.w('Only this card is paused', 'Endast detta kort är pausat')}${this.frozenGeneration !== this.savedSources.viewGeneration ? html`<br>${this.w('Session or playback settings have changed. This snapshot keeps its original context. Resume to show current data.', 'Sessionen eller uppspelningsinställningarna har ändrats. Läsbilden behåller sitt ursprungliga sammanhang. Välj Fortsätt för att visa aktuell data.')}` : ''}${this.focus.driver !== this.frozenFocus?.driver || this.focus.team !== this.frozenFocus?.team ? html`<br>${this.w('Group focus has changed. Resume to follow it.', 'Gruppens fokus har ändrats. Välj Fortsätt för att följa det.')}` : ''}</p>` : ''}</div>
      ${this.config.layout === 'tabs' ? html`<nav part="tabs" aria-label=${this.w('Modules', 'Moduler')}>${modules.map(module => html`<button aria-pressed=${String(active === module.id)} aria-controls=${`module-${module.id}`} @click=${() => { this.tab = module.id; }}>${module.title || models.get(module.id).title}</button>`)}</nav>` : ''}
      ${nodes.length ? html`<div class="modules" part="modules">${nodes}</div>` : this.emptyCard()}
      ${configWarnings(this.config).length ? html`<p class="muted">${this.w('Some settings need a newer card version. They are preserved in the editor.', 'Vissa inställningar kräver en nyare kortversion. De finns kvar i editorn.')}</p>` : ''}
    </ha-card>`;
  }
  emptyCard() { return html`<div class="empty" part="empty-state">${this.w('Add your first module in the editor.', 'Lägg till din första modul i editorn.')}</div>`; }
}
if (!customElements.get('f1-sensor-card')) customElements.define('f1-sensor-card', F1SensorCard);
