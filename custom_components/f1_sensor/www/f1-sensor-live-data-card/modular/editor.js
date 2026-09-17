const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, css, repeat }, configAPI, { MODULES, PRESETS, FIELDS, defaultFields, fieldDefinition, moduleFields, timingFields, INCIDENT_SIGNALS, label, moduleTitle, moduleFocusKinds }, { sharedStyles, words }, { makeDemo }, { watchEntries, HistoryResources }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./config.js'), load('./catalog.js'), load('./view.js'), load('./demo.js'), load('./connection.js'),
]);
await load('./card.js');
const { source, array, lapChartModel, spoilerState, accentTeams } = await load('./data.js');
const { telemetryPlan, telemetryModel } = await load('./telemetry-data.js');
const { replayModel } = await load('./data.js');
const { cardAccent, PALETTES, SIGNALS } = await load('./semantics.js');
let telemetryLoading;
const { restoreLegacy, isLegacyConfig } = await load('./migration.js');
const { resultChoices, resultsModel, standingsModel, progressionModel, archiveModel, archivePlan } = await load('./season-data.js');

export class F1SensorCardEditor extends LitElement {
  static properties = { hass: { attribute: false }, config: { state: true }, selected: { state: true }, error: { state: true }, pendingPreset: { state: true }, scene: { state: true }, width: { state: true }, mobilePreview: { state: true }, entries: { state: true }, transfer: { state: true }, templateName: { state: true }, pendingTemplate: { state: true }, templateEntry: { state: true }, pendingRestore: { state: true }, originalTransfer: { state: true } };
  static styles = [sharedStyles, css`
    :host { container-type:inline-size; --f1-text:var(--primary-text-color,#e9edf3); --f1-muted:var(--secondary-text-color,#b9c1ce); --f1-surface:var(--card-background-color,#17202b); --f1-border:var(--divider-color,#637083); }
    .builder { display:grid; grid-template-columns:minmax(260px,1fr) minmax(300px,1fr); gap:24px; align-items:start; }
    .form { min-width:0; }
    .preview { min-width:0; overflow:auto; position:sticky; top:0; }
    .preview-shell { width:var(--preview-width,100%); margin:auto; }
    .toolbar,.module-row,.buttons { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .toolbar { justify-content:space-between; margin:12px 0; }
    .presets { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-bottom:16px; }
    .presets button { text-align:left; min-height:72px; overflow-wrap:anywhere; }
    .presets small { display:block; color:var(--f1-muted); font-size:.75em; }
    .module-list { list-style:none; margin:12px 0; padding:0; }
    .module-row { margin-bottom:8px; border:1px solid var(--f1-border); border-radius:8px; padding:4px; }
    .module-row .select-module { flex:1; text-align:left; min-width:120px; border:0; }
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
    details { border-top:1px solid var(--f1-border); padding:12px 0; }
    summary { cursor:pointer; min-height:44px; display:flex; align-items:center; font-weight:650; }
    .danger,.notice { border:1px solid currentColor; border-radius:8px; padding:12px; margin:12px 0; }
    .notice p { margin-bottom:8px; }
    .danger { color:var(--error-color,#ffb4b4); }
    .muted { font-size:.85em; }
    textarea { min-height:130px; font-family:monospace; font-size:.85em; }
    .mobile-toggle { display:none; }
    @container(max-width:760px) { .builder { grid-template-columns:1fr; } .preview { position:static; } .mobile-toggle { display:flex; } .builder[data-mobile=edit] .preview,.builder[data-mobile=preview] .form { display:none; } }
  `];
  constructor() { super(); this.archive = new HistoryResources(() => this.requestUpdate()); this.telemetry = new HistoryResources(() => this.requestUpdate()); this.history = []; this.entries = []; this.selected = ''; this.scene = 'race'; this.width = 'normal'; this.mobilePreview = false; this.error = ''; this.pendingPreset = ''; this.transfer = ''; this.templateName = ''; this.pendingTemplate = null; this.templateEntry = ''; }
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
    if (missing && !this.templateEntry) { this.error = this.w('Choose an F1 Sensor installation for this template.', 'Välj en F1 Sensor-installation för mallen.'); return; }
    const card = configAPI.copyConfig(this.pendingTemplate.card);
    if (missing) card.f1_entry_id = this.templateEntry;
    this.updateConfig(() => card);
    this.selected = card.modules[0]?.id ?? '';
    this.pendingTemplate = null; this.templateEntry = '';
  }
  async readTemplateFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 512_000) { this.error = this.w('Template file is larger than 512 KB.', 'Mallfilen är större än 512 kB.'); return; }
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
    return html`<details><summary>${this.w('Original card and recovery', 'Originalkort och återställning')}</summary>
      <p>${this.w('This card was converted from', 'Detta kort konverterades från')} <code>${this.config.migration.original.type}</code>.</p>
      <p>${this.w('The saved original includes settings that could not be converted. Restoring replaces the current modules and appearance. Save in Home Assistant to keep the restored card.', 'Det sparade originalet innehåller inställningar som inte kunde konverteras. Återställning ersätter nuvarande moduler och utseende. Spara i Home Assistant för att behålla det återställda kortet.')}</p>
      <div class="buttons"><button @click=${() => { this.originalTransfer = JSON.stringify(restoreLegacy(this.config), null, 2); }}>${this.w('Export original', 'Exportera original')}</button><button @click=${() => { this.pendingRestore = true; }}>${this.w('Restore original…', 'Återställ original…')}</button></div>
      ${this.originalTransfer ? html`<label><span>${this.w('Original configuration', 'Originalkonfiguration')}</span><textarea readonly .value=${this.originalTransfer}></textarea></label>` : ''}
      ${this.pendingRestore ? html`<div class="notice" role="status"><p>${this.w('Replace this converted card with its exact saved original?', 'Ersätta detta konverterade kort med dess exakt sparade original?')}</p><div class="buttons"><button @click=${() => { this.pendingRestore = false; }}>${this.w('Cancel restoration', 'Avbryt återställning')}</button><button @click=${() => this.restoreOriginal()}>${this.w('Restore original card', 'Återställ originalkort')}</button></div></div>` : ''}
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
    if (!entry) return html`<p class="muted">${this.w('Choose an F1 Sensor installation to select recorded laps.', 'Välj en F1 Sensor-installation för att välja registrerade varv.')}</p>`;
    if (spoilerState(this.hass, entry, this.config.context.spoilers) !== 'clear') return html`<p class="muted">${this.w('Spoiler protection hides the recorded laps.', 'Spoilerskyddet döljer registrerade varv.')}</p>`;
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
    if (this.telemetryError) return html`<p>${this.w('Reload the editor to load the lap picker.', 'Ladda om editorn för att hämta varvväljaren.')}</p>`;
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
    if (value && !options.some(([id]) => id === value)) options.unshift([value, `${value} · ${this.w('saved selection', 'sparat val')}`]);
    return this.select(title, value, [['', inherit ? this.w('Follow card focus', 'Följ kortets fokus') : this.w('All', 'Alla')], ...options], change);
  }
  selectionPicker(title, value, change, { inherit = false, archive = null } = {}) {
    const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
    const current = source(this.hass, entry, 'current_session'), replay = source(this.hass, entry, 'replay_status'), player = source(this.hass, entry, 'replay_player');
    const choices = [];
    if (inherit) choices.push([{ mode: 'inherit' }, this.w('Follow card session', 'Följ kortets session')]);
    for (const [sourceName, en, sv] of [['auto', 'Automatic source', 'Automatisk källa'], ['live', 'Follow live session', 'Följ livesession'], ['replay', 'Follow loaded replay', 'Följ laddad replay']]) choices.push([{ mode: 'follow', source: sourceName }, this.w(en, sv)]);
    const pinned = (sourceName, identity, name) => {
      const season = Number(identity.season), meetingKey = String(identity.meeting_key ?? ''), sessionKey = String(identity.session_key ?? '');
      if (Number.isInteger(season) && season >= 1950 && season <= 9999 && meetingKey && sessionKey) choices.push([{ mode: 'pinned', source: sourceName, season, meeting_key: meetingKey, session_key: sessionKey }, name]);
    };
    pinned('live', current.attributes, `${this.w('Pin current live session', 'Lås aktuell livesession')} · ${current.attributes.meeting_name ?? current.state ?? ''}`);
    const replayAttrs = { ...replay.attributes, ...player.attributes };
    pinned('replay', { season: replayAttrs.selected_session_year ?? replayAttrs.selected_year, meeting_key: replayAttrs.selected_meeting_key, session_key: replayAttrs.selected_session_key }, `${this.w('Pin loaded replay', 'Lås laddad replay')} · ${replayAttrs.selected_session ?? ''}`);
    if (archive?.context) pinned('archive', { season: archive.context.season, meeting_key: archive.context.meetingKey, session_key: archive.context.sessionKey }, `${this.w('Pin selected archive session', 'Lås vald arkivsession')} · ${archive.context.meeting} · ${archive.context.session}`);
    const serialized = JSON.stringify(value);
    if (!choices.some(([choice]) => JSON.stringify(choice) === serialized)) choices.push([value, this.w('Saved pinned session', 'Sparad låst session')]);
    return this.select(title, serialized, choices.map(([choice, label]) => [JSON.stringify(choice), label]), selected => change(JSON.parse(selected)));
  }
  move(id, offset) {
    this.updateConfig(config => configAPI.moveModule(config, id, offset));
    this.updateComplete.then(() => [...this.shadowRoot.querySelectorAll('[data-module]')].find(button => button.dataset.module === id)?.focus({ preventScroll: true }));
  }
  moduleSettings() {
    const saved = this.config.modules.find(module => module.id === this.selected), definition = MODULES[saved?.type];
    if (!saved) return html``;
    const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
    const protectedArchive = saved.type === 'archive' && spoilerState(this.hass, entry, this.config.context.spoilers) !== 'clear';
    const archiveState = saved.type === 'archive' ? archiveModel(saved, entry?.entry_id, query => protectedArchive ? { status: 'ready', data: null } : this.archive.read(query)) : null;
    const archiveFields = archiveState?.fields ?? null;
    const module = saved.type === 'timing' ? { ...saved, fields: timingFields(saved, this.scene) } : archiveFields ? { ...saved, fields: archiveFields } : saved;
    const available = moduleFields(module), fields = [...module.fields, ...available.filter(id => !module.fields.includes(id))];
    return html`<section aria-label=${this.w('Selected module', 'Vald modul')}><h3>${moduleTitle(module, this.language)}</h3>
      ${this.input(this.w('Module title', 'Modulrubrik'), module.title, value => this.setModule('title', value))}
      ${this.check(this.w('Show module', 'Visa modulen'), module.enabled, value => this.setModule('enabled', value))}
      <details><summary>${this.w('Module appearance', 'Modulens utseende')}</summary>
        ${this.check(this.w('Show module title', 'Visa modulrubrik'), module.show_header, value => this.setModule('show_header', value))}
        ${['timing', 'results', 'standings', 'archive', 'tyres', 'pit_stops', 'strategy', 'battles', 'timeline', 'incidents'].includes(module.type) ? html`${this.check(this.w('Show table header', 'Visa tabellhuvud'), module.show_table_header, value => this.setModule('show_table_header', value))}<p class="muted">${this.w('Hidden column labels remain available to screen readers. Chart data tables always keep their series labels visible.', 'Dolda kolumnnamn finns kvar för skärmläsare. Diagrammens datatabeller visar alltid namnen på serierna.')}</p>` : ''}
        <p class="muted">${this.w('Session details and status labels remain visible when the title is hidden.', 'Sessionsuppgifter och statusmarkeringar visas även när rubriken är dold.')}</p>
      </details>
      ${['timing', 'archive'].includes(module.type) && module.options.profile !== 'custom' && (module.type !== 'archive' || module.options.content === 'classification') ? html`<p class="muted">${this.w('This profile chooses the columns. Changing a checkbox or order switches to custom columns.', 'Profilen väljer kolumnerna. Ändra en kryssruta eller ordningen för att använda egna kolumner.')}</p>` : ''}
      <details open><summary>${this.w('Content and columns', 'Innehåll och kolumner')}</summary>${repeat(fields, id => id, id => html`<div class="field-row">
        ${this.check(label(fieldDefinition(module, id), this.language) || id, module.fields.includes(id), checked => this.setModule('fields', checked ? [...module.fields, id] : module.fields.filter(key => key !== id)))}
        ${module.fields.includes(id) ? html`<button aria-label=${`${this.w('Move up', 'Flytta upp')} ${label(fieldDefinition(module, id), this.language) || id}`} ?disabled=${module.fields.indexOf(id) === 0} @click=${() => { const fields = [...module.fields], index = fields.indexOf(id); [fields[index - 1], fields[index]] = [fields[index], fields[index - 1]]; this.setModule('fields', fields); }}>↑</button><button aria-label=${`${this.w('Move down', 'Flytta ned')} ${label(fieldDefinition(module, id), this.language) || id}`} ?disabled=${module.fields.indexOf(id) === module.fields.length - 1} @click=${() => { const fields = [...module.fields], index = fields.indexOf(id); [fields[index + 1], fields[index]] = [fields[index], fields[index + 1]]; this.setModule('fields', fields); }}>↓</button>` : ''}
        ${!available.includes(id) ? html`<small class="muted">${this.w('Saved · not used by this view', 'Sparat · används inte i denna vy')}</small>` : ''}
      </div>`)}</details>
      <details><summary>${this.w('Module options', 'Modulinställningar')}</summary>${Object.entries(definition?.options ?? {}).map(([key, option]) => {
        const title = module.type === 'incidents' && module.options.content === 'track_limits_summary' && key === 'rows' ? this.w('Maximum drivers', 'Max antal förare') : label(option, this.language), value = module.options[key];
        if (module.type === 'archive') {
          const chart = module.options.content !== 'classification';
          if (chart && ['profile', 'sort', 'direction', 'rows'].includes(key) || !chart && ['presentation', 'start_lap', 'end_lap', 'series_limit'].includes(key)) return '';
          if (['source_choice', 'source_list'].includes(option.type)) {
            const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
            const allowed = spoilerState(this.hass, entry, this.config.context.spoilers) === 'clear';
            const model = archiveModel(module, entry?.entry_id, query => allowed ? this.archive.read(query) : { status: 'ready', data: null });
            const choices = key === 'round' ? model.meetings.map(item => [String(item.round), `${item.round} · ${item.name}`]) : key === 'session_key' ? model.sessions.map(item => [item.session_key, item.name]) : model.allSeries.map(item => [item.id, item.name]);
            const selected = option.type === 'source_list' ? value : value ? [value] : [];
            for (const id of selected) if (!choices.some(([key]) => key === id)) choices.push([id, `${id} · ${this.w('saved selection', 'sparat val')}`]);
            const status = !allowed ? this.w('Spoiler protection hides the archive choices.', 'Spoilerskyddet döljer arkivvalen.') : model.error ? this.w('Archive unavailable. Try again.', 'Arkivet är inte tillgängligt. Försök igen.') : model.loading ? this.w('Loading archive…', 'Hämtar arkiv…') : null;
            return html`${option.type === 'source_list' ? html`<p>${title}</p>${choices.map(([id, name]) => this.check(name, value.includes(id), enabled => this.setOption(key, enabled ? [...value, id] : value.filter(item => item !== id))))}` : this.select(title, value, [['', this.w('Latest supported selection', 'Senaste urval med stöd')], ...choices], value => this.setOption(key, value))}${status ? html`<p class="muted">${status}</p>` : ''}${model.error && allowed && key === 'round' ? html`<button @click=${() => this.archive.retry(model.requests)}>${this.w('Retry archive', 'Försök hämta arkivet igen')}</button>` : ''}`;
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
            for (const id of value) if (!choices.some(([key]) => key === id)) choices.push([id, `${id} · ${this.w('saved selection', 'sparat val')}`]);
            return html`<p>${title}</p>${choices.map(([id, name]) => this.check(name, value.includes(id), enabled => this.setOption(key, enabled ? [...value, id] : value.filter(item => item !== id))))}`;
          }
          const choices = model.allRounds.map(item => [String(item.id), `${item.id} · ${item.race_name ?? ''}`]);
          if (value && !choices.some(([id]) => id === value)) choices.push([value, `${value} · ${this.w('saved selection', 'sparat val')}`]);
          return this.select(title, value, [['', this.w('All available rounds', 'Alla tillgängliga deltävlingar')], ...choices], value => this.setOption(key, value));
        }
        if (option.type === 'source_choice') {
          if (!['race_results', 'sprint_results'].includes(module.options.content)) return '';
          const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
          const choices = resultChoices(this.hass, entry, module).map(item => [item.id, `${item.id} · ${item.name}`]);
          if (value && !choices.some(([id]) => id === value)) choices.unshift([value, `${value} · ${this.w('saved selection', 'sparat val')}`]);
          return this.select(title, value, [['', this.w('Latest published', 'Senast publicerade')], ...choices], value => this.setOption(key, value));
        }
        if (option.type === 'enum') return this.select(title, value, option.values.map(value => [value, this.optionName(value)]), value => this.setOption(key, value));
        if (option.type === 'boolean') return this.check(title, value, value => this.setOption(key, value));
        if (option.type === 'list') return html`<p>${title}</p>${option.values.map(item => this.check(this.optionName(item), value.includes(item), enabled => this.setOption(key, enabled ? [...value, item] : value.filter(key => key !== item))))}`;
        return this.input(title, value, value => this.setOption(key, value), option.type === 'integer' ? 'number' : 'text');
      })}
      ${this.select(this.w('When data is unavailable', 'När data saknas'), module.unavailable, [['explain', this.w('Show explanation', 'Visa förklaring')], ['retain', this.w('Keep saved data', 'Behåll sparad data')], ['hide', this.w('Hide module', 'Dölj modulen')]], value => this.setModule('unavailable', value))}
      ${this.selectionPicker(this.w('Session selection', 'Sessionsurval'), module.selection, value => this.setModule('selection', value), { inherit: true, archive: archiveState })}
      <p>${this.w('Show in session phases', 'Visa i sessionsfaser')}</p>${[['before', 'Before', 'Före'], ['active', 'Active or interrupted', 'Pågående eller avbruten'], ['finished', 'Finished', 'Avslutad'], ['unknown', 'Unknown', 'Okänd']].map(([phase, en, sv]) => this.check(this.w(en, sv), module.when.includes(phase), enabled => this.setModule('when', enabled ? [...module.when, phase] : module.when.filter(item => item !== phase))))}
      ${moduleFocusKinds(module).length ? html`${this.select(this.w('Driver and team selection', 'Förar- och teamurval'), module.focus_mode, [['inherit', this.w('Follow card focus', 'Följ kortets fokus')], ['independent', this.w('Use own selection', 'Använd eget urval')]], value => this.setModule('focus_mode', value))}${module.focus_mode === 'independent' ? html`<p class="muted">${this.w('Empty driver or team filters include everyone. Card and group focus do not change this module; other filters still apply.', 'Tomma förar- eller teamfilter omfattar alla. Kortets och gruppens fokus ändrar inte denna modul; övriga filter gäller fortfarande.')}</p>` : ''}` : ''}
      ${(moduleFocusKinds(module).includes('driver')) ? this.focusPicker('driver', this.w('Pinned driver', 'Låst förare'), module.driver, value => this.setModule('driver', value), module.focus_mode !== 'independent') : ''}
      ${(moduleFocusKinds(module).includes('team')) ? this.focusPicker('team', this.w('Pinned team', 'Låst team'), module.team, value => this.setModule('team', value), module.focus_mode !== 'independent') : ''}
      <button @click=${() => this.setModule('options', Object.fromEntries(Object.entries(module.options).filter(([key]) => !Object.hasOwn(definition?.options ?? {}, key))))}>${this.w('Reset module options', 'Återställ modulinställningar')}</button></details>
      <div class="buttons"><button @click=${() => this.updateConfig(config => configAPI.duplicateModule(config, module.id))}>${this.w('Duplicate module', 'Duplicera modulen')}</button>
      <button @click=${() => { const index = this.config.modules.findIndex(item => item.id === module.id); this.updateConfig(config => { config.modules = config.modules.filter(item => item.id !== module.id); return config; }); this.selected = this.config.modules[Math.min(index, this.config.modules.length - 1)]?.id ?? ''; }}>${this.w('Remove module', 'Ta bort modulen')}</button></div>
    </section>`;
  }
  optionName(value) {
    const calendarLabels = { none: ['None', 'Ingen'], round: ['Round', 'Rond'], circuit: ['Circuit', 'Bana'], location: ['Location', 'Plats'], show: ['Show', 'Visa'], dim: ['Mark past starts', 'Markera passerade starter'], label: ['Show label', 'Visa markering'] };
    if (calendarLabels[value]) return this.w(...calendarLabels[value]);
    if (value === 'time_s') return this.w('Time from lap start (s)', 'Tid från varvstart (s)');
    if (value === 'distance') return this.w('Estimated distance (m)', 'Uppskattat avstånd (m)');
    const names = { automatic_conditions: ['Automatic current weather', 'Automatiskt aktuellt väder'], classification: ['Published classification', 'Publicerat resultat'], lap_position: ['Positions at lap completion', 'Placeringar vid avslutat varv'], lap_time: ['Lap time', 'Varvtid'], lap_change: ['Change from previous lap', 'Skillnad mot föregående varv'], track_limits_summary: ['Track limits by driver', 'Track limits per förare'], track_limit_deletions: ['Most deleted times first', 'Flest strukna tider först'], weather_overview: ['Current weather and race rain risk', 'Aktuellt väder och regnrisk inför race'], current_conditions: ['Current circuit weather', 'Aktuellt väder vid banan'], race_forecast: ['Forecast near race start', 'Prognos nära racestart'], track_conditions: ['Track weather observations', 'Väderobservationer från banan'], metrics: ['Large metrics', 'Stora mätvärden'], compact_list: ['Compact list', 'Kompakt lista'], latest_message: ['Latest matching message', 'Senaste matchande meddelande'], include: ['Include', 'Ta med'], hide: ['Hide', 'Dölj'], teammates: ['Compare teammates', 'Jämför teamkamrater'], crossover: ['Compound pace crossover', 'Blandningarnas temposkärning'], pit_outcomes: ['Observed pit-cycle outcomes', 'Observerade utfall av depåcykler'], active_battles: ['Current battles', 'Pågående närkamper'], battle_history: ['Battle history', 'Närkampernas historik'], position_exchanges: ['Position exchanges', 'Positionsbyten'], battle_started: ['Battle started', 'Närkamp började'], battle_ended: ['Battle ended', 'Närkamp avslutades'], position_exchange: ['Position exchange', 'Positionsbyte'], likely_on_track_overtake: ['Likely on-track overtake', 'Trolig omkörning på banan'], code: ['Driver code', 'Förarkod'], number: ['Racing number', 'Startnummer'], highlight: ['Highlight selection', 'Markera urval'], filter: ['Show selection only', 'Visa endast urval'], source: ['Source orientation', 'Källans orientering'], raw: ['Original coordinates', 'Ursprungliga koordinater'], normal: ['Original', 'Ursprunglig'], flipped: ['Flipped', 'Vänd'], stints: ['Stint pace and quality', 'Stinttempo och kvalitet'], compound_comparison: ['Compare compounds', 'Jämför blandningar'], custom: ['Custom columns', 'Egna kolumner'], auto: ['Follow the session', 'Följ sessionen'], practice: ['Practice', 'Träning'], current: ['Current tyres', 'Aktuella däck'], statistics: ['Compound statistics', 'Statistik per blandning'], latest_stop: ['Latest stop per driver', 'Senaste stopp per förare'], all_stops: ['All recorded stops', 'Alla registrerade stopp'], investigations: ['Investigations and decisions', 'Utredningar och beslut'], track_limits: ['Track limits', 'Bangränser'], list: ['Event list', 'Händelselista'], SOFT: ['Soft', 'Mjuka'], MEDIUM: ['Medium', 'Medium'], HARD: ['Hard', 'Hårda'], INTERMEDIATE: ['Intermediate', 'Intermediate'], WET: ['Wet', 'Regndäck'], UNKNOWN: ['Unknown compound', 'Okänd blandning'], cumulative_points: ['Total points', 'Totala poäng'], points_per_round: ['Points per round', 'Poäng per deltävling'], wins_per_round: ['Wins per round', 'Vinster per deltävling'], chart: ['Chart with optional data table', 'Diagram med valbar datatabell'], table: ['Data table', 'Datatabell'], both: ['Chart and table', 'Diagram och tabell'], latest_race: ['Latest race', 'Senaste race'], race_results: ['Season race results', 'Säsongens raceresultat'], sprint_results: ['Season sprint results', 'Säsongens sprintresultat'], starting_grid: ['Starting grid', 'Startuppställning'], drivers: ['Drivers', 'Förare'], teams: ['Teams', 'Team'], weekend: ['Next weekend', 'Nästa tävlingshelg'], season: ['Whole season', 'Hela säsongen'], home: ['Home time', 'Hemmatid'], circuit: ['Circuit time', 'Bantid'], utc: ['UTC', 'UTC'], asc: ['Ascending', 'Stigande'], desc: ['Descending', 'Fallande'], coherent: ['Same lap', 'Samma varv'], latest: ['Latest sectors, with lap labels', 'Senaste sektorerna, med varvnummer'], newest: ['Newest first', 'Nyaste först'], oldest: ['Oldest first', 'Äldsta först'], practice_1: ['Practice 1', 'Träning 1'], practice_2: ['Practice 2', 'Träning 2'], practice_3: ['Practice 3', 'Träning 3'], qualifying: ['Qualifying', 'Kval'], sprint_qualifying: ['Sprint qualifying', 'Sprintkval'], sprint: ['Sprint', 'Sprint'], race: ['Race', 'Race'] };
    return names[value] ? this.w(...names[value]) : label(INCIDENT_SIGNALS[value] ?? FIELDS[value], this.language) || value;
  }
  actionSettings() {
    const keys = ['entity', 'tap_action', 'hold_action', 'double_tap_action'];
    const labels = { entity: this.w('Action entity', 'Åtgärdens entitet'), tap_action: this.w('Tap action', 'Åtgärd vid tryck'), hold_action: this.w('Hold action', 'Åtgärd vid långtryck'), double_tap_action: this.w('Double tap action', 'Åtgärd vid dubbeltryck') };
    const schema = keys.map(name => ({ name, selector: name === 'entity' ? { entity: {} } : { ui_action: { default_action: name === 'tap_action' && this.config.entity ? 'more-info' : 'none' } } }));
    return html`<details><summary>${this.w('Card actions', 'Kortåtgärder')}</summary>
      <p class="muted">${this.w('Actions belong to the card title. Hold and double tap also have buttons under Card actions; when the title is hidden, tap has a button there too. Preview never runs actions.', 'Åtgärder hör till kortrubriken. Långtryck och dubbeltryck har även knappar under Kortåtgärder; när rubriken är dold får tryck också en knapp där. Förhandsvisningen utför aldrig åtgärder.')}</p>
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
    if (appearance.accent_team && !teams.some(team => team.name === appearance.accent_team)) teamOptions.unshift([appearance.accent_team, `${appearance.accent_team} · ${this.w('saved selection', 'sparat val')}`]);
    const accent = cardAccent(appearance, teams, mode);
    return html`<details><summary>${this.w('Appearance', 'Utseende')}</summary>
      ${this.select(this.w('Style', 'Stil'), appearance.style, [['f1', 'F1'], ['ha', 'Home Assistant'], ['minimal', this.w('Minimal', 'Avskalad')]], value => this.setGroup('appearance', 'style', value))}
      ${this.select(this.w('Theme', 'Tema'), appearance.mode, [['auto', this.w('Automatic', 'Automatiskt')], ['light', this.w('Light', 'Ljust')], ['dark', this.w('Dark', 'Mörkt')]], value => this.setGroup('appearance', 'mode', value))}
      ${this.select(this.w('Density', 'Täthet'), appearance.density, [['compact', this.w('Compact', 'Kompakt')], ['comfortable', this.w('Normal', 'Normal')], ['spacious', this.w('Spacious', 'Luftig')]], value => this.setGroup('appearance', 'density', value))}
      <details><summary>${this.w('Headings and surface', 'Rubriker och yta')}</summary>
        ${this.select(this.w('Heading font', 'Rubriktypsnitt'), appearance.font, [['auto', this.w('Follow style', 'Följ stil')], ['f1', this.w('F1 inspired', 'F1-inspirerat')], ['system', 'Home Assistant']], value => this.setGroup('appearance', 'font', value))}
        ${this.check(this.w('Show card title', 'Visa kortrubrik'), appearance.show_header, value => this.setGroup('appearance', 'show_header', value))}
        <p class="muted">${this.w('Driver focus, reading pause and configured actions stay available when the card title is hidden. Module titles are set per module.', 'Förarfokus, läspaus och valda åtgärder finns kvar när kortrubriken är dold. Modulrubriker väljs per modul.')}</p>
        ${this.select(this.w('Surface', 'Yta'), appearance.surface, [['style', this.w('Follow style', 'Följ stil')], ['framed', this.w('Defined frame', 'Tydlig ram')], ['soft', this.w('Soft corners and alternating rows', 'Mjuka hörn och varannan rad')], ['flat', this.w('Flat, without a frame', 'Rak, utan ram')]], value => this.setGroup('appearance', 'surface', value))}
        ${this.select(this.w('Numerals', 'Siffror'), appearance.numbers, [['tabular', this.w('Aligned timing numerals', 'Linjera tidernas siffror')], ['inherit', 'Home Assistant']], value => this.setGroup('appearance', 'numbers', value))}
      </details>
      <details><summary>${this.w('Colors and branding', 'Färger och loggor')}</summary>
        ${this.select(this.w('Decorative accent', 'Dekorativ accent'), appearance.accent_mode, [['style', this.w('Follow style', 'Följ stil')], ['neutral', this.w('Neutral', 'Neutral')], ['f1', 'F1'], ['team', this.w('Favorite team', 'Favoritteam')], ['custom', this.w('Custom color', 'Egen färg')]], value => this.setGroup('appearance', 'accent_mode', value))}
        ${appearance.accent_mode === 'custom' ? this.input(this.w('Accent color', 'Accentfärg'), appearance.accent, value => this.setGroup('appearance', 'accent', value), 'color') : ''}
        ${appearance.accent_mode === 'team' ? html`${this.select(this.w('Accent team', 'Accentteam'), appearance.accent_team, [['', this.w('Choose a team', 'Välj ett team')], ...teamOptions], value => this.setGroup('appearance', 'accent_team', value))}${accent.missingTeamColor ? html`<p class="muted">${this.w('Team color is unavailable. A neutral accent is used until the integration supplies it.', 'Teamfärgen saknas. En neutral accent används tills integrationen visar den.')}</p>` : ''}` : ''}
        <p class="muted">${this.w('The accent decorates the card edge. It does not change timing colors, flag meanings or driver selection.', 'Accenten dekorerar kortets kant. Den ändrar inte timingfärger, flaggornas betydelse eller förarurval.')}</p>
        ${[['logos', 'Team logos', 'Teamloggor'], ['flags', 'Country flags', 'Landsflaggor'], ['team_colors', 'Team accents', 'Teamaccenter'], ['full_names', 'Full driver names', 'Fullständiga förarnamn']].map(([key, en, sv]) => this.check(this.w(en, sv), appearance[key], value => this.setGroup('appearance', key, value)))}
        ${appearance.logos ? html`${this.select(this.w('Logo variant', 'Logotypvariant'), appearance.logo_style, [['auto', this.w('Automatic', 'Automatisk')], ['color', this.w('Color', 'Färg')], ['mono', this.w('Monochrome', 'Monokrom')], ['white', this.w('White', 'Vit')]], value => this.setGroup('appearance', 'logo_style', value))}
          ${this.select(this.w('Logo size', 'Logotypstorlek'), appearance.logo_size, [['small', this.w('Small', 'Liten')], ['normal', this.w('Normal', 'Normal')], ['large', this.w('Large', 'Stor')]], value => this.setGroup('appearance', 'logo_size', value))}` : ''}
        ${this.select(this.w('Tyre appearance', 'Däckens utseende'), appearance.tyre_style, [['ring', this.w('Colored ring and letter', 'Färgad ring och bokstav')], ['image', this.w('Tyre image and letter', 'Däckbild och bokstav')], ['text', this.w('Compound name', 'Compoundnamn')], ['both', this.w('Tyre image and name', 'Däckbild och namn')]], value => this.setGroup('appearance', 'tyre_style', value))}
      </details>
      <button @click=${() => this.updateConfig(config => ({ ...config, appearance: { ...configAPI.APPEARANCE, ...Object.fromEntries(Object.entries(config.appearance).filter(([key]) => !Object.hasOwn(configAPI.APPEARANCE, key))) } }))}>${this.w('Reset appearance', 'Återställ utseende')}</button>
    </details><details><summary>${this.w('Accessibility and timing colors', 'Tillgänglighet och timingfärger')}</summary>
      <p class="muted">${this.w('Colors always have a shape or text equivalent. Yellow means a recorded time, not a slower lap.', 'Färger har alltid en motsvarighet i form eller text. Gult betyder registrerad tid, inte ett långsammare varv.')}</p>
      ${this.check(this.w('High contrast', 'Hög kontrast'), accessibility.high_contrast, value => this.setGroup('accessibility', 'high_contrast', value))}
      ${this.select(this.w('Status signals', 'Statusmarkeringar'), accessibility.signals, [['shape', this.w('Compact shapes', 'Kompakta former')], ['text', this.w('Text', 'Text')], ['both', this.w('Shapes and text', 'Former och text')]], value => this.setGroup('accessibility', 'signals', value))}
      ${this.select(this.w('Motion', 'Rörelse'), accessibility.motion, [['system', this.w('Follow device preference', 'Följ enhetens inställning')], ['reduced', this.w('Reduce motion', 'Minska rörelse')]], value => this.setGroup('accessibility', 'motion', value))}
      ${this.check(this.w('Announce reading pause to screen readers', 'Meddela läspaus för skärmläsare'), accessibility.announce, value => this.setGroup('accessibility', 'announce', value))}
      <details><summary>${this.w('Timing palette', 'Timingpalett')}</summary>
        ${Object.entries(PALETTES[mode]).map(([key, fallback]) => { const title = label(SIGNALS[key], this.language); return html`<div class="palette-row">${this.input(title, appearance.palette[key] ?? fallback, value => this.setGroup('appearance', 'palette', { ...appearance.palette, [key]: value }), 'color')}<button aria-label=${`${this.w('Reset', 'Återställ')} ${title}`} ?disabled=${!Object.hasOwn(appearance.palette, key)} @click=${() => { const palette = { ...appearance.palette }; delete palette[key]; this.setGroup('appearance', 'palette', palette); }}>↺</button></div>`; })}
        <button @click=${() => this.setGroup('appearance', 'palette', {})}>${this.w('Use automatic timing colors', 'Använd automatiska timingfärger')}</button>
      </details>
    </details>`;
  }
  render() {
    if (!this.config) return html``;
    if (!this.previewNode) this.previewNode = document.createElement('f1-sensor-card');
    const demo = makeDemo(this.scene, this.language, this.config.f1_entry_id);
    demo.hass.themes.darkMode = this.hass?.themes?.darkMode ?? true;
    const entry = this.config.f1_entry_id ? this.entries.find(item => item.entry_id === this.config.f1_entry_id) : this.entries.length === 1 ? this.entries[0] : null;
    this.previewNode.previewData = { ...demo.preview, accentTeams: accentTeams(this.hass, entry) }; this.previewNode.hass = demo.hass; this.previewNode.setConfig(this.config);
    return html`<div class="toolbar"><h2>F1 Sensor</h2><button ?disabled=${!this.history.length} @click=${this.undo}>${this.w('Undo', 'Ångra')}</button></div>
      <div class="buttons mobile-toggle"><button aria-pressed=${String(!this.mobilePreview)} @click=${() => { this.mobilePreview = false; }}>${this.w('Edit', 'Redigera')}</button><button aria-pressed=${String(this.mobilePreview)} @click=${() => { this.mobilePreview = true; }}>${this.w('Preview', 'Förhandsvisa')}</button></div>
      ${this.error ? html`<p class="danger" role="alert">${this.error}</p>` : ''}
      <div class="builder" data-mobile=${this.mobilePreview ? 'preview' : 'edit'}><div class="form">
        <div class="presets">${Object.entries(PRESETS).map(([id, preset]) => html`<button @click=${() => { if (this.config.modules.length) this.pendingPreset = id; else { this.updateConfig(config => configAPI.applyPreset(config, id)); this.selected = this.config.modules[0]?.id ?? ''; } }}>${label(preset, this.language)}<small>${preset.modules.map(module => moduleTitle(module, this.language)).join(' · ') || this.w('Choose your first module', 'Välj din första modul')}</small></button>`)}</div>
        ${this.pendingPreset ? html`<div class="notice" role="region" aria-label=${this.w('Replace content', 'Byt innehåll')}><p>${this.w('Current modules will be replaced. Appearance is kept.', 'Nuvarande moduler ersätts. Utseendet behålls.')}</p><p>${this.config.modules.map(module => moduleTitle(module, this.language)).join(', ')} → ${label(PRESETS[this.pendingPreset], this.language)}</p><div class="buttons"><button @click=${() => { this.updateConfig(config => configAPI.applyPreset(config, this.pendingPreset)); this.selected = this.config.modules[0]?.id ?? ''; this.pendingPreset = ''; }}>${this.w('Replace content', 'Byt innehåll')}</button><button @click=${() => { this.pendingPreset = ''; }}>${this.w('Cancel', 'Avbryt')}</button></div></div>` : ''}
        ${this.input(this.w('Card title', 'Kortrubrik'), this.config.title, value => this.updateConfig(config => ({ ...config, title: value })))}
        ${this.entries.length > 1 || this.config.f1_entry_id ? this.select(this.w('F1 Sensor installation', 'F1 Sensor-installation'), this.config.f1_entry_id, [['', this.w('Automatic (one installation)', 'Automatiskt (en installation)')], ...this.entries.map(entry => [entry.entry_id, entry.title])], value => this.updateConfig(config => ({ ...config, f1_entry_id: value }))) : ''}
        <h3>${this.w('Your modules', 'Dina moduler')}</h3><ol class="module-list">${repeat(this.config.modules, module => module.id, (module, index) => html`<li class="module-row"><button class="select-module" data-module=${module.id} aria-pressed=${String(this.selected === module.id)} @click=${() => { this.selected = module.id; }}>${index + 1}. ${moduleTitle(module, this.language)}</button><button ?disabled=${index === 0} aria-label=${`${this.w('Move up', 'Flytta upp')} ${moduleTitle(module, this.language)}`} @click=${() => this.move(module.id, -1)}>↑</button><button ?disabled=${index === this.config.modules.length - 1} aria-label=${`${this.w('Move down', 'Flytta ned')} ${moduleTitle(module, this.language)}`} @click=${() => this.move(module.id, 1)}>↓</button></li>`)}</ol>
        ${this.select(this.w('Add module', 'Lägg till modul'), '', [['', this.w('Choose content…', 'Välj innehåll…')], ...Object.values(MODULES).map(module => [module.id, label(module, this.language)])], value => { if (!value) return; const module = configAPI.makeModule(value, this.config.modules); this.updateConfig(config => ({ ...config, modules: [...config.modules, module] })); this.selected = module.id; })}
        ${this.moduleSettings()}${this.appearanceSettings()}${this.actionSettings()}${this.migrationSettings()}
        <details><summary>${this.w('Layout and shared focus', 'Layout och gemensamt fokus')}</summary>
          ${this.select(this.w('Layout', 'Layout'), this.config.layout, [['stack', this.w('Stacked modules', 'Staplade moduler')], ['tabs', this.w('Tabs', 'Flikar')]], value => this.updateConfig(config => ({ ...config, layout: value })))}
          ${this.focusPicker('driver', this.w('Default driver', 'Förvald förare'), this.config.context.driver, value => this.setGroup('context', 'driver', value))}
          ${this.focusPicker('team', this.w('Default team', 'Förvalt team'), this.config.context.team, value => this.setGroup('context', 'team', value))}
          ${this.selectionPicker(this.w('Card session', 'Kortets session'), this.config.context.selection, value => this.setGroup('context', 'selection', value))}
          ${this.check(this.w('Share driver focus with a named group', 'Dela förarfokus med en namngiven grupp'), this.config.context.scope === 'group', value => this.updateConfig(config => ({ ...config, context: { ...config.context, scope: value ? 'group' : 'local', group: config.context.group || 'F1' } })))}
          ${this.config.context.scope === 'group' ? this.input(this.w('Group name', 'Gruppnamn'), this.config.context.group, value => this.setGroup('context', 'group', value)) : ''}
          ${this.config.context.scope === 'group' ? this.check(this.w('Share temporary session selection', 'Dela tillfälligt sessionsurval'), this.config.context.share.includes('selection'), enabled => this.setGroup('context', 'share', enabled ? [...this.config.context.share, 'selection'] : this.config.context.share.filter(item => item !== 'selection'))) : ''}
          <p class="muted">${this.w('Groups share selected display context in this dashboard view. Pinned cards keep their own session. Replay, Live Delay and automations are unaffected.', 'Grupper delar valt visningssammanhang i denna dashboardvy. Låsta kort behåller sin egen session. Replay, Live Delay och automationer påverkas inte.')}</p>
          ${this.check(this.w('Show Live Delay and global spoiler controls', 'Visa kontroller för Live Delay och globalt spoilerskydd'), this.config.context.viewing_controls, value => this.setGroup('context', 'viewing_controls', value))}
          <p class="muted">${this.w('Optional viewing controls change integration settings. Live Delay affects this installation and its automations; spoiler protection affects every F1 installation.', 'Valfria visningskontroller ändrar integrationens inställningar. Live Delay påverkar denna installation och dess automationer; spoilerskyddet påverkar alla F1-installationer.')}</p>
          ${this.check(this.w('Always hide spoilers in this card', 'Dölj alltid spoilers i detta kort'), this.config.context.spoilers === 'hide', value => this.setGroup('context', 'spoilers', value ? 'hide' : 'inherit'))}
        </details>
        <details><summary>${this.w('Reusable templates', 'Återanvändbara mallar')}</summary><p class="muted">${this.w('Export a named template or paste/open one to review it before replacing this card. Applying a template can be undone and does not save the dashboard automatically.', 'Exportera en namngiven mall eller klistra in/öppna en för att granska den innan kortet ersätts. En tillämpad mall kan ångras och sparar inte dashboarden automatiskt.')}</p>
          ${this.input(this.w('Template name', 'Mallnamn'), this.templateName, value => { this.templateName = value; })}
          <label><span>${this.w('Template JSON', 'Mallens JSON')}</span><textarea .value=${this.transfer} @input=${event => { this.transfer = event.target.value; }}></textarea></label>
          <div class="buttons"><button @click=${() => { try { this.transfer = configAPI.exportTemplate(this.config, this.templateName); this.error = ''; } catch (error) { this.error = error.message; } }}>${this.w('Export template', 'Exportera mall')}</button><button @click=${() => this.reviewTemplate(this.transfer)}>${this.w('Review template', 'Granska mall')}</button><label class="file-button"><span>${this.w('Open template file', 'Öppna mallfil')}</span><input type="file" accept="application/json,.json" @change=${event => this.readTemplateFile(event)}></label></div>
          ${this.pendingTemplate ? html`<div class="notice" role="region" aria-label=${this.w('Template review', 'Mallgranskning')}><p><strong>${this.pendingTemplate.name}</strong></p><p>${this.w('Current content', 'Nuvarande innehåll')}: ${this.config.modules.map(module => moduleTitle(module, this.language)).join(', ') || '—'}<br>${this.w('Template content', 'Mallens innehåll')}: ${this.pendingTemplate.card.modules.map(module => moduleTitle(module, this.language)).join(', ') || '—'}</p>
            ${this.pendingTemplate.card.f1_entry_id && !this.entries.some(entry => entry.entry_id === this.pendingTemplate.card.f1_entry_id) ? html`<p>${this.w('The saved installation is not available here. Choose the installation this copy should use.', 'Den sparade installationen finns inte här. Välj vilken installation kopian ska använda.')}</p>${this.select(this.w('F1 Sensor installation for template', 'F1 Sensor-installation för mallen'), this.templateEntry, [['', this.w('Choose…', 'Välj…')], ...this.entries.map(entry => [entry.entry_id, entry.title])], value => { this.templateEntry = value; })}` : ''}
            <div class="buttons"><button @click=${() => { this.pendingTemplate = null; this.templateEntry = ''; }}>${this.w('Cancel', 'Avbryt')}</button><button ?disabled=${Boolean(this.pendingTemplate.card.f1_entry_id && !this.entries.some(entry => entry.entry_id === this.pendingTemplate.card.f1_entry_id) && !this.templateEntry)} @click=${() => this.applyTemplate()}>${this.w('Apply template', 'Tillämpa mall')}</button></div></div>` : ''}
        </details><details><summary>${this.w('Advanced card JSON', 'Avancerad kort-JSON')}</summary><p class="muted">${this.w('Export or import the raw card configuration. Import applies immediately and can be undone.', 'Exportera eller importera kortets råa konfiguration. Import tillämpas direkt och kan ångras.')}</p>
          <div class="buttons"><button @click=${() => { this.transfer = configAPI.exportConfig(this.config); }}>${this.w('Export card JSON', 'Exportera kort-JSON')}</button><button @click=${() => this.updateConfig(() => configAPI.importConfig(this.transfer))}>${this.w('Import card JSON', 'Importera kort-JSON')}</button></div>
        </details>
      </div><div class="preview"><h3>${this.w('Preview', 'Förhandsvisning')}</h3><div class="toolbar">
        ${this.select(this.w('Sample session', 'Exempelsession'), this.scene, [['before', this.w('Before a session', 'Före session')], ['practice', this.w('Practice', 'Träning')], ['qualifying', this.w('Qualifying', 'Kval')], ['sprint_qualifying', this.w('Sprint qualifying', 'Sprintkval')], ['sprint', 'Sprint'], ['race', 'Race'], ['ended', this.w('Finished', 'Avslutad')], ['replay', 'Replay'], ['missing', this.w('Missing data', 'Saknad data')]], value => { this.scene = value; })}
        ${this.select(this.w('Preview width', 'Förhandsvisningens bredd'), this.width, [['narrow', this.w('Narrow', 'Smal')], ['normal', this.w('Normal', 'Normal')], ['wide', this.w('Wide', 'Bred')]], value => { this.width = value; })}
      </div><div class="preview-shell" style=${`--preview-width:${this.width === 'narrow' ? '360px' : this.width === 'wide' ? '1050px' : '100%'}`}>${this.previewNode}</div></div></div>`;
  }
}
if (!customElements.get('f1-sensor-card-editor')) customElements.define('f1-sensor-card-editor', F1SensorCardEditor);
