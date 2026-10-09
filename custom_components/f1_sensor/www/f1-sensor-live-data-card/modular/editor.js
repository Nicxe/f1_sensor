const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, css, repeat }, configAPI, { MODULES, PRESETS, FIELDS, defaultFields, fieldDefinition, moduleFields, timingFields, INCIDENT_SIGNALS, label, moduleTitle, moduleFocusKinds }, { sharedStyles, words }, { watchEntries, HistoryResources }, { visibilityMet }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./config.js'), load('./catalog.js'), load('./view.js'), load('./connection.js'), load('./visibility.js'),
]);
await load('./arranger.js');
const { source, array, sessionContext, lapChartModel, spoilerState, accentTeams } = await load('./data.js');
const { telemetryPlan, telemetryModel } = await load('./telemetry-data.js');
const { replayModel } = await load('./data.js');
const { cardAccent, PALETTES, SIGNALS } = await load('./semantics.js');
let telemetryLoading;
const { restoreLegacy, isLegacyConfig } = await load('./migration.js');
const { resultChoices, resultsModel, standingsModel, progressionModel, archiveModel, archivePlan } = await load('./season-data.js');

export class F1SensorCardEditor extends LitElement {
  static properties = { hass: { attribute: false }, config: { state: true }, selected: { state: true }, error: { state: true }, pendingPreset: { state: true }, entries: { state: true }, transfer: { state: true }, templateName: { state: true }, pendingTemplate: { state: true }, templateEntry: { state: true }, pendingRestore: { state: true }, originalTransfer: { state: true }, arranging: { state: true } };
  static styles = [sharedStyles, css`
    :host { container-type:inline-size; --f1-text:var(--primary-text-color,#e9edf3); --f1-muted:var(--secondary-text-color,#b9c1ce); --f1-surface:var(--card-background-color,#17202b); --f1-border:var(--divider-color,#637083); --editor-card-accent:var(--primary-color,#03a9f4); --editor-module-accent:#e10600; }
    .builder { min-width:0; }
    .form { min-width:0; }
    .toolbar,.module-row,.buttons { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .toolbar { justify-content:space-between; margin:12px 0; }
    .presets { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-bottom:16px; }
    .presets button { text-align:left; min-height:72px; overflow-wrap:anywhere; }
    .presets small { display:block; color:var(--f1-muted); font-size:.75em; }
    .scope-panel { --scope-accent:var(--editor-card-accent); position:relative; margin:16px 0; padding:16px; border:1px solid color-mix(in srgb,var(--scope-accent) 42%,var(--f1-border)); border-inline-start:5px solid var(--scope-accent); border-radius:14px; background:color-mix(in srgb,var(--scope-accent) 6%,var(--f1-surface)); box-shadow:0 1px 2px rgba(0,0,0,.08); }
    .module-scope { --scope-accent:var(--editor-module-accent); }
    .scope-heading,.selected-module-heading { display:flex; gap:12px; align-items:flex-start; margin-bottom:12px; }
    .scope-heading h3,.selected-module-heading h4 { margin:2px 0 3px; line-height:1.2; }
    .scope-heading p,.selected-module-heading p { margin:0; }
    .scope-badge,.module-number { flex:0 0 auto; display:grid; place-items:center; min-width:34px; height:34px; padding:0 7px; border:2px solid var(--scope-accent); border-radius:9px; color:var(--f1-text); background:var(--f1-surface); font-size:.72em; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }
    .scope-kicker { color:var(--f1-text); font-size:.72em; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }
    .scope-description { color:var(--f1-muted); font-size:.84em; }
    .module-list { list-style:none; margin:12px 0; padding:0; }
    .module-row { margin-bottom:8px; border:1px solid var(--f1-border); border-radius:10px; padding:4px; background:var(--f1-surface); transition:border-color .15s ease,box-shadow .15s ease; }
    .module-row[data-selected=true] { border-color:var(--editor-module-accent); box-shadow:inset 4px 0 0 var(--editor-module-accent); }
    .module-row .select-module { flex:1; display:flex; align-items:center; gap:10px; text-align:left; min-width:120px; border:0; }
    .module-row .select-module[aria-pressed=true] { color:var(--f1-text); background:transparent; box-shadow:none; }
    .module-row .module-index { color:var(--f1-muted); font-variant-numeric:tabular-nums; font-size:.8em; font-weight:700; }
    .module-row .module-name { font-weight:650; }
    .module-width { display:block; font-size:.8em; font-weight:400; color:var(--f1-muted); }
    .selected-module { margin-top:16px; padding:14px; border:1px solid color-mix(in srgb,var(--editor-module-accent) 36%,var(--f1-border)); border-radius:11px; background:color-mix(in srgb,var(--editor-module-accent) 4%,var(--f1-surface)); }
    .selected-module-heading { margin-bottom:6px; }
    label { display:block; margin:12px 0; }
    label span { display:block; margin-bottom:5px; }
    input:not([type=checkbox]),select,textarea { width:100%; min-height:44px; padding:8px 10px; border:1px solid var(--f1-border); border-radius:7px; background:var(--f1-surface); }
    input[type=checkbox] { width:22px; height:22px; accent-color:var(--primary-color); }
    .check { display:flex; align-items:center; gap:10px; min-height:44px; margin:2px 0; }
    .check span { margin:0; }
    .palette-row { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:end; gap:8px; }
    .palette-row button { margin-bottom:12px; }
    .field-row { display:flex; align-items:center; gap:5px; }
    .field-row .check { flex:1; }
    .visibility-status { display:inline-flex; align-items:center; gap:6px; margin:0 0 8px; padding:5px 8px; border:1px solid var(--f1-border); border-radius:999px; font-size:.82em; }
    .condition-list { display:grid; gap:10px; margin:10px 0; }
    .condition-row { padding:10px; border:1px solid var(--f1-border); border-radius:9px; background:var(--f1-surface); }
    .condition-row > .buttons { justify-content:space-between; }
    .condition-row .condition-list { margin-inline-start:12px; padding-inline-start:10px; border-inline-start:2px solid var(--f1-border); }
    .weekday-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:2px 8px; }
    .weekday-grid .check { min-width:0; }
    details { border-top:1px solid var(--f1-border); padding:12px 0; }
    details:first-of-type { border-top:0; }
    summary { cursor:pointer; min-height:44px; display:flex; align-items:center; justify-content:space-between; gap:12px; font-weight:650; }
    summary::-webkit-details-marker { display:none; }
    summary::marker { content:""; }
    summary::after { content:"›"; flex:0 0 auto; color:var(--f1-muted); font-size:1.35em; line-height:1; transform:rotate(0deg); transition:transform .15s ease; }
    details[open] > summary::after { transform:rotate(90deg); }
    .starter { padding:0 14px 14px; border:1px solid var(--f1-border); border-radius:12px; background:color-mix(in srgb,var(--f1-border) 5%,transparent); }
    .starter summary { margin-bottom:4px; }
    .danger,.notice { border:1px solid currentColor; border-radius:8px; padding:12px; margin:12px 0; }
    .notice p { margin-bottom:8px; }
    .danger { color:var(--error-color,#ffb4b4); }
    .muted { font-size:.85em; }
    textarea { min-height:130px; font-family:monospace; font-size:.85em; }
    @media(forced-colors:active) { .scope-panel,.selected-module,.module-row[data-selected=true] { border-color:CanvasText; } .scope-badge,.module-number { border-color:CanvasText; color:CanvasText; } }
  `];
  constructor() { super(); this.archive = new HistoryResources(() => this.requestUpdate()); this.telemetry = new HistoryResources(() => this.requestUpdate()); this.history = []; this.entries = []; this.selected = ''; this.error = ''; this.pendingPreset = ''; this.transfer = ''; this.templateName = ''; this.pendingTemplate = null; this.templateEntry = ''; }
  setConfig(value) { this.config = configAPI.normalizeConfig(value); if (!this.selected || !this.config.modules.some(module => module.id === this.selected)) this.selected = this.config.modules[0]?.id ?? ''; }
  get language() { return this.hass?.locale?.language ?? this.hass?.language ?? 'en'; }
  w(en, sv) { return words(this.language, en, sv); }
  connectedCallback() { super.connectedCallback(); this.requestUpdate(); }
  disconnectedCallback() { super.disconnectedCallback(); this.archive.close(); this.telemetry.close(); this.stopEntries?.(); this.stopEntries = null; this.connection = null; }
  willUpdate() {
    if (this.isConnected && this.hass?.connection && this.connection !== this.hass.connection) {
      this.stopEntries?.(); this.connection = this.hass.connection;
      this.stopEntries = watchEntries(this.hass, state => { if (state.data) this.entries = state.data; });
    }
    const entry = this.config?.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
    const module = this.config?.modules.find(item => item.id === this.selected);
    this.telemetry.sync(this.hass, this.isConnected && entry && module?.type === 'telemetry' && spoilerState(this.hass, entry, this.config.context.spoilers) === 'clear' ? telemetryPlan(module, entry, replayModel(this.hass, entry), query => this.telemetry.read(query)).requests : []);
    this.archive.sync(this.hass, this.isConnected && entry && module?.type === 'archive' && spoilerState(this.hass, entry, this.config.context.spoilers) === 'clear' ? archivePlan(module, entry.entry_id, query => this.archive.read(query)).requests : []);
  }
  updateConfig(change) {
    try {
      const next = typeof change === 'function' ? change(configAPI.copyConfig(this.config)) : change;
      const config = configAPI.normalizeConfig(next);
      this.history.push(configAPI.copyConfig(this.config)); if (this.history.length > 40) this.history.shift();
      this.config = config; this.error = '';
      this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: configAPI.copyConfig(config) }, bubbles: true, composed: true }));
    } catch (error) { this.error = error.message; }
  }
  reviewTemplate(source) {
    try {
      this.pendingTemplate = configAPI.importTemplate(source);
      const saved = this.pendingTemplate.card.f1_entry_id;
      this.templateEntry = saved && !this.entries.some(entry => entry.entry_id === saved) ? '' : saved;
      this.error = '';
    } catch (error) { this.pendingTemplate = null; this.error = error.message; }
  }
  applyTemplate() {
    if (!this.pendingTemplate) return;
    const saved = this.pendingTemplate.card.f1_entry_id;
    const missing = saved && !this.entries.some(entry => entry.entry_id === saved);
    if (missing && !this.templateEntry) { this.error = this.w('modular.choose_an_f1_sensor_installation_for_this_template'); return; }
    const card = configAPI.copyConfig(this.pendingTemplate.card);
    if (missing) card.f1_entry_id = this.templateEntry;
    this.updateConfig(() => card);
    this.selected = card.modules[0]?.id ?? '';
    this.pendingTemplate = null; this.templateEntry = '';
  }
  async readTemplateFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 512_000) { this.error = this.w('modular.template_file_is_larger_than_512_kb'); return; }
    this.transfer = await file.text();
    this.reviewTemplate(this.transfer);
    event.target.value = '';
  }
  restoreOriginal() {
    try {
      const config = restoreLegacy(this.config);
      this.dispatchEvent(new CustomEvent('config-changed', { detail: { config }, bubbles: true, composed: true }));
    } catch (error) { this.error = error.message; }
  }
  migrationSettings() {
    if (!isLegacyConfig(this.config?.migration?.original)) return '';
    return html`<details><summary>${this.w('modular.original_card_and_recovery')}</summary>
      <p>${this.w('modular.this_card_was_converted_from')} <code>${this.config.migration.original.type}</code>.</p>
      <p>${this.w('modular.the_saved_original_includes_settings_that_could_not_be_converted_restoring_replaces_the_current')}</p>
      <div class="buttons"><button @click=${() => { this.originalTransfer = JSON.stringify(restoreLegacy(this.config), null, 2); }}>${this.w('modular.export_original')}</button><button @click=${() => { this.pendingRestore = true; }}>${this.w('modular.restore_original')}</button></div>
      ${this.originalTransfer ? html`<label><span>${this.w('modular.original_configuration')}</span><textarea readonly .value=${this.originalTransfer}></textarea></label>` : ''}
      ${this.pendingRestore ? html`<div class="notice" role="status"><p>${this.w('modular.replace_this_converted_card_with_its_exact_saved_original')}</p><div class="buttons"><button @click=${() => { this.pendingRestore = false; }}>${this.w('modular.cancel_restoration')}</button><button @click=${() => this.restoreOriginal()}>${this.w('modular.restore_original_card')}</button></div></div>` : ''}
    </details>`;
  }
  setGroup(group, key, value) { this.updateConfig(config => { config[group][key] = value; return config; }); }
  setModule(key, value) { this.updateConfig(config => { const module = config.modules.find(module => module.id === this.selected); if (module) { module[key] = value; if (['timing', 'archive'].includes(module.type) && key === 'fields') module.options.profile = 'custom'; } return config; }); }
  setOption(key, value) {
    this.updateConfig(config => {
      const module = config.modules.find(module => module.id === this.selected);
      if (module) {
        // An explicit content change carries its untouched starter columns with it.
        // Customized fields remain the user's choice across content changes.
        if (key === 'content' && JSON.stringify(module.fields) === JSON.stringify(defaultFields(module))) module.fields = [...defaultFields({ ...module, options: { ...module.options, [key]: value } })];
        if (module.type === 'archive') {
          if (key === 'year') Object.assign(module.options, { round: '', session_key: '', selected: [] });
          if (key === 'round') Object.assign(module.options, { session_key: '', selected: [] });
          if (key === 'session_key') module.options.selected = [];
        }
        module.options[key] = value;
      }
      return config;
    });
  }
  telemetryPicker(module) {
    const entry = this.config.f1_entry_id ? this.entries.find(entry => entry.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
    if (!entry) return html`<p class="muted">${this.w('modular.choose_an_f1_sensor_installation_to_select_recorded_laps')}</p>`;
    if (spoilerState(this.hass, entry, this.config.context.spoilers) !== 'clear') return html`<p class="muted">${this.w('modular.spoiler_protection_hides_the_recorded_laps')}</p>`;
    if (!this.telemetryNode) {
      this.telemetryNode = document.createElement('f1-telemetry-view');
      this.telemetryNode.pickerOnly = true;
      telemetryLoading ??= load('./telemetry-view.js').catch(error => { telemetryLoading = null; throw error; });
      telemetryLoading.catch(() => { this.telemetryError = true; this.requestUpdate(); });
      this.telemetryNode.addEventListener('f1-telemetry-selection', event => {
        event.stopPropagation();
        const current = this.telemetryNode.model;
        if (!current.replay.loaded || event.detail.sessionId !== current.replay.sessionId || event.detail.module !== this.selected) return;
        this.updateConfig(config => {
          const selected = config.modules.find(module => module.id === this.selected);
          selected.options.selected = event.detail.selected; selected.options.session_id = event.detail.sessionId;
          return config;
        });
      });
      this.telemetryNode.addEventListener('f1-telemetry-retry', event => { event.stopPropagation(); this.telemetry.retry(this.telemetryNode.model.requests); });
    }
    if (this.telemetryError) return html`<p>${this.w('modular.reload_the_editor_to_load_the_lap_picker')}</p>`;
    this.telemetryNode.module = module; this.telemetryNode.model = telemetryModel(this.hass, entry, module, query => this.telemetry.read(query));
    this.telemetryNode.settings = { language: this.language };
    return this.telemetryNode;
  }
  undo() {
    const previous = this.history.pop(); if (!previous) return;
    this.config = previous; this.error = '';
    this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: configAPI.copyConfig(previous) }, bubbles: true, composed: true }));
  }
  input(title, value, change, type = 'text') {
    return html`<label><span>${title}</span><input type=${type} .value=${String(value ?? '')} @change=${event => change(type === 'number' ? Number(event.target.value) : event.target.value)}></label>`;
  }
  select(title, value, options, change) {
    return html`<label><span>${title}</span><select aria-label=${title} .value=${value} @change=${event => change(event.target.value)}>${options.map(([key, text]) => html`<option value=${key} .selected=${key === value}>${text}</option>`)}</select></label>`;
  }
  check(title, value, change) { return html`<label class="check"><input type="checkbox" .checked=${value === true} @change=${event => change(event.target.checked)}><span>${title}</span></label>`; }
  focusPicker(kind, title, value, change, inherit = false) {
    const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
    const module = this.config.modules.find(item => item.id === this.selected);
    const model = module?.type === 'results' ? resultsModel(this.hass, entry, module) : module?.type === 'standings' ? standingsModel(this.hass, entry, module) : null;
    const drivers = model ? model.allRows.map(row => ({ racing_number: row.number || row.id, name: row.name, team: row.team }))
      : array(source(this.hass, entry, 'driver_list').attributes.drivers).filter(item => item && typeof item === 'object');
    const options = kind === 'driver' ? drivers.filter(item => item.racing_number != null).map(item => [String(item.racing_number), `${item.name ?? item.full_name ?? item.tla ?? item.racing_number} · ${item.racing_number}`])
      : [...new Set(drivers.map(item => item.team).filter(Boolean))].sort().map(team => [team, team]);
    if (value && !options.some(([id]) => id === value)) options.unshift([value, `${value} · ${this.w('modular.saved_selection')}`]);
    return this.select(title, value, [['', inherit ? this.w('modular.follow_card_focus') : this.w('modular.all')], ...options], change);
  }
  selectionPicker(title, value, change, { inherit = false, archive = null } = {}) {
    const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
    const current = source(this.hass, entry, 'current_session'), replay = source(this.hass, entry, 'replay_status'), player = source(this.hass, entry, 'replay_player');
    const choices = [];
    if (inherit) choices.push([{ mode: 'inherit' }, this.w('modular.follow_card_session')]);
    for (const [sourceName, en, sv] of [['auto', 'Automatic source', 'Automatisk källa'], ['live', 'Follow live session', 'Följ livesession'], ['replay', 'Follow loaded replay', 'Följ laddad replay']]) choices.push([{ mode: 'follow', source: sourceName }, this.w(en, sv)]);
    const pinned = (sourceName, identity, name) => {
      const season = Number(identity.season), meetingKey = String(identity.meeting_key ?? ''), sessionKey = String(identity.session_key ?? '');
      if (Number.isInteger(season) && season >= 1950 && season <= 9999 && meetingKey && sessionKey) choices.push([{ mode: 'pinned', source: sourceName, season, meeting_key: meetingKey, session_key: sessionKey }, name]);
    };
    pinned('live', current.attributes, `${this.w('modular.pin_current_live_session')} · ${current.attributes.meeting_name ?? current.state ?? ''}`);
    const replayAttrs = { ...replay.attributes, ...player.attributes };
    pinned('replay', { season: replayAttrs.selected_session_year ?? replayAttrs.selected_year, meeting_key: replayAttrs.selected_meeting_key, session_key: replayAttrs.selected_session_key }, `${this.w('modular.pin_loaded_replay')} · ${replayAttrs.selected_session ?? ''}`);
    if (archive?.context) pinned('archive', { season: archive.context.season, meeting_key: archive.context.meetingKey, session_key: archive.context.sessionKey }, `${this.w('modular.pin_selected_archive_session')} · ${archive.context.meeting} · ${archive.context.session}`);
    const serialized = JSON.stringify(value);
    if (!choices.some(([choice]) => JSON.stringify(choice) === serialized)) choices.push([value, this.w('modular.saved_pinned_session')]);
    return this.select(title, serialized, choices.map(([choice, label]) => [JSON.stringify(choice), label]), selected => change(JSON.parse(selected)));
  }
  move(id, offset) {
    this.updateConfig(config => configAPI.moveModule(config, id, offset));
    this.updateComplete.then(() => [...this.shadowRoot.querySelectorAll('[data-module]')].find(button => button.dataset.module === id)?.focus({ preventScroll: true }));
  }
  visibilityList(module, parentPath) {
    let list = module.visibility;
    for (const index of parentPath) list = list[index].conditions;
    return list;
  }
  visibilityDefault(type) {
    const entity = Object.keys(this.hass?.states ?? {})[0] ?? 'sensor.example';
    if (type === 'state') return { condition: type, entity, state: 'on' };
    if (type === 'numeric_state') return { condition: type, entity, above: 0 };
    if (type === 'screen') return { condition: type, media_query: '(min-width: 768px)' };
    if (type === 'user') return { condition: type, users: [this.hass?.user?.id ?? 'current-user'] };
    if (type === 'location') {
      const person = Object.entries(this.hass?.states ?? {}).find(([id, state]) => id.startsWith('person.') && state?.attributes?.user_id === this.hass?.user?.id)?.[1];
      return { condition: type, locations: [person?.state ?? 'home'] };
    }
    if (type === 'time') return { condition: type, after: '08:00' };
    return { condition: type, conditions: [this.visibilityDefault('state')] };
  }
  updateVisibility(change) {
    this.updateConfig(config => {
      const module = config.modules.find(item => item.id === this.selected);
      if (module) change(module);
      return config;
    });
  }
  addVisibility(parentPath, type) { this.updateVisibility(module => { this.visibilityList(module, parentPath).push(this.visibilityDefault(type)); }); }
  removeVisibility(path) { this.updateVisibility(module => { const list = this.visibilityList(module, path.slice(0, -1)); list.splice(path.at(-1), 1); }); }
  replaceVisibility(path, type) { this.updateVisibility(module => { const list = this.visibilityList(module, path.slice(0, -1)); list[path.at(-1)] = this.visibilityDefault(type); }); }
  setVisibilityValue(path, key, value) {
    this.updateVisibility(module => {
      const list = this.visibilityList(module, path.slice(0, -1)), condition = list[path.at(-1)];
      if (value === undefined) delete condition[key]; else condition[key] = value;
    });
  }
  listValue(value) { return Array.isArray(value) ? value.join(', ') : String(value ?? ''); }
  parseList(value) { return [...new Set(value.split(',').map(item => item.trim()).filter(Boolean))]; }
  threshold(value) { const text = value.trim(); return text === '' ? undefined : /^-?(?:\d+\.?\d*|\.\d+)$/.test(text) ? Number(text) : text; }
  conditionTypeOptions() {
    return [
      ['state', this.w('modular.entity_state')], ['numeric_state', this.w('modular.numeric_state')],
      ['screen', this.w('modular.screen')], ['user', this.w('modular.user')], ['location', this.w('modular.location')],
      ['time', this.w('modular.time')], ['and', this.w('modular.all_conditions_and')],
      ['or', this.w('modular.any_condition_or')], ['not', this.w('modular.invert_conditions_not')],
    ];
  }
  visibilityCondition(condition, path) {
    const name = `${this.w('modular.condition')} ${path.map(index => index + 1).join('.')}`;
    const set = (key, value) => this.setVisibilityValue(path, key, value);
    const common = html`<div class="buttons">${this.select(this.w('modular.condition_type'), condition.condition, this.conditionTypeOptions(), value => this.replaceVisibility(path, value))}<button aria-label=${`${this.w('modular.remove')} ${name}`} @click=${() => this.removeVisibility(path)}>${this.w('modular.remove')}</button></div>`;
    if (['and', 'or', 'not'].includes(condition.condition)) return html`<section class="condition-row" aria-label=${name}>${common}<p class="muted">${condition.condition === 'and' ? this.w('modular.every_nested_condition_must_match') : condition.condition === 'or' ? this.w('modular.at_least_one_nested_condition_must_match') : this.w('modular.the_nested_result_is_inverted')}</p>${this.visibilityConditions(condition.conditions, path)}</section>`;
    let fields;
    if (condition.condition === 'state') {
      const negative = condition.state === undefined;
      fields = html`${this.entityInput(this.w('modular.entity'), condition.entity, value => set('entity', value))}${this.input(this.w('modular.attribute_optional'), condition.attribute, value => set('attribute', value || undefined))}${this.select(this.w('modular.comparison'), negative ? 'not' : 'is', [['is', this.w('modular.is')], ['not', this.w('modular.is_not')]], value => { const current = condition.state ?? condition.state_not; this.updateVisibility(module => { const item = this.visibilityList(module, path.slice(0, -1))[path.at(-1)]; delete item.state; delete item.state_not; item[value === 'is' ? 'state' : 'state_not'] = current; }); })}${this.input(this.w('modular.state_values_separated_by_commas'), this.listValue(condition.state ?? condition.state_not), value => set(negative ? 'state_not' : 'state', this.parseList(value)))}`;
    } else if (condition.condition === 'numeric_state') fields = html`${this.entityInput(this.w('modular.entity'), condition.entity, value => set('entity', value))}${this.input(this.w('modular.attribute_optional'), condition.attribute, value => set('attribute', value || undefined))}${this.input(this.w('modular.above_optional'), condition.above, value => set('above', this.threshold(value)))}${this.input(this.w('modular.below_optional'), condition.below, value => set('below', this.threshold(value)))}`;
    else if (condition.condition === 'screen') fields = html`${this.input(this.w('modular.media_query'), condition.media_query, value => set('media_query', value))}<div class="buttons"><button @click=${() => set('media_query', '(max-width: 767px)')}>${this.w('modular.phone')}</button><button @click=${() => set('media_query', '(min-width: 768px) and (max-width: 1023px)')}>${this.w('modular.tablet')}</button><button @click=${() => set('media_query', '(min-width: 1024px)')}>${this.w('modular.desktop')}</button></div>`;
    else if (condition.condition === 'user') fields = html`${this.input(this.w('modular.user_ids_separated_by_commas'), this.listValue(condition.users), value => set('users', this.parseList(value)))}${this.hass?.user?.id ? html`<button @click=${() => set('users', [this.hass.user.id])}>${this.w('modular.use_current_user')}</button>` : ''}`;
    else if (condition.condition === 'location') fields = this.input(this.w('modular.locations_separated_by_commas'), this.listValue(condition.locations), value => set('locations', this.parseList(value)));
    else fields = html`${this.input(this.w('modular.after_optional'), condition.after, value => set('after', value || undefined), 'time')}${this.input(this.w('modular.before_optional'), condition.before, value => set('before', value || undefined), 'time')}<p>${this.w('modular.weekdays_optional')}</p><div class="weekday-grid">${[['mon', 'Mon', 'Mån'], ['tue', 'Tue', 'Tis'], ['wed', 'Wed', 'Ons'], ['thu', 'Thu', 'Tor'], ['fri', 'Fri', 'Fre'], ['sat', 'Sat', 'Lör'], ['sun', 'Sun', 'Sön']].map(([day, en, sv]) => this.check(this.w(en, sv), condition.weekdays?.includes(day), checked => set('weekdays', checked ? [...(condition.weekdays ?? []), day] : (condition.weekdays ?? []).filter(item => item !== day))))}</div>`;
    return html`<section class="condition-row" aria-label=${name}>${common}${fields}</section>`;
  }
  visibilityConditions(conditions, parentPath = []) {
    return html`<div class="condition-list">${conditions.map((condition, index) => this.visibilityCondition(condition, [...parentPath, index]))}<div class="buttons">${this.select(this.w('modular.add_condition'), '', [['', this.w('modular.choose')], ...this.conditionTypeOptions()], value => { if (value) this.addVisibility(parentPath, value); })}</div></div>`;
  }
  visibilitySettings(module) {
    return html`<details><summary>${this.w('modular.visibility_conditions')}</summary><p class="muted">${this.w('modular.like_home_assistant_card_visibility_every_top_level_condition_must_match_session_phases_above')}</p>${module.visibility.length ? html`<p class="visibility-status">${visibilityMet(module.visibility, this.hass) ? this.w('modular.visible_now') : this.w('modular.hidden_now')}</p>` : html`<p class="visibility-status">${this.w('modular.always_visible')}</p>`}${this.visibilityConditions(module.visibility)}</details>`;
  }
  entityInput(title, value, change) {
    const id = `entities-${this.selected}-${title.replace(/[^a-z0-9]/gi, '-').toLowerCase()}`;
    return html`<label><span>${title}</span><input list=${id} .value=${String(value ?? '')} @change=${event => change(event.target.value)}><datalist id=${id}>${Object.keys(this.hass?.states ?? {}).sort().map(entity => html`<option value=${entity}></option>`)}</datalist></label>`;
  }
  columnWidth(span) {
    return span === 'full' ? this.w('modular.full_card_width') : span === 1 ? this.w('modular.1_column') : this.w('modular.span_columns', { span: span });
  }
  minisectorOverlap(module) {
    const sectors = [1, 2, 3].filter(n => module.fields.includes(`sector_${n}_with_minisectors`)
      && (module.fields.includes(`sector_${n}`) || module.fields.includes(`minisector_${n}`)));
    if (!sectors.length) return '';
    const sectorList = sectors.join(', ');
    return this.w('modular.minisector_duplicate_fields', { sectors: sectorList });
  }
  moduleSettings() {
    const saved = this.config.modules.find(module => module.id === this.selected), definition = MODULES[saved?.type];
    if (!saved) return html``;
    const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
    const protectedArchive = saved.type === 'archive' && spoilerState(this.hass, entry, this.config.context.spoilers) !== 'clear';
    const archiveState = saved.type === 'archive' ? archiveModel(saved, entry?.entry_id, query => protectedArchive ? { status: 'ready', data: null } : this.archive.read(query)) : null;
    const archiveFields = archiveState?.fields ?? null;
    const module = saved.type === 'timing' ? { ...saved, fields: timingFields(saved, sessionContext(this.hass, entry).name) } : archiveFields ? { ...saved, fields: archiveFields } : saved;
    const available = moduleFields(module), fields = [...module.fields, ...available.filter(id => !module.fields.includes(id))];
    const index = this.config.modules.findIndex(item => item.id === module.id);
    return html`<section class="selected-module" aria-label=${this.w('modular.selected_module')}><div class="selected-module-heading"><span class="module-number" aria-hidden="true">${index + 1}</span><div><p class="scope-kicker">${this.w('modular.editing_module_value_of_length', { value: index + 1, length: this.config.modules.length })}</p><h4>${moduleTitle(module, this.language)}</h4><p class="scope-description">${this.w('modular.only_this_module_is_affected_by_the_settings_below')}</p></div></div>
      ${this.input(this.w('modular.module_title'), module.title, value => this.setModule('title', value))}
      ${this.check(this.w('modular.show_module'), module.enabled, value => this.setModule('enabled', value))}
      ${this.config.layout === 'columns' ? html`
        ${this.select(this.w('modular.module_width'), String(module.column_span), [...[1, 2, 3, 4].map(count => [String(count), this.columnWidth(count)]), ['full', this.columnWidth('full')]], value => this.setModule('column_span', value === 'full' ? value : Number(value)))}
        <p class="muted">${this.w('modular.widths_shrink_to_fit_the_available_columns_full_card_width_always_starts_a_new')}</p>
      ` : ''}
      ${this.minisectorOverlap(module) ? html`<p class="notice" role="status">${this.minisectorOverlap(module)}</p>` : ''}
      <details><summary>${this.w('modular.module_appearance')}</summary>
        ${this.check(this.w('modular.show_module_title'), module.show_header, value => this.setModule('show_header', value))}
        ${['timing', 'minisectors', 'results', 'standings', 'archive', 'tyres', 'pit_stops', 'strategy', 'battles', 'timeline', 'incidents'].includes(module.type) ? html`${this.check(this.w('modular.show_table_header'), module.show_table_header, value => this.setModule('show_table_header', value))}<p class="muted">${this.w('modular.hidden_column_labels_remain_available_to_screen_readers_chart_data_tables_always_keep_their')}</p>` : ''}
        <p class="muted">${this.w('modular.session_details_and_status_labels_remain_visible_when_the_title_is_hidden')}</p>
      </details>
      ${['timing', 'archive'].includes(module.type) && module.options.profile !== 'custom' && (module.type !== 'archive' || module.options.content === 'classification') ? html`<p class="muted">${this.w('modular.this_profile_chooses_the_columns_changing_a_checkbox_or_order_switches_to_custom_columns')}</p>` : ''}
      <details open><summary>${this.w('modular.content_and_columns')}</summary>${repeat(fields, id => id, id => html`<div class="field-row">
        ${this.check(label(fieldDefinition(module, id), this.language) || id, module.fields.includes(id), checked => this.setModule('fields', checked ? [...module.fields, id] : module.fields.filter(key => key !== id)))}
        ${module.fields.includes(id) ? html`<button aria-label=${`${this.w('modular.move_up')} ${label(fieldDefinition(module, id), this.language) || id}`} ?disabled=${module.fields.indexOf(id) === 0} @click=${() => { const fields = [...module.fields], index = fields.indexOf(id); [fields[index - 1], fields[index]] = [fields[index], fields[index - 1]]; this.setModule('fields', fields); }}>↑</button><button aria-label=${`${this.w('modular.move_down')} ${label(fieldDefinition(module, id), this.language) || id}`} ?disabled=${module.fields.indexOf(id) === module.fields.length - 1} @click=${() => { const fields = [...module.fields], index = fields.indexOf(id); [fields[index + 1], fields[index]] = [fields[index], fields[index + 1]]; this.setModule('fields', fields); }}>↓</button>` : ''}
        ${!available.includes(id) ? html`<small class="muted">${this.w('modular.saved_not_used_by_this_view')}</small>` : ''}
      </div>`)}</details>
      <details><summary>${this.w('modular.module_options')}</summary>${Object.entries(definition?.options ?? {}).map(([key, option]) => {
        const title = module.type === 'incidents' && module.options.content === 'track_limits_summary' && key === 'rows' ? this.w('modular.maximum_drivers') : label(option, this.language), value = module.options[key];
        if (module.type === 'archive') {
          const chart = module.options.content !== 'classification';
          if (chart && ['profile', 'sort', 'direction', 'rows'].includes(key) || !chart && ['presentation', 'start_lap', 'end_lap', 'series_limit'].includes(key)) return '';
          if (['source_choice', 'source_list'].includes(option.type)) {
            const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
            const allowed = spoilerState(this.hass, entry, this.config.context.spoilers) === 'clear';
            const model = archiveModel(module, entry?.entry_id, query => allowed ? this.archive.read(query) : { status: 'ready', data: null });
            const choices = key === 'round' ? model.meetings.map(item => [String(item.round), `${item.round} · ${item.name}`]) : key === 'session_key' ? model.sessions.map(item => [item.session_key, item.name]) : model.allSeries.map(item => [item.id, item.name]);
            const selected = option.type === 'source_list' ? value : value ? [value] : [];
            for (const id of selected) if (!choices.some(([key]) => key === id)) choices.push([id, `${id} · ${this.w('modular.saved_selection')}`]);
            const status = !allowed ? this.w('modular.spoiler_protection_hides_the_archive_choices') : model.error ? this.w('modular.archive_unavailable_try_again') : model.loading ? this.w('modular.loading_archive') : null;
            return html`${option.type === 'source_list' ? html`<p>${title}</p>${choices.map(([id, name]) => this.check(name, value.includes(id), enabled => this.setOption(key, enabled ? [...value, id] : value.filter(item => item !== id))))}` : this.select(title, value, [['', this.w('modular.latest_supported_selection')], ...choices], value => this.setOption(key, value))}${status ? html`<p class="muted">${status}</p>` : ''}${model.error && allowed && key === 'round' ? html`<button @click=${() => this.archive.retry(model.requests)}>${this.w('modular.retry_archive')}</button>` : ''}`;
          }
        }
        if (module.type === 'incidents' && (key === 'summary_sort' && module.options.content !== 'track_limits_summary' || ['order', 'presentation'].includes(key) && module.options.content === 'track_limits_summary')) return '';
        if (module.type === 'telemetry' && key === 'session_id') return '';
        if (module.type === 'telemetry' && key === 'selected') return this.telemetryPicker(module);
        if (module.type === 'race_control' && ['limit', 'order'].includes(key) && module.options.presentation === 'latest_message') return '';
        if (module.type === 'strategy' && key === 'presentation' && module.options.content !== 'stints') return '';
        if (module.type === 'strategy' && key === 'minimum_clean_laps' && !['stints', 'compound_comparison'].includes(module.options.content)) return '';
        if (module.type === 'strategy' && key === 'compounds' && ['teammates', 'pit_outcomes'].includes(module.options.content)) return '';
        if (['progression', 'lap_chart'].includes(module.type) && ['source_choice', 'source_list'].includes(option.type)) {
          const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
          const model = module.type === 'lap_chart' ? lapChartModel(this.hass, entry, module) : progressionModel(this.hass, entry, module);
          if (option.type === 'source_list') {
            const choices = model.allSeries.map(item => [item.id, item.name]);
            for (const id of value) if (!choices.some(([key]) => key === id)) choices.push([id, `${id} · ${this.w('modular.saved_selection')}`]);
            return html`<p>${title}</p>${choices.map(([id, name]) => this.check(name, value.includes(id), enabled => this.setOption(key, enabled ? [...value, id] : value.filter(item => item !== id))))}`;
          }
          const choices = model.allRounds.map(item => [String(item.id), `${item.id} · ${item.race_name ?? ''}`]);
          if (value && !choices.some(([id]) => id === value)) choices.push([value, `${value} · ${this.w('modular.saved_selection')}`]);
          return this.select(title, value, [['', this.w('modular.all_available_rounds')], ...choices], value => this.setOption(key, value));
        }
        if (option.type === 'source_choice') {
          if (!['race_results', 'sprint_results'].includes(module.options.content)) return '';
          const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
          const choices = resultChoices(this.hass, entry, module).map(item => [item.id, `${item.id} · ${item.name}`]);
          if (value && !choices.some(([id]) => id === value)) choices.unshift([value, `${value} · ${this.w('modular.saved_selection')}`]);
          return this.select(title, value, [['', this.w('modular.latest_published')], ...choices], value => this.setOption(key, value));
        }
        if (option.type === 'enum') return this.select(title, value, option.values.map(value => [value, this.optionName(value)]), value => this.setOption(key, value));
        if (option.type === 'boolean') return this.check(title, value, value => this.setOption(key, value));
        if (option.type === 'list') return html`<p>${title}</p>${option.values.map(item => this.check(this.optionName(item), value.includes(item), enabled => this.setOption(key, enabled ? [...value, item] : value.filter(key => key !== item))))}`;
        return this.input(title, value, value => this.setOption(key, value), option.type === 'integer' ? 'number' : 'text');
      })}
      ${this.select(this.w('modular.when_data_is_unavailable'), module.unavailable, [['explain', this.w('modular.show_explanation')], ['retain', this.w('modular.keep_saved_data')], ['hide', this.w('modular.hide_module')]], value => this.setModule('unavailable', value))}
      ${this.selectionPicker(this.w('modular.session_selection'), module.selection, value => this.setModule('selection', value), { inherit: true, archive: archiveState })}
      <p>${this.w('modular.show_in_session_phases')}</p>${[['before', 'Before', 'Före'], ['active', 'Active or interrupted', 'Pågående eller avbruten'], ['finished', 'Finished', 'Avslutad'], ['unknown', 'Unknown', 'Okänd']].map(([phase, en, sv]) => this.check(this.w(en, sv), module.when.includes(phase), enabled => this.setModule('when', enabled ? [...module.when, phase] : module.when.filter(item => item !== phase))))}
      ${moduleFocusKinds(module).length ? html`${this.select(this.w('modular.driver_and_team_selection'), module.focus_mode, [['inherit', this.w('modular.follow_card_focus')], ['independent', this.w('modular.use_own_selection')]], value => this.setModule('focus_mode', value))}${module.focus_mode === 'independent' ? html`<p class="muted">${this.w('modular.empty_driver_or_team_filters_include_everyone_card_and_group_focus_do_not_change')}</p>` : ''}` : ''}
      ${(moduleFocusKinds(module).includes('driver')) ? this.focusPicker('driver', this.w('modular.pinned_driver'), module.driver, value => this.setModule('driver', value), module.focus_mode !== 'independent') : ''}
      ${(moduleFocusKinds(module).includes('team')) ? this.focusPicker('team', this.w('modular.pinned_team'), module.team, value => this.setModule('team', value), module.focus_mode !== 'independent') : ''}
      <button @click=${() => this.setModule('options', Object.fromEntries(Object.entries(module.options).filter(([key]) => !Object.hasOwn(definition?.options ?? {}, key))))}>${this.w('modular.reset_module_options')}</button></details>
      ${this.visibilitySettings(module)}
      <div class="buttons"><button @click=${() => this.updateConfig(config => configAPI.duplicateModule(config, module.id))}>${this.w('modular.duplicate_module')}</button>
      <button @click=${() => { const index = this.config.modules.findIndex(item => item.id === module.id); this.updateConfig(config => { config.modules = config.modules.filter(item => item.id !== module.id); return config; }); this.selected = this.config.modules[Math.min(index, this.config.modules.length - 1)]?.id ?? ''; }}>${this.w('modular.remove_module')}</button></div>
    </section>`;
  }
  optionName(value) {
    const calendarLabels = { none: ['None', 'Ingen'], round: ['Round', 'Rond'], circuit: ['Circuit', 'Bana'], location: ['Location', 'Plats'], show: ['Show', 'Visa'], dim: ['Mark past starts', 'Markera passerade starter'], label: ['Show label', 'Visa markering'] };
    if (calendarLabels[value]) return this.w(...calendarLabels[value]);
    if (value === 'time_s') return this.w('modular.time_from_lap_start_s');
    if (value === 'distance') return this.w('modular.estimated_distance_m');
    const names = { automatic_conditions: ['Automatic current weather', 'Automatiskt aktuellt väder'], classification: ['Published classification', 'Publicerat resultat'], lap_position: ['Positions at lap completion', 'Placeringar vid avslutat varv'], lap_time: ['Lap time', 'Varvtid'], lap_change: ['Change from previous lap', 'Skillnad mot föregående varv'], track_limits_summary: ['Track limits by driver', 'Track limits per förare'], track_limit_deletions: ['Most deleted times first', 'Flest strukna tider först'], weather_overview: ['Current weather and race rain risk', 'Aktuellt väder och regnrisk inför race'], current_conditions: ['Current circuit weather', 'Aktuellt väder vid banan'], race_forecast: ['Forecast near race start', 'Prognos nära racestart'], track_conditions: ['Track weather observations', 'Väderobservationer från banan'], metrics: ['Large metrics', 'Stora mätvärden'], compact_list: ['Compact list', 'Kompakt lista'], latest_message: ['Latest matching message', 'Senaste matchande meddelande'], include: ['Include', 'Ta med'], hide: ['Hide', 'Dölj'], teammates: ['Compare teammates', 'Jämför teamkamrater'], crossover: ['Compound pace crossover', 'Blandningarnas temposkärning'], pit_outcomes: ['Observed pit-cycle outcomes', 'Observerade utfall av depåcykler'], active_battles: ['Current battles', 'Pågående närkamper'], battle_history: ['Battle history', 'Närkampernas historik'], position_exchanges: ['Position exchanges', 'Positionsbyten'], battle_started: ['Battle started', 'Närkamp började'], battle_ended: ['Battle ended', 'Närkamp avslutades'], position_exchange: ['Position exchange', 'Positionsbyte'], likely_on_track_overtake: ['Likely on-track overtake', 'Trolig omkörning på banan'], code: ['Driver code', 'Förarkod'], number: ['Racing number', 'Startnummer'], highlight: ['Highlight selection', 'Markera urval'], filter: ['Show selection only', 'Visa endast urval'], source: ['Source orientation', 'Källans orientering'], raw: ['Original coordinates', 'Ursprungliga koordinater'], normal: ['Original', 'Ursprunglig'], flipped: ['Flipped', 'Vänd'], stints: ['Stint pace and quality', 'Stinttempo och kvalitet'], compound_comparison: ['Compare compounds', 'Jämför blandningar'], custom: ['Custom columns', 'Egna kolumner'], auto: ['Follow the session', 'Följ sessionen'], practice: ['Practice', 'Träning'], current: ['Current tyres', 'Aktuella däck'], statistics: ['Compound statistics', 'Statistik per blandning'], latest_stop: ['Latest stop per driver', 'Senaste stopp per förare'], all_stops: ['All recorded stops', 'Alla registrerade stopp'], investigations: ['Investigations and decisions', 'Utredningar och beslut'], track_limits: ['Track limits', 'Bangränser'], list: ['Event list', 'Händelselista'], SOFT: ['Soft', 'Mjuka'], MEDIUM: ['Medium', 'Medium'], HARD: ['Hard', 'Hårda'], INTERMEDIATE: ['Intermediate', 'Intermediate'], WET: ['Wet', 'Regndäck'], UNKNOWN: ['Unknown compound', 'Okänd blandning'], cumulative_points: ['Total points', 'Totala poäng'], points_per_round: ['Points per round', 'Poäng per deltävling'], wins_per_round: ['Wins per round', 'Vinster per deltävling'], chart: ['Chart with optional data table', 'Diagram med valbar datatabell'], table: ['Data table', 'Datatabell'], both: ['Chart and table', 'Diagram och tabell'], latest_race: ['Latest race', 'Senaste race'], race_results: ['Season race results', 'Säsongens raceresultat'], sprint_results: ['Season sprint results', 'Säsongens sprintresultat'], starting_grid: ['Starting grid', 'Startuppställning'], drivers: ['Drivers', 'Förare'], teams: ['Teams', 'Team'], weekend: ['Next weekend', 'Nästa tävlingshelg'], season: ['Whole season', 'Hela säsongen'], home: ['Home time', 'Hemmatid'], circuit: ['Circuit time', 'Bantid'], utc: ['UTC', 'UTC'], asc: ['Ascending', 'Stigande'], desc: ['Descending', 'Fallande'], coherent: ['Same lap', 'Samma varv'], latest: ['Latest sectors, with lap labels', 'Senaste sektorerna, med varvnummer'], newest: ['Newest first', 'Nyaste först'], oldest: ['Oldest first', 'Äldsta först'], practice_1: ['Practice 1', 'Träning 1'], practice_2: ['Practice 2', 'Träning 2'], practice_3: ['Practice 3', 'Träning 3'], qualifying: ['Qualifying', 'Kval'], sprint_qualifying: ['Sprint qualifying', 'Sprintkval'], sprint: ['Sprint', 'Sprint'], race: ['Race', 'Race'] };
    return names[value] ? this.w(...names[value]) : label(INCIDENT_SIGNALS[value] ?? FIELDS[value], this.language) || value;
  }
  actionSettings() {
    const keys = ['entity', 'tap_action', 'hold_action', 'double_tap_action'];
    const labels = { entity: this.w('modular.action_entity'), tap_action: this.w('modular.tap_action'), hold_action: this.w('modular.hold_action'), double_tap_action: this.w('modular.double_tap_action') };
    const schema = keys.map(name => ({ name, selector: name === 'entity' ? { entity: {} } : { ui_action: { default_action: name === 'tap_action' && this.config.entity ? 'more-info' : 'none' } } }));
    return html`<details><summary>${this.w('modular.card_actions')}</summary>
      <p class="muted">${this.w('modular.actions_belong_to_the_card_title_hold_and_double_tap_also_have_buttons_under')}</p>
      <ha-form .hass=${this.hass} .data=${Object.fromEntries(keys.filter(key => this.config[key] !== undefined).map(key => [key, this.config[key]]))}
        .schema=${schema} .computeLabel=${field => labels[field.name]} @value-changed=${event => {
          event.stopPropagation();
          const value = event.detail.value;
          this.updateConfig(config => { for (const key of keys) { if (value[key] === undefined) delete config[key]; else config[key] = value[key]; } return config; });
        }}></ha-form>
    </details>`;
  }
  appearanceSettings() {
    const appearance = this.config.appearance, accessibility = this.config.accessibility;
    const mode = appearance.mode === 'auto' ? this.hass?.themes?.darkMode === false ? 'light' : 'dark' : appearance.mode;
    const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
    const teams = accentTeams(this.hass, entry), teamOptions = teams.map(team => [team.name, team.name]);
    if (appearance.accent_team && !teams.some(team => team.name === appearance.accent_team)) teamOptions.unshift([appearance.accent_team, `${appearance.accent_team} · ${this.w('modular.saved_selection')}`]);
    const accent = cardAccent(appearance, teams, mode);
    return html`<details><summary>${this.w('modular.appearance')}</summary>
      ${this.select(this.w('modular.style'), appearance.style, [['f1', 'F1'], ['ha', 'Home Assistant'], ['minimal', this.w('modular.minimal')]], value => this.setGroup('appearance', 'style', value))}
      ${this.select(this.w('modular.theme'), appearance.mode, [['auto', this.w('modular.automatic')], ['light', this.w('modular.light')], ['dark', this.w('modular.dark')]], value => this.setGroup('appearance', 'mode', value))}
      ${this.select(this.w('modular.density'), appearance.density, [['compact', this.w('modular.compact')], ['comfortable', this.w('modular.normal')], ['spacious', this.w('modular.spacious')]], value => this.setGroup('appearance', 'density', value))}
      <details><summary>${this.w('modular.headings_and_surface')}</summary>
        ${this.select(this.w('modular.heading_font'), appearance.font, [['auto', this.w('modular.follow_style')], ['f1', this.w('modular.f1_inspired')], ['system', 'Home Assistant']], value => this.setGroup('appearance', 'font', value))}
        ${this.check(this.w('modular.show_card_title'), appearance.show_header, value => this.setGroup('appearance', 'show_header', value))}
        <p class="muted">${this.w('modular.driver_focus_reading_pause_and_configured_actions_stay_available_when_the_card_title_is')}</p>
        ${this.select(this.w('modular.surface'), appearance.surface, [['style', this.w('modular.follow_style')], ['framed', this.w('modular.defined_frame')], ['soft', this.w('modular.soft_corners_and_alternating_rows')], ['flat', this.w('modular.flat_without_a_frame')]], value => this.setGroup('appearance', 'surface', value))}
        ${this.select(this.w('modular.numerals'), appearance.numbers, [['tabular', this.w('modular.aligned_timing_numerals')], ['inherit', 'Home Assistant']], value => this.setGroup('appearance', 'numbers', value))}
      </details>
      <details><summary>${this.w('modular.colors_and_branding')}</summary>
        ${this.select(this.w('modular.decorative_accent'), appearance.accent_mode, [['style', this.w('modular.follow_style')], ['neutral', this.w('modular.neutral')], ['f1', 'F1'], ['team', this.w('modular.favorite_team')], ['custom', this.w('modular.custom_color')]], value => this.setGroup('appearance', 'accent_mode', value))}
        ${appearance.accent_mode === 'custom' ? this.input(this.w('modular.accent_color'), appearance.accent, value => this.setGroup('appearance', 'accent', value), 'color') : ''}
        ${appearance.accent_mode === 'team' ? html`${this.select(this.w('modular.accent_team'), appearance.accent_team, [['', this.w('modular.choose_a_team')], ...teamOptions], value => this.setGroup('appearance', 'accent_team', value))}${accent.missingTeamColor ? html`<p class="muted">${this.w('modular.team_color_is_unavailable_a_neutral_accent_is_used_until_the_integration_supplies_it')}</p>` : ''}` : ''}
        <p class="muted">${this.w('modular.the_accent_decorates_the_card_edge_it_does_not_change_timing_colors_flag_meanings')}</p>
        ${[['logos', 'Team logos', 'Teamloggor'], ['flags', 'Country flags', 'Landsflaggor'], ['team_colors', 'Team accents', 'Teamaccenter'], ['full_names', 'Full driver names', 'Fullständiga förarnamn']].map(([key, en, sv]) => this.check(this.w(en, sv), appearance[key], value => this.setGroup('appearance', key, value)))}
        ${appearance.logos ? html`${this.select(this.w('modular.logo_variant'), appearance.logo_style, [['auto', this.w('modular.automatic_aec0889a')], ['color', this.w('modular.color')], ['mono', this.w('modular.monochrome')], ['white', this.w('modular.white')]], value => this.setGroup('appearance', 'logo_style', value))}
          ${this.select(this.w('modular.logo_size'), appearance.logo_size, [['small', this.w('modular.small')], ['normal', this.w('modular.normal')], ['large', this.w('modular.large')]], value => this.setGroup('appearance', 'logo_size', value))}` : ''}
        ${this.select(this.w('modular.tyre_appearance'), appearance.tyre_style, [['ring', this.w('modular.colored_ring_and_letter')], ['image', this.w('modular.tyre_image_and_letter')], ['text', this.w('modular.compound_name')], ['both', this.w('modular.tyre_image_and_name')]], value => this.setGroup('appearance', 'tyre_style', value))}
      </details>
      <details><summary>${this.w('modular.custom_css_advanced')}</summary>
        <p class="muted">${this.w('modular.custom_css_applies_only_to_this_card_use_the_documented_f1_variables_and_parts')}</p>
        <label><span>${this.w('modular.custom_css')}</span><textarea aria-label=${this.w('modular.custom_css')} spellcheck="false" placeholder=${`ha-card {\n  --f1-card-radius: 20px;\n}`} .value=${this.config.styles ?? ''} @input=${event => this.updateConfig(config => { if (event.target.value.trim()) config.styles = event.target.value; else delete config.styles; return config; })}></textarea></label>
        <p class="muted">${this.w('modular.enter_css_without_a_styles_prefix_javascript_templates_imported_stylesheets_and_image_urls_are')}</p>
        <button ?disabled=${!this.config.styles} @click=${() => this.updateConfig(config => { delete config.styles; return config; })}>${this.w('modular.reset_custom_css')}</button>
      </details>
      <button @click=${() => this.updateConfig(config => ({ ...config, appearance: { ...configAPI.APPEARANCE, ...Object.fromEntries(Object.entries(config.appearance).filter(([key]) => !Object.hasOwn(configAPI.APPEARANCE, key))) } }))}>${this.w('modular.reset_appearance')}</button>
    </details><details><summary>${this.w('modular.accessibility_and_timing_colors')}</summary>
      <p class="muted">${this.w('modular.colors_always_have_a_shape_or_text_equivalent_yellow_means_a_recorded_time_not')}</p>
      ${this.check(this.w('modular.high_contrast'), accessibility.high_contrast, value => this.setGroup('accessibility', 'high_contrast', value))}
      ${this.select(this.w('modular.status_signals'), accessibility.signals, [['shape', this.w('modular.compact_shapes')], ['text', this.w('modular.text')], ['both', this.w('modular.shapes_and_text')]], value => this.setGroup('accessibility', 'signals', value))}
      ${this.select(this.w('modular.motion'), accessibility.motion, [['system', this.w('modular.follow_device_preference')], ['reduced', this.w('modular.reduce_motion')]], value => this.setGroup('accessibility', 'motion', value))}
      ${this.check(this.w('modular.announce_reading_pause_to_screen_readers'), accessibility.announce, value => this.setGroup('accessibility', 'announce', value))}
      <details><summary>${this.w('modular.timing_palette')}</summary>
        ${Object.entries(PALETTES[mode]).map(([key, fallback]) => { const title = label(SIGNALS[key], this.language); return html`<div class="palette-row">${this.input(title, appearance.palette[key] ?? fallback, value => this.setGroup('appearance', 'palette', { ...appearance.palette, [key]: value }), 'color')}<button aria-label=${`${this.w('modular.reset')} ${title}`} ?disabled=${!Object.hasOwn(appearance.palette, key)} @click=${() => { const palette = { ...appearance.palette }; delete palette[key]; this.setGroup('appearance', 'palette', palette); }}>↺</button></div>`; })}
        <button @click=${() => this.setGroup('appearance', 'palette', {})}>${this.w('modular.use_automatic_timing_colors')}</button>
      </details>
    </details>`;
  }
  render() {
    if (!this.config) return html``;
    return html`<div class="toolbar"><h2>F1 Sensor</h2><button ?disabled=${!this.history.length} @click=${this.undo}>${this.w('modular.undo')}</button></div>
      ${this.error ? html`<p class="danger" role="alert">${this.error}</p>` : ''}
      <div class="builder"><div class="form">
        <details class="starter" ?open=${!this.config.modules.length}><summary>${this.w('modular.start_from_a_template')}</summary>
          <p class="scope-description">${this.w('modular.templates_replace_the_module_content_but_keep_the_card_appearance')}</p>
          <div class="presets">${Object.entries(PRESETS).map(([id, preset]) => html`<button @click=${() => { if (this.config.modules.length) this.pendingPreset = id; else { this.updateConfig(config => configAPI.applyPreset(config, id)); this.selected = this.config.modules[0]?.id ?? ''; } }}>${label(preset, this.language)}<small>${preset.modules.map(module => moduleTitle(module, this.language)).join(' · ') || this.w('modular.choose_your_first_module')}</small></button>`)}</div>
          ${this.pendingPreset ? html`<div class="notice" role="region" aria-label=${this.w('modular.replace_content')}><p>${this.w('modular.current_modules_will_be_replaced_appearance_is_kept')}</p><p>${this.config.modules.map(module => moduleTitle(module, this.language)).join(', ')} → ${label(PRESETS[this.pendingPreset], this.language)}</p><div class="buttons"><button @click=${() => { this.updateConfig(config => configAPI.applyPreset(config, this.pendingPreset)); this.selected = this.config.modules[0]?.id ?? ''; this.pendingPreset = ''; }}>${this.w('modular.replace_content')}</button><button @click=${() => { this.pendingPreset = ''; }}>${this.w('modular.cancel')}</button></div></div>` : ''}
        </details>
        <section class="scope-panel card-scope" data-scope="card" aria-labelledby="card-settings-title"><div class="scope-heading"><span class="scope-badge" aria-hidden="true">${this.w('modular.card')}</span><div><p class="scope-kicker">${this.w('modular.whole_card')}</p><h3 id="card-settings-title">${this.w('modular.card_settings')}</h3><p class="scope-description">${this.w('modular.these_settings_apply_to_every_module_in_this_card')}</p></div></div>
          ${this.input(this.w('modular.card_title'), this.config.title, value => this.updateConfig(config => ({ ...config, title: value })))}
          ${this.entries.length > 1 || this.config.f1_entry_id ? this.select(this.w('modular.f1_sensor_installation'), this.config.f1_entry_id, [['', this.w('modular.automatic_one_installation')], ...this.entries.map(entry => [entry.entry_id, entry.title])], value => this.updateConfig(config => ({ ...config, f1_entry_id: value }))) : ''}
          <details><summary>${this.w('modular.layout_and_shared_focus')}</summary>
          ${this.select(this.w('modular.layout'), this.config.layout, [['stack', this.w('modular.stacked_modules')], ['tabs', this.w('modular.tabs')], ['columns', this.w('modular.columns')]], value => this.updateConfig(config => ({ ...config, layout: value })))}
          ${this.config.layout === 'columns' ? html`
            ${this.select(this.w('modular.maximum_columns'), String(this.config.columns), [2, 3, 4].map(count => [String(count), String(count)]), value => this.updateConfig(config => ({ ...config, columns: Number(value) })))}
            <p class="muted">${this.w('modular.modules_flow_in_list_order_left_to_right_then_onto_the_next_row_fewer')}</p>
            <p class="muted">${this.w('modular.for_a_wide_card_in_home_assistant_sections_increase_the_section_width_and_enable')}</p>
          ` : ''}
          ${this.focusPicker('driver', this.w('modular.default_driver'), this.config.context.driver, value => this.setGroup('context', 'driver', value))}
          ${this.focusPicker('team', this.w('modular.default_team'), this.config.context.team, value => this.setGroup('context', 'team', value))}
          ${this.selectionPicker(this.w('modular.card_session'), this.config.context.selection, value => this.setGroup('context', 'selection', value))}
          ${this.check(this.w('modular.share_driver_focus_with_a_named_group'), this.config.context.scope === 'group', value => this.updateConfig(config => ({ ...config, context: { ...config.context, scope: value ? 'group' : 'local', group: config.context.group || 'F1' } })))}
          ${this.config.context.scope === 'group' ? this.input(this.w('modular.group_name'), this.config.context.group, value => this.setGroup('context', 'group', value)) : ''}
          ${this.config.context.scope === 'group' ? this.check(this.w('modular.share_temporary_session_selection'), this.config.context.share.includes('selection'), enabled => this.setGroup('context', 'share', enabled ? [...this.config.context.share, 'selection'] : this.config.context.share.filter(item => item !== 'selection'))) : ''}
          <p class="muted">${this.w('modular.groups_share_selected_display_context_in_this_dashboard_view_pinned_cards_keep_their_own')}</p>
          ${this.check(this.w('modular.show_driver_focus_menu'), this.config.context.show_focus_control, value => this.setGroup('context', 'show_focus_control', value))}
          ${this.check(this.w('modular.show_freeze_view_button'), this.config.context.show_freeze_control, value => this.setGroup('context', 'show_freeze_control', value))}
          ${this.check(this.w('modular.show_live_delay_and_global_spoiler_controls'), this.config.context.viewing_controls, value => this.setGroup('context', 'viewing_controls', value))}
          <p class="muted">${this.w('modular.optional_viewing_controls_change_integration_settings_live_delay_affects_this_installation_and_its_automations')}</p>
          ${this.check(this.w('modular.always_hide_spoilers_in_this_card'), this.config.context.spoilers === 'hide', value => this.setGroup('context', 'spoilers', value ? 'hide' : 'inherit'))}
          </details>
          ${this.appearanceSettings()}${this.actionSettings()}${this.migrationSettings()}
          <details><summary>${this.w('modular.reusable_templates')}</summary><p class="muted">${this.w('modular.export_a_named_template_or_paste_open_one_to_review_it_before_replacing_this')}</p>
          ${this.input(this.w('modular.template_name'), this.templateName, value => { this.templateName = value; })}
          <label><span>${this.w('modular.template_json')}</span><textarea .value=${this.transfer} @input=${event => { this.transfer = event.target.value; }}></textarea></label>
          <div class="buttons"><button @click=${() => { try { this.transfer = configAPI.exportTemplate(this.config, this.templateName); this.error = ''; } catch (error) { this.error = error.message; } }}>${this.w('modular.export_template')}</button><button @click=${() => this.reviewTemplate(this.transfer)}>${this.w('modular.review_template')}</button><label class="file-button"><span>${this.w('modular.open_template_file')}</span><input type="file" accept="application/json,.json" @change=${event => this.readTemplateFile(event)}></label></div>
          ${this.pendingTemplate ? html`<div class="notice" role="region" aria-label=${this.w('modular.template_review')}><p><strong>${this.pendingTemplate.name}</strong></p><p>${this.w('modular.current_content')}: ${this.config.modules.map(module => moduleTitle(module, this.language)).join(', ') || '—'}<br>${this.w('modular.template_content')}: ${this.pendingTemplate.card.modules.map(module => moduleTitle(module, this.language)).join(', ') || '—'}</p>
            ${this.pendingTemplate.card.f1_entry_id && !this.entries.some(entry => entry.entry_id === this.pendingTemplate.card.f1_entry_id) ? html`<p>${this.w('modular.the_saved_installation_is_not_available_here_choose_the_installation_this_copy_should_use')}</p>${this.select(this.w('modular.f1_sensor_installation_for_template'), this.templateEntry, [['', this.w('modular.choose')], ...this.entries.map(entry => [entry.entry_id, entry.title])], value => { this.templateEntry = value; })}` : ''}
            <div class="buttons"><button @click=${() => { this.pendingTemplate = null; this.templateEntry = ''; }}>${this.w('modular.cancel')}</button><button ?disabled=${Boolean(this.pendingTemplate.card.f1_entry_id && !this.entries.some(entry => entry.entry_id === this.pendingTemplate.card.f1_entry_id) && !this.templateEntry)} @click=${() => this.applyTemplate()}>${this.w('modular.apply_template')}</button></div></div>` : ''}
          </details><details><summary>${this.w('modular.advanced_card_json')}</summary><p class="muted">${this.w('modular.export_or_import_the_raw_card_configuration_import_applies_immediately_and_can_be_undone')}</p>
          <div class="buttons"><button @click=${() => { this.transfer = configAPI.exportConfig(this.config); }}>${this.w('modular.export_card_json')}</button><button @click=${() => this.updateConfig(() => configAPI.importConfig(this.transfer))}>${this.w('modular.import_card_json')}</button></div>
          </details>
        </section>
        <section class="scope-panel module-scope" data-scope="module" aria-labelledby="modules-title"><div class="scope-heading"><span class="scope-badge" aria-hidden="true">${this.w('modular.module')}</span><div><p class="scope-kicker">${this.w('modular.selected_content')}</p><h3 id="modules-title">${this.w('modular.modules')}</h3><p class="scope-description">${this.w('modular.choose_a_module_to_edit_only_its_content_behavior_and_appearance')}</p></div></div>
          <button aria-expanded=${String(Boolean(this.arranging))} aria-controls="module-arrangement" @click=${() => { this.arranging = !this.arranging; }}>${this.w('modular.arrange_modules')}</button>
          ${this.arranging ? html`<div id="module-arrangement"><f1-module-arranger .config=${this.config} .language=${this.language} .selected=${this.selected} @module-selected=${event => { event.stopPropagation(); this.selected = event.detail.id; }} @arrangement-changed=${event => { event.stopPropagation(); this.updateConfig(config => ({ ...config, ...event.detail })); }}></f1-module-arranger></div>` : ''}
          <ol class="module-list">${repeat(this.config.modules, module => module.id, (module, index) => html`<li class="module-row" data-selected=${String(this.selected === module.id)}><button class="select-module" data-module=${module.id} aria-label=${`${index + 1}. ${moduleTitle(module, this.language)}`} aria-pressed=${String(this.selected === module.id)} @click=${() => { this.selected = module.id; }}><span class="module-index">${String(index + 1).padStart(2, '0')}</span><span class="module-name">${moduleTitle(module, this.language)}${this.config.layout === 'columns' ? html`<small class="module-width">${this.columnWidth(module.column_span)}</small>` : ''}</span></button><button ?disabled=${index === 0} aria-label=${`${this.w('modular.move_up')} ${moduleTitle(module, this.language)}`} @click=${() => this.move(module.id, -1)}>↑</button><button ?disabled=${index === this.config.modules.length - 1} aria-label=${`${this.w('modular.move_down')} ${moduleTitle(module, this.language)}`} @click=${() => this.move(module.id, 1)}>↓</button></li>`)}</ol>
          ${this.select(this.w('modular.add_module'), '', [['', this.w('modular.choose_content')], ...Object.values(MODULES).map(module => [module.id, label(module, this.language)])], value => { if (!value) return; const module = configAPI.makeModule(value, this.config.modules); this.updateConfig(config => ({ ...config, modules: [...config.modules, module] })); this.selected = module.id; })}
          ${this.moduleSettings()}
        </section>
      </div></div>`;
  }
}
if (!customElements.get('f1-sensor-card-editor')) customElements.define('f1-sensor-card-editor', F1SensorCardEditor);
