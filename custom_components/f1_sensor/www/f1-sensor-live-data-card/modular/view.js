const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
let chartLoading, mapLoading, telemetryLoading;
const [{ LitElement, html, css, repeat }, { FIELDS, fieldDefinition, moduleFields, moduleFocusKinds, INCIDENT_SIGNALS, label }, { formatTime, formatDelta, timingStatus, SIGNALS, statusColors, safeImageUrl, compoundMeta, trackSignal, logoDimensions }, { getTeamLogoMeta }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./catalog.js'), load('./semantics.js'), load('../platform/branding.js'),
]);

export const words = (language, en, sv) => String(language).startsWith('sv') ? sv : en;
export function dateTime(value, settings = {}, options = {}) {
  const date = new Date(value);
  if (value === null || value === undefined || value === '' || !Number.isFinite(date.getTime())) return '—';
  const language = settings.language || 'en';
  const format = { timeZone: settings.timezone || 'UTC', ...options };
  if (format.timeStyle || ['hour', 'minute', 'second'].some(key => key in format)) {
    const preference = settings.timeFormat;
    let hour12 = preference === '12';
    if (preference !== '12' && preference !== '24') {
      try { hour12 = new Intl.DateTimeFormat(preference === 'system' ? undefined : language, { hour: 'numeric' }).resolvedOptions().hour12; }
      catch { hour12 = false; }
    }
    // h23 keeps midnight at 00:00 even with an English (US) interface.
    format.hourCycle = hour12 ? 'h12' : 'h23';
  }
  try { return new Intl.DateTimeFormat(language, format).format(date); }
  catch { return new Intl.DateTimeFormat('en', { ...format, timeZone: 'UTC' }).format(date); }
}
const documentType = title => {
  const text = String(title ?? '').toLowerCase();
  if (text.includes('summons')) return 'Summons';
  if (text.includes('penalty')) return 'Penalty';
  if (text.includes('decision')) return 'Decision';
  if (text.includes('classification')) return 'Classified';
  if (text.includes('result')) return 'Result';
  if (text.includes('championship')) return 'Points';
  if (text.includes('scrutineering')) return 'Checks';
  return 'Document';
};
const documentTone = title => {
  const text = String(title ?? '').toLowerCase();
  if (text.includes('penalty') || text.includes('decision')) return 'red';
  if (text.includes('summons') || text.includes('stewards')) return 'yellow';
  if (text.includes('classification') || text.includes('result')) return 'blue';
  if (text.includes('championship') || text.includes('points')) return 'green';
  if (text.includes('scrutineering') || text.includes('technical')) return 'orange';
  return 'neutral';
};

export const sharedStyles = css`
  :host { display:block; min-width:0; color:var(--f1-text,var(--primary-text-color,#e9edf3)); font-family:var(--ha-font-family-body,inherit); font-size:1rem; line-height:1.5; }
  :host([hidden]) { display:none!important; }
  * { box-sizing:border-box; }
  button,input,select,textarea { font:inherit; color:inherit; }
  button { min-height:44px; min-width:44px; padding:8px 12px; cursor:pointer; border:1px solid var(--f1-border,#6c7480); background:var(--f1-surface,transparent); border-radius:8px; }
  button:disabled { cursor:default; opacity:.5; }
  button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,[tabindex]:focus-visible { outline:3px solid var(--f1-focus,#56aaff); outline-offset:3px; }
  button:hover:not(:disabled) { background:var(--f1-hover,rgba(127,127,127,.14)); }
  button[aria-pressed=true],button[aria-selected=true] { border-color:currentColor; box-shadow:inset 0 -3px currentColor; }
  h2,h3,p { margin:0; }
  h2 { font-family:var(--f1-heading-font,inherit); font-size:var(--f1-module-heading-size,1.1em); font-weight:700; text-transform:var(--f1-heading-transform,none); letter-spacing:.01em; }
  h3 { font-size:1em; }
  .muted { color:var(--f1-muted,#b9c1ce); }
  .sr { position:absolute; left:0; top:0; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
  .empty { padding:24px 16px; border:1px dashed var(--f1-border,#6c7480); border-radius:10px; }
  .empty p+p { margin-top:8px; }
  .chip { display:inline-flex; align-items:center; gap:6px; font-size:.85em; font-weight:650; padding:3px 8px; border:1px solid currentColor; border-radius:5px; }
  .section-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; flex-wrap:wrap; }
  .table-scroll { overflow:auto; max-width:100%; scrollbar-gutter:stable; border:1px solid var(--f1-border,#6c7480); border-radius:var(--f1-table-radius,8px); }
  .result-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr)); gap:12px; list-style:none; margin:0; padding:0; }
  .result-grid li { border:1px solid var(--f1-divider); border-left:4px solid var(--f1-border); border-radius:8px; padding:12px; min-width:0; }
  .result-grid dl { display:grid; grid-template-columns:minmax(7rem,auto) minmax(0,1fr); gap:5px 10px; margin:0; }
  .result-grid dt { color:var(--f1-muted); font-size:.85em; } .result-grid dd { margin:0; min-width:0; overflow-wrap:anywhere; }
  table { width:100%; border-collapse:separate; border-spacing:0; font-variant-numeric:var(--f1-numerals,tabular-nums); }
  th,td { padding:var(--f1-cell-padding,10px 12px); text-align:left; vertical-align:middle; border-bottom:1px solid var(--f1-divider,rgba(127,127,127,.25)); white-space:nowrap; }
  th { font-weight:650; color:var(--f1-muted,#b9c1ce); font-size:.85em; background:var(--f1-panel,rgba(127,127,127,.07)); }
  tbody tr:last-child td { border-bottom:0; }
  tbody tr:nth-child(even) { background:var(--f1-row-alternate,transparent); }
  thead.labels-hidden th { padding:0; border:0; height:0; }
  .metric strong { font-variant-numeric:var(--f1-numerals,tabular-nums); }
  .replay-controls { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }
  .replay-controls button { display:inline-flex; align-items:center; justify-content:center; gap:6px; }
  .replay-controls button.icon-only { min-width:44px; padding-inline:10px; }
  .replay-scope { font-size:.85em; margin:8px 0 14px; }
  .replay-picker { display:grid; gap:12px; margin:12px 0; }
  .replay-picker label { display:grid; gap:4px; min-width:0; }
  .replay-picker select { width:100%; min-width:0; min-height:44px; padding:8px; border:1px solid var(--f1-border); background:var(--f1-surface); border-radius:8px; }
  .replay-progress { display:grid; gap:6px; font-variant-numeric:tabular-nums; }
  .replay-progress input { width:100%; min-height:44px; margin:0; accent-color:var(--f1-focus); }
  .replay-progress progress { width:100%; accent-color:var(--f1-focus); }
  .weather-list { margin:0; }
  .weather-list .weather-item { display:flex; align-items:baseline; justify-content:space-between; flex-wrap:wrap; gap:6px 20px; padding:var(--f1-item-padding,9px) 0; border-bottom:1px solid var(--f1-divider); }
  .weather-item dt { color:var(--f1-muted); }
  dl.overview { margin:0; display:flex; flex-wrap:wrap; }
  dl.overview > .weather-item { flex:1 1 8rem; min-width:0; }
  .metric.weather-item dt { font-size:.85em; margin-bottom:5px; }
  .metric.weather-item dd { font-size:1.35em; line-height:1.3; overflow-wrap:anywhere; }
  .metric.weather-item .provenance { font-size:.65em; line-height:1.5; }
  .weather-item dd { margin:0; font-weight:650; font-variant-numeric:tabular-nums; }
  .weather-symbol { display:inline-block; width:1.3em; text-align:center; margin-right:.25em; color:inherit; }
  .weather-condition { display:inline-flex; align-items:center; gap:.25em; max-width:100%; }
  .weather-condition-text { min-width:0; }
  ha-icon.weather-symbol { --mdc-icon-size:1.1em; display:inline-flex; align-items:center; justify-content:center; flex:0 0 1.3em; height:1.1em; margin:0; line-height:0; }
  @media (forced-colors:active) { ha-icon.weather-symbol { color:CanvasText !important; } }
  .weather-item .provenance { font-weight:400; }

  .analysis-explanation { margin-top:12px; font-size:.85em; }
  .analysis-explanation summary { min-height:44px; padding:10px 0; cursor:pointer; }
  .analysis-explanation summary:focus-visible { outline:3px solid var(--f1-focus); outline-offset:3px; }
  .stint-chart { margin:0 0 16px; }
  .stint-chart > p { margin-bottom:12px; }
  .stint-bars { list-style:none; padding:0; margin:0; max-height:550px; overflow:auto; scrollbar-gutter:stable; }
  .stint-bars li { margin:0 0 14px; padding:12px; border:1px solid var(--f1-border); border-radius:8px; }
  .stint-meta { display:flex; gap:8px 16px; align-items:center; justify-content:space-between; flex-wrap:wrap; }
  .stint-lane { position:relative; height:22px; margin:10px 0; border-bottom:1px dashed var(--f1-border); }
  .stint-bar { position:absolute; height:20px; border:1px solid var(--f1-text); border-top:5px solid var(--stint-color,var(--f1-text)); background:var(--f1-panel); }
  .stint-axis { display:flex; justify-content:space-between; font-size:.8em; }
  @media(forced-colors:active) { .stint-bar { border-color:CanvasText!important; background:Canvas!important; } }
  .stint-runs { padding-left:1.2em; margin:0; }
  .incident-list dl { display:flex; flex-wrap:wrap; gap:10px 24px; margin:0; }
  .incident-list dl > div { min-width:0; overflow-wrap:anywhere; }
  .incident-list dt { font-size:.8em; }
  .incident-list dd { margin:0; }
  .cell-stack { display:flex; flex-direction:column; align-items:flex-start; gap:3px; }
  .provenance { display:block; font-size:.75em; line-height:1.3; color:var(--f1-muted,#b9c1ce); }
  .time { font-variant-numeric:var(--f1-numerals,tabular-nums); }
  .signal { display:inline-flex; align-items:center; gap:5px; border:1px solid transparent; border-radius:4px; padding:2px 5px; font-weight:650; }
  .signal.deleted .time { text-decoration:line-through; }
  .driver { display:flex; align-items:center; gap:8px; border:0; border-left:3px solid var(--team-color,transparent); background:transparent; border-radius:0; text-align:left; font-weight:700; padding-left:9px; }
  .driver-headshot { width:var(--f1-logo-frame,32px); height:var(--f1-logo-frame,32px); object-fit:cover; object-position:center top; border-radius:50%; background:var(--f1-panel); flex:0 0 auto; }
  .tyre { display:inline-flex; align-items:center; gap:7px; }
  .compound { position:relative; display:inline-flex; width:32px; height:32px; flex:0 0 32px; align-items:center; justify-content:center; border:3px solid var(--compound-color,currentColor); border-radius:50%; background:#141920; color:#ffffff; font-weight:750; }
  .compound img { position:absolute; width:32px; height:32px; object-fit:contain; }
  .compound.image { border:0; }
  .tyre-letter { font-weight:750; }
  .track-signal { display:inline-flex; align-items:center; gap:8px; font-size:1rem; }
  .track-symbol { min-width:28px; text-align:center; border:1px solid currentColor; border-radius:3px; padding:1px 4px; font-weight:750; }
  .overview { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr)); gap:18px; }
  .overview.compact { grid-template-columns:1fr; }
  .overview.full { grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr)); }
  .metric small { display:block; color:var(--f1-muted,#b9c1ce); margin-bottom:5px; }
  .metric strong { display:block; font-size:1.35em; line-height:1.25; overflow-wrap:anywhere; }
  .metric.hero { grid-column:1/-1; }
  .metric-value { display:flex; align-items:center; gap:14px; min-width:0; }
  .metric-value strong { min-width:0; }
  .metric.hero:has(.flag:not([hidden])) > small { margin-inline-start:54px; }
  .metric-value .flag { margin-top:0; }
  .metric.hero strong { font-size:clamp(1.4rem,4vw,2rem); letter-spacing:-.025em; }
  .circuit-panel { grid-column:1/-1; display:grid; gap:12px; }
  .circuit-map { min-height:180px; display:grid; place-items:center; overflow:hidden; border:1px solid var(--f1-border); border-radius:10px; background:var(--f1-panel); }
  .circuit-map img { display:block; width:100%; max-height:360px; object-fit:contain; }
  .circuit-map-copy { padding:18px; text-align:center; }
  .history-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr)); gap:8px; }
  .history-item { padding:10px; border:1px solid var(--f1-border); border-radius:8px; background:var(--f1-panel); }
  .history-item small,.history-item span { display:block; color:var(--f1-muted); }
  .history-list { margin:0; padding-left:22px; }
  .flag { width:40px; height:27px; object-fit:contain; flex:0 0 40px; margin-top:5px; }
  .schedule { list-style:none; padding:0; margin:0; }
  .schedule li { display:flex; justify-content:space-between; gap:12px; padding:12px 0; border-bottom:1px solid var(--f1-divider,rgba(127,127,127,.25)); flex-wrap:wrap; }
  .schedule li:last-child { border-bottom:0; }
  .schedule-identity { display:flex; align-items:flex-start; gap:12px; min-width:0; }
  .schedule-copy { min-width:0; overflow-wrap:anywhere; }
  .flag-fallback { display:block; max-width:90px; overflow-wrap:anywhere; }
  .flag-fallback[hidden] { display:none; }
  .schedule time { font-variant-numeric:tabular-nums; font-weight:650; }
  .events { list-style:none; padding:0; margin:0; max-height:440px; overflow:auto; }
  .events li { border-left:2px solid var(--f1-border,#6c7480); margin:0 0 16px 5px; padding:0 12px 8px; overflow-wrap:anywhere; }
  .event-meta { display:flex; gap:8px; flex-wrap:wrap; font-size:.8em; margin-bottom:5px; color:var(--f1-muted,#b9c1ce); }
  .timing-legend { margin-top:12px; font-size:.85em; line-height:1.5; overflow-wrap:anywhere; }
  .timing-legend summary { min-height:44px; padding:10px 0; cursor:pointer; box-sizing:border-box; }
  .timing-legend summary:focus-visible { outline:3px solid var(--f1-focus,#56aaff); outline-offset:3px; }
  .timing-legend dl { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr)); gap:12px; margin:8px 0; }
  .timing-legend dt { font-weight:650; }
  .timing-legend dd { margin:4px 0 0; }
  .timing-legend p { margin:10px 0; }
  a { color:var(--f1-focus,#7ebfff); text-underline-offset:3px; }
  .module-context { margin:-4px 0 14px; color:var(--f1-muted); font-size:.85em; overflow-wrap:anywhere; }
  .module-picker { display:block; margin:0 0 14px; }
  .archive-pickers { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,11rem),1fr)); gap:0 12px; }
  .module-picker select { display:block; max-width:100%; width:100%; min-height:44px; font:inherit; color:inherit; background:var(--f1-surface); border:1px solid var(--f1-border); border-radius:7px; padding:8px; }
  .timing-gap-toggle { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:0 0 12px; }
  .timing-gap-toggle button { min-width:88px; }
  th.recent-lap.lap-start,td.recent-lap.lap-start { border-left:2px solid var(--f1-border,#6c7480); }
  .documents { list-style:none; margin:0; padding:0; }
  .documents li { border-bottom:1px solid var(--f1-divider); padding:12px 0; overflow-wrap:anywhere; }
  .documents li[class^="tone-"] { border-left:3px solid var(--document-tone,var(--f1-border)); padding-left:10px; }
  .documents li.tone-red { --document-tone:#ff3b30; } .documents li.tone-yellow { --document-tone:#ffd60a; }
  .documents li.tone-blue { --document-tone:#0a84ff; } .documents li.tone-green { --document-tone:#34c759; }
  .documents li.tone-orange { --document-tone:#ff9500; } .documents li.tone-neutral { --document-tone:var(--f1-border); }
  .documents a { display:inline-flex; align-items:center; min-height:44px; }
  .documents ha-icon { margin-right:7px; flex:0 0 auto; }
  .documents small { display:block; color:var(--f1-muted); }
  .document-type { display:inline-flex!important; width:max-content; margin-top:3px; padding:1px 6px; border:1px solid currentColor; border-radius:999px; font-size:.72em; font-weight:650; text-transform:uppercase; }
  .document-summary { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin:0 0 8px; color:var(--f1-muted); font-size:.85em; }
  .details { padding:14px; white-space:normal; background:var(--f1-panel,rgba(127,127,127,.07)); }
  .details dl { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:12px; margin:0; }
  .details dd { margin:2px 0 0; }
  @media (prefers-reduced-motion:reduce) { *,*::before,*::after { animation:none!important; transition:none!important; scroll-behavior:auto!important; } }
  @media (forced-colors:active) { :host,ha-card { --f1-surface:Canvas!important; --f1-panel:Canvas!important; --f1-text:CanvasText!important; --f1-muted:CanvasText!important; --f1-border:CanvasText!important; --f1-divider:GrayText!important; --f1-focus:Highlight!important; } :host,ha-card { color:CanvasText!important; background:Canvas!important; } .signal,.chip,.compound,.track-symbol { forced-color-adjust:auto; border-color:CanvasText!important; color:CanvasText!important; background:Canvas!important; } button { border:1px solid ButtonText; } .driver { border-left-color:CanvasText; } .muted,th,.provenance,.event-meta { color:CanvasText; } }
`;

export class F1ModuleView extends LitElement {
  static properties = { module: { attribute: false }, model: { attribute: false }, settings: { attribute: false }, expanded: { state: true }, stintTable: { state: true }, seekDraft: { state: true }, clearConfirm: { state: true }, timingGapMode: { state: true } };
  static styles = sharedStyles;
  constructor() { super(); this.expanded = ''; this.clearConfirm = false; this.raceQueue = []; }
  disconnectedCallback() { super.disconnectedCallback(); clearTimeout(this.raceTimer); clearTimeout(this.clearTimer); }
  get language() { return this.settings?.language ?? 'en'; }
  w(en, sv) { return words(this.language, en, sv); }
  willUpdate() {
    if (this.seekDraft && this.seekDraft.context !== this.model?.controlContext) this.seekDraft = null;
    const configuredGap = this.module?.fields?.includes('interval') ? 'ahead' : this.module?.fields?.includes('gap') ? 'leader' : '';
    const timingGapContext = `${this.module?.id ?? ''}|${configuredGap}|${this.module?.options?.show_gap_toggle === true}`;
    if (timingGapContext !== this.timingGapContext) {
      this.timingGapContext = timingGapContext;
      this.timingGapMode = configuredGap || 'ahead';
    }
    this.syncRaceControlMessage();
    this.setAttribute('density', this.settings?.appearance?.density ?? 'comfortable');
    const focused = this.shadowRoot?.activeElement;
    this.focusKey = focused?.dataset?.focus ?? null;
  }
  syncRaceControlMessage() {
    if (this.module?.type !== 'race_control') return;
    const latest = this.module.options.presentation === 'latest_message', seconds = this.module.options.min_display_time;
    const context = `${this.module.id}|${this.model?.raceControlContext ?? ''}|${latest}|${seconds}`;
    if (context !== this.raceContext) {
      clearTimeout(this.raceTimer); this.raceContext = context; this.raceQueue = []; this.raceShown = this.model?.rows?.[0] ?? null; this.raceShownAt = Date.now();
      this.clearConfirm = false; clearTimeout(this.clearTimer);
    }
    if (!latest || !Number.isInteger(seconds) || seconds <= 0) { clearTimeout(this.raceTimer); this.raceQueue = []; this.raceShown = null; return; }
    const incoming = this.model?.rows?.[0] ?? null;
    if (!this.raceShown && incoming) { this.raceShown = incoming; this.raceShownAt = Date.now(); }
    else if (incoming && incoming.id !== this.raceShown?.id && !this.raceQueue.some(row => row.id === incoming.id)) {
      this.raceQueue.push(incoming); this.raceQueue = this.raceQueue.slice(-50);
    }
    this.scheduleRaceControlMessage(seconds * 1000);
  }
  scheduleRaceControlMessage(duration) {
    clearTimeout(this.raceTimer);
    if (!this.raceQueue.length) return;
    const remaining = duration - (Date.now() - this.raceShownAt);
    if (remaining > 0) { this.raceTimer = setTimeout(() => this.advanceRaceControlMessage(duration), remaining); return; }
    this.advanceRaceControlMessage(duration);
  }
  advanceRaceControlMessage(duration) {
    const next = this.raceQueue.shift(); if (!next) return;
    this.raceShown = next; this.raceShownAt = Date.now(); this.requestUpdate(); this.scheduleRaceControlMessage(duration);
  }
  clearRaceControl() {
    if (this.model?.readonly || this.model?.request?.pending) return;
    if (!this.clearConfirm) {
      this.clearConfirm = true; clearTimeout(this.clearTimer);
      this.clearTimer = setTimeout(() => { this.clearConfirm = false; this.requestUpdate(); }, 5000); return;
    }
    this.clearConfirm = false; clearTimeout(this.clearTimer);
    this.dispatchEvent(new CustomEvent('f1-race-control-action', { bubbles: true, composed: true, detail: { module: this.module.id, action: 'clear' } }));
  }
  updated() {
    if (this.focusKey && this.shadowRoot.activeElement?.dataset?.focus !== this.focusKey) {
      [...this.shadowRoot.querySelectorAll('[data-focus]')].find(node => node.dataset.focus === this.focusKey)?.focus({ preventScroll: true });
    }
  }
  render() {
    if (!this.module || !this.model) return html``;
    const title = this.module.title || this.model.title;
    return html`<section part="module-content" aria-label=${title}>
      ${this.module.show_header !== false || this.model.badge ? html`<div class="section-head" part="module-header"><h2 part="module-title" class=${this.module.show_header === false ? 'sr' : ''}>${title}</h2>${this.model.badge ? html`<span class="chip" part="module-badge">${this.model.badge}</span>` : ''}</div>` : html`<h2 class="sr" part="module-title">${title}</h2>`}
      ${this.module.focus_mode === 'independent' && moduleFocusKinds(this.module).length ? html`<p class="muted module-focus">${this.w('Own selection', 'Eget urval')}</p>` : ''}
      ${this.model.blocked ? this.empty(this.model.blocked) : html`${this.contextLine()}${this.coverageLine()}${this.content()}`}
      ${this.module.options.show_explanation !== false && this.model.explanation ? html`<details class="analysis-explanation"><summary>${this.model.explanationTitle ?? this.w('About this analysis', 'Om analysen')}</summary><p class="muted">${this.model.explanation}</p></details>` : ''}
      ${this.model.notice ? html`<p class="muted" style="margin-top:10px;font-size:.85em">${this.model.notice}</p>` : ''}
    </section>`;
  }
  empty(message) { return html`<div class="empty" part="empty-state"><p>${message}</p></div>`; }
  content() {
    switch (this.module.type) {
      case 'overview': return this.overview();
      case 'weather': return this.weather();
      case 'calendar': return this.calendar();
      case 'timing': return this.timing();
      case 'results': case 'standings': case 'tyres': case 'pit_stops': return this.results();
      case 'strategy': return this.strategy();
      case 'battles': case 'timeline': case 'incidents': return this.model.summary || this.module.options.presentation === 'table' ? this.results() : this.incidents();
      case 'documents': return this.documents();
      case 'progression': case 'lap_chart': return this.chart();
      case 'map': return this.map();
      case 'replay': return this.replay();
      case 'archive': return this.archive();
      case 'telemetry': return this.telemetry();
      case 'race_control': return this.events();
      default: return this.empty(this.w('This module needs a newer card version. Its settings are preserved.', 'Den här modulen kräver en nyare kortversion. Inställningarna finns kvar.'));
    }
  }
  map() {
    if (!this.mapNode) {
      this.mapNode = document.createElement('f1-track-map-view');
      this.mapNode.setAttribute('part', 'map');
      mapLoading ??= load('./map-view.js').catch(error => { mapLoading = null; throw error; });
      mapLoading.catch(() => { this.mapError = true; this.requestUpdate(); });
    }
    if (this.mapError) return this.empty(this.w('The map could not be loaded. Reload this dashboard to try again.', 'Kartan kunde inte laddas. Ladda om dashboarden för att försöka igen.'));
    this.mapNode.model = this.model; this.mapNode.module = this.module; this.mapNode.settings = this.settings;
    return this.mapNode;
  }
  chart() {
    if (!this.module.fields.includes(['lap_chart', 'archive'].includes(this.module.type) ? 'lap_series' : 'progression')) return this.empty(this.w('Choose fields in the editor.', 'Välj fält i editorn.'));
    if (!this.chartNode) {
      this.chartNode = document.createElement('f1-series-chart');
      this.chartNode.setAttribute('part', 'chart');
      chartLoading ??= load('./chart.js').catch(error => { chartLoading = null; throw error; });
      chartLoading.catch(() => { this.chartError = true; this.requestUpdate(); });
    }
    if (this.chartError) return this.empty(this.w('The chart could not be loaded. Reload this dashboard to try again.', 'Diagrammet kunde inte laddas. Ladda om dashboarden för att försöka igen.'));
    this.chartNode.model = this.model; this.chartNode.module = this.module; this.chartNode.settings = this.settings;
    return this.chartNode;
  }
  telemetry() {
    if (!this.telemetryNode) {
      this.telemetryNode = document.createElement('f1-telemetry-view');
      this.telemetryNode.setAttribute('part', 'telemetry');
      telemetryLoading ??= load('./telemetry-view.js').catch(error => { telemetryLoading = null; throw error; });
      telemetryLoading.catch(() => { this.telemetryError = true; this.requestUpdate(); });
    }
    if (this.telemetryError) return this.empty(this.w('Telemetry view could not be loaded. Reload the dashboard.', 'Telemetrivyn kunde inte laddas. Ladda om dashboarden.'));
    this.telemetryNode.model = this.model; this.telemetryNode.module = this.module; this.telemetryNode.settings = this.settings;
    return this.telemetryNode;
  }
  archive() {
    const model = this.model, options = this.module.options;
    const picker = (key, title, value, choices) => html`<label class="module-picker"><span>${title}</span><select aria-label=${title} data-focus=${`archive-${key}`} .value=${String(value ?? '')} @change=${event => this.choose(key, key === 'year' ? Number(event.target.value) : event.target.value)}>
      ${choices.map(([id, name]) => html`<option value=${String(id)} .selected=${String(id) === String(value ?? '')}>${name}</option>`)}</select></label>`;
    const currentYear = new Date().getUTCFullYear(), lastYear = Math.max(currentYear, model.year), years = Array.from({ length: lastYear - 1950 + 1 }, (_, i) => [lastYear - i, String(lastYear - i)]);
    const meetingChoices = model.meetings.map(item => [String(item.round), `${item.round} · ${item.name}`]);
    const sessionChoices = model.sessions.map(item => [item.session_key, item.name]);
    const selectedRound = model.meeting ? String(model.meeting.round) : model.requestedRound;
    const selectedSession = model.session?.session_key ?? model.requestedSession;
    if (selectedRound && !meetingChoices.some(([id]) => id === selectedRound)) meetingChoices.push([selectedRound, `${selectedRound} · ${this.w('saved selection unavailable', 'sparat val saknas')}`]);
    if (selectedSession && !sessionChoices.some(([id]) => id === selectedSession)) sessionChoices.push([selectedSession, this.w('Saved session unavailable', 'Sparad session saknas')]);
    const errorMessage = model.disconnected ? this.w('Home Assistant is disconnected. The archive will reload after reconnection.', 'Home Assistant är frånkopplad. Arkivet laddas igen efter återanslutning.') : model.error ? this.w('The archive could not be loaded. Try again when the source is available.', 'Arkivet kunde inte hämtas. Försök igen när källan är tillgänglig.') : null;
    return html`${options.show_session_selector ? html`<div class="archive-pickers">
      ${picker('year', this.w('Year', 'År'), model.year, years)}
      ${picker('round', this.w('Grand Prix', 'Grand Prix'), selectedRound, [['', this.w('Latest started event', 'Senaste påbörjade tävling')], ...meetingChoices])}
      ${picker('session_key', this.w('Session', 'Session'), selectedSession, [['', this.w('Latest supported session', 'Senaste session med stöd')], ...sessionChoices])}
    </div>` : ''}
    ${errorMessage ? html`${this.empty(errorMessage)}${!model.disconnected ? html`<button @click=${() => this.choose('retry', true)}>${this.w('Retry archive', 'Försök hämta arkivet igen')}</button>` : ''}`
      : model.loading ? this.empty(this.w('Loading archive…', 'Hämtar arkiv…'))
      : !model.session ? this.empty(this.w('No session matches this selection. Choose another event or session.', 'Ingen session matchar urvalet. Välj en annan tävling eller session.'))
      : model.unsupported ? this.empty(options.content === 'classification' ? this.w('This source provides race, sprint and qualifying results. Results for this session are unavailable.', 'Källan ger resultat från race, sprint och kval. Resultat för den här sessionen saknas.') : this.w('Historical lap times and positions are available for races only.', 'Historiska varvtider och placeringar finns endast för race.'))
      : model.invalidIdentity ? this.empty(this.w('The returned lap data belongs to a different session. Reload the archive.', 'Varvuppgifterna hör till en annan session. Hämta arkivet igen.'))
      : model.invalidRange ? this.empty(this.w('The first lap is after the last lap. Adjust the range in the editor.', 'Första varvet är efter det sista. Ändra intervallet i editorn.'))
      : options.content === 'classification' ? this.results() : this.chart()}`;
  }
  contextLine() {
    const context = this.model.context;
    if (!context) return '';
    const details = this.module.options?.show_context === false ? [] : [context?.meeting, context?.session, context?.season, context?.round ? `${this.w('Round', 'Deltävling')} ${context.round}` : null].filter(Boolean);
    const status = this.module.options?.show_status === false ? null : context?.status;
    const rawSource = this.module.options?.show_source ? context?.source : null;
    const sourceNames = { live_timing_gridpos: ['GridPos', 'GridPos'], live_timing_qualifying: ['Live qualifying', 'Livekval'], live_timing_archive: ['Archive', 'Arkiv'] };
    const sourceLabel = rawSource ? sourceNames[rawSource] ? this.w(...sourceNames[rawSource]) : String(rawSource).replaceAll('_', ' ') : null;
    if (!details.length && !status && !sourceLabel) return '';
    return html`<p class="module-context">${details.join(' · ')}
      ${status ? html`<span class="provenance">${this.w('Grid status', 'Startuppställningens status')}: ${this.w(({ confirmed: 'Confirmed', provisional: 'Provisional', completed: 'Completed', unavailable: 'Unavailable', pending: 'Pending' })[status] ?? status, ({ confirmed: 'Bekräftad', provisional: 'Preliminär', completed: 'Avslutad', unavailable: 'Uppgift saknas', pending: 'Inväntas' })[status] ?? status)}</span>` : ''}
      ${sourceLabel ? html`<span class="provenance">${this.w('Source', 'Källa')}: ${sourceLabel}</span>` : ''}
    </p>`;
  }
  coverageLine() {
    const coverage = this.model.coverage;
    if (!coverage) return '';
    return html`<p class="module-context">${this.w('Session coverage · all drivers', 'Sessionens underlag · alla förare')}<br>${this.w('Clean laps', 'Rena varv')}: ${coverage.clean_laps ?? '—'} · ${this.w('Recorded', 'Registrerade')}: ${coverage.raw_laps ?? '—'} · ${this.w('Excluded', 'Uteslutna')}: ${coverage.excluded_laps ?? '—'}</p>`;
  }
  choose(key, value) { this.dispatchEvent(new CustomEvent('f1-module-choice', { bubbles: true, composed: true, detail: { module: this.module.id, key, value } })); }
  field(id) {
    const field = fieldDefinition(this.module, id);
    return this.model?.sessionKind === 'sprint_qualifying' && /^q[123]_/.test(id) ? { ...field, label: { en: field.label.en.replace('Q', 'SQ'), sv: field.label.sv.replace('Q', 'SQ') } } : field;
  }
  resultCell(row, id) {
    const type = this.field(id)?.type;
    if (id === 'analysis_source') {
      const names = { f1_live: ['Live timing', 'Livetiming'], f1_replay: ['Recorded replay', 'Inspelad replay'], jolpica: ['Published results', 'Publicerade resultat'], TimingData: ['Timing', 'Timing'], RaceControlMessages: ['Race Control message', 'Race Control-meddelande'], pit_context: ['Pit stop context', 'Depåsammanhang'], pit_state: ['Pit status', 'Depåstatus'], close_gap: ['Small gap', 'Litet avstånd'], consecutive_gap_frames: ['Repeated gap observations', 'Upprepade avståndsobservationer'], penalty_context: ['Penalty context', 'Bestraffningssammanhang'], lap_difference: ['Different laps', 'Olika varv'], track_status: ['Track status', 'Banstatus'], gap_opened: ['Gap increased', 'Avståndet ökade'], SessionStatus: ['Session status', 'Sessionsstatus'], session_finished: ['Session finished', 'Sessionen avslutades'], stint_transition: ['Stint change', 'Stintbyte'], lap_position_before: ['Position before stops', 'Placering före stopp'], lap_position_after: ['Position after stops', 'Placering efter stopp'] };
      return [row.source_provider, ...(row.source_signals ?? [])].filter(Boolean).map(value => names[value] ? this.w(...names[value]) : value).join(' · ') || '—';
    }
    if (type === 'compound_list') return row[id]?.length ? html`<div class="cell-stack">${row[id].map(compound => this.tyreCell(compound))}</div>` : '—';
    if (type === 'driver_paces' || type === 'driver_laps') return row[id]?.length ? html`<ul class="stint-runs">${row[id].map(item => html`<li>${item.driver}: ${type === 'driver_paces' ? formatTime(item.value) : item.value ?? '—'}</li>`)}</ul>` : '—';
    if (type === 'lap_age') return row[id] == null ? '—' : `${new Intl.NumberFormat(this.language, { maximumFractionDigits: 1 }).format(row[id])} ${this.w('laps', 'varv')}`;
    if (type === 'lap_range') return row[id] ? `${row[id].map(value => new Intl.NumberFormat(this.language, { maximumFractionDigits: 1 }).format(value)).join('–')} ${this.w('laps', 'varv')}` : '—';
    if (id === 'pace_leader' && row.equal_pace) return this.w('Equal median pace', 'Samma mediantempo');
    if (type === 'strategy_outcome') {
      const labels = { order_held: ['Order held', 'Ordningen behölls'], undercut_succeeded: ['Undercut observed', 'Observerad undercut'], overcut_succeeded: ['Overcut observed', 'Observerad overcut'] };
      return labels[row[id]] ? this.w(...labels[row[id]]) : row[id] ?? '—';
    }
    if (type === 'battle_status') {
      const states = { active_battle: ['●', 'Active battle estimate', 'Uppskattad pågående närkamp'], battle_started: ['▶', 'Battle started', 'Närkamp började'], battle_ended: ['■', 'Battle ended', 'Närkamp avslutades'], position_exchange: ['↔', 'Position exchange', 'Positionsbyte'], likely_on_track_overtake: ['↑', 'Likely on-track overtake', 'Trolig omkörning på banan'] };
      const signal = states[row[id]];
      return html`<span class="chip"><span aria-hidden="true">${signal?.[0] ?? '·'}</span><span>${signal ? this.w(signal[1], signal[2]) : row[id] ?? '—'}</span></span>`;
    }
    if (type === 'exchange_positions') return row[id]?.length ? html`<ul class="stint-runs">${row[id].map(item => html`<li>${item.driver}: ${item.before ?? '—'} → ${item.after ?? '—'}</li>`)}</ul>` : '—';
    if (type === 'degradation') return row[id] == null ? '—' : html`<span class="time">${formatDelta(row[id])} ${this.w('s/lap', 's/varv')}</span>`;
    if (type === 'reason_counts') return row[id]?.length ? html`<ul class="stint-runs">${row[id].map(item => html`<li>${item.reason.replaceAll('_', ' ')}: ${item.count}</li>`)}</ul>` : '—';
    if (type === 'confidence') return row[id] == null ? '—' : new Intl.NumberFormat(this.language, { style: 'percent', maximumFractionDigits: 0 }).format(row[id]);
    if (type === 'lap_duration') return html`<span class="time">${formatTime(row[id])}</span>`;
    if (type === 'seconds_duration' || type === 'seconds_delta') return row[id] == null ? '—' : html`<span class="time">${type === 'seconds_delta' ? formatDelta(row[id]) : new Intl.NumberFormat(this.language, { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(row[id])} s</span>`;
    if (type === 'points_delta') return row[id] == null ? '—' : html`<span>${row[id] > 0 ? '+' : ''}${new Intl.NumberFormat(this.language, { maximumFractionDigits: 2 }).format(row[id])}</span><span class="provenance">${this.w('points', 'poäng')}</span>`;
    if (type === 'warning_indicator') return row[id] === null ? '—' : row[id] ? html`<span class="chip"><span aria-hidden="true">△</span>${this.w('Warning recorded', 'Varning registrerad')}</span>` : this.w('No warning recorded', 'Ingen varning registrerad');
    if (type === 'penalty_summary') return row[id] ?? (row.penalty_known ? this.w('No penalty recorded', 'Ingen bestraffning registrerad') : '—');
    if (type === 'boolean') return row[id] == null ? '—' : row[id] ? this.w('New', 'Nytt') : this.w('Used', 'Använt');
    if (id === 'event_time') return html`<time datetime=${row.event_time ?? ''}>${dateTime(row.event_time, this.settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>${row.decision_time ? html`<span class="provenance">${this.w('Decision time', 'Beslutstid')}</span>` : ''}`;
    if (id === 'incident_status') {
      const signal = INCIDENT_SIGNALS[row.incident_status];
      return html`<span class="chip"><span aria-hidden="true">${signal?.symbol ?? '·'}</span><span>${label(signal, this.language) || row.incident_status || '—'}</span></span>${row.after_race ? html`<span class="provenance">${this.w('After the race', 'Efter racet')}</span>` : ''}`;
    }
    if (id === 'incident_location' && this.model.trackLimits && row[id]) return `${this.w('Turn', 'Kurva')} ${row[id]}`;
    if (id === 'best_runs') return row.best_runs?.length ? html`<ol class="stint-runs">${row.best_runs.map(run => html`<li><span class="time">${formatTime(run.time)}</span> · ${run.name || run.driver}${run.stint !== null ? html`<span class="provenance">${this.w('Stint', 'Stint')} ${run.stint + 1}${run.new_tyre === true ? this.w(' · new set', ' · nytt set') : run.new_tyre === false ? this.w(' · used set', ' · använt set') : ''}</span>` : ''}</li>`)}</ol>` : '—';
    if (id === 'result_time') return html`<span class="time">${row.result_time ?? '—'}</span>${row.result_status && row.result_status.toLowerCase() !== 'finished' && !this.module.fields.includes('result_status') ? html`<span class="provenance">${row.result_status}</span>` : ''}`;

    if (this.module.type === 'archive' && /^q[123]_time$/.test(id)) return html`<span class="time">${formatTime(row[id])}</span>`;
    if (id === 'qualifying_time') return html`<span class="time">${formatTime(row[id])}</span>`;
    if (id === 'grid_position') return row[id] === 0 ? this.w('Pit lane', 'Depåstart') : row[id] ?? '—';
    if (id === 'grid_delta') {
      const change = row[id];
      if (change == null) return '—';
      return html`<span>${change > 0 ? '+' : ''}${change}</span><span class="provenance">${this.w('from qualifying position', 'från kvalplacering')}</span><span class="sr">${change === 0 ? this.w('unchanged', 'oförändrat') : change > 0 ? this.w('places lost', 'förlorade platser') : this.w('places gained', 'vunna platser')}</span>`;
    }
    if (id === 'position_change') {
      const change = row[id];
      return change ? html`<span>${change.symbol} ${Math.abs(change.value)}</span><span class="provenance">${this.w('from starting grid', 'från startuppställningen')}</span><span class="sr">${this.w(({ gain: 'places gained', loss: 'places lost', equal: 'unchanged' })[change.status], ({ gain: 'vunna platser', loss: 'förlorade platser', equal: 'oförändrat' })[change.status])}</span>` : '—';
    }
    if (id === 'team' && this.model.teams) return this.driverCell({ ...row, driver: row.team, name: row.team });
    return this.cell(row, id);
  }
  tableHeader(fields) {
    const hidden = this.module.show_table_header === false;
    // Keep native column relationships when only the visible labels are hidden.
    return html`<thead part="table-header" class=${hidden ? 'labels-hidden' : ''}><tr part="table-row">${repeat(fields, id => id, id => html`<th part="table-cell" scope="col"><span class=${hidden ? 'sr' : ''}>${label(this.field(id), this.language)}</span></th>`)}</tr></thead>`;
  }
  timingHeader(fields, laps) {
    const hidden = this.module.show_table_header === false;
    return html`<thead part="table-header" class=${hidden ? 'labels-hidden' : ''}><tr part="table-row">
      ${repeat(fields, id => id, id => html`<th part="table-cell" scope="col"><span class=${hidden ? 'sr' : ''}>${label(this.field(id), this.language)}</span></th>`)}
      ${repeat(laps, lap => lap, (lap, index) => html`<th part="table-cell" scope="col" class=${`recent-lap ${index === 0 ? 'lap-start' : ''}`}><span class=${hidden ? 'sr' : ''}>${this.w('Lap', 'Varv')} ${lap}</span></th>`)}
    </tr></thead>`;
  }
  results() {
    const rows = this.model.rows ?? [];
    const fields = this.module.fields.filter(id => moduleFields(this.module).includes(id));
    const selector = this.module.options.show_selector && this.model.choices?.length ? html`<label class="module-picker"><span>${this.w('Round', 'Deltävling')}</span><select aria-label=${this.w('Round', 'Deltävling')} data-focus="result-round" .value=${this.model.selected} @change=${event => this.choose('round', event.target.value)}>${this.model.choices.map(item => html`<option value=${item.id} .selected=${item.id === this.model.selected}>${item.id} · ${item.name}</option>`)}</select></label>` : '';
    if (!rows.length) return html`${selector}${this.empty(this.model.filtered ? this.w('No competitors match this selection.', 'Inga deltagare matchar urvalet.') : this.model.emptyMessage ?? this.w('No data is available for this selection yet.', 'Inga uppgifter finns för urvalet ännu.'))}`;
    if (!fields.length) return this.empty(this.w('Choose columns in the editor.', 'Välj kolumner i editorn.'));
    if (this.module.type === 'results' && this.module.options.presentation === 'grid') return html`${selector}<ol class="result-grid" part="result-grid" aria-label=${this.module.title || this.model.title}>${repeat(rows, row => `${this.model.context?.season}:${this.model.context?.round}:${this.model.context?.session}:${row.id}`, row => html`<li part="result-card" data-driver=${row.id}><dl>${repeat(fields, id => id, id => html`<div><dt>${label(this.field(id), this.language)}</dt><dd>${this.resultCell(row, id)}</dd></div>`)}</dl></li>`)}</ol><p class="muted" style="margin-top:10px">${rows.length} ${this.w('of', 'av')} ${this.model.total} ${this.w('competitors', 'deltagare')}</p>`;
    return html`${selector}<div class="table-scroll" part="table-container" tabindex="0" role="region" aria-label=${`${this.module.title || this.model.title} · ${this.w('scroll horizontally for more columns', 'rulla i sidled för fler kolumner')}`}><table part="table">
      <caption class="sr">${this.module.title || this.model.title}</caption>${this.tableHeader(fields)}
      <tbody>${repeat(rows, row => `${this.model.context?.season}:${this.model.context?.round}:${this.model.context?.session}:${row.id}`, row => html`<tr part="table-row" data-driver=${row.id}>${repeat(fields, id => id, id => html`<td part="table-cell">${row.derived && id === fields[0] ? html`<span class="provenance">${this.w('Derived estimate', 'Härledd uppskattning')}</span>` : ''}${this.resultCell(row, id)}</td>`)}</tr>
      ${this.expanded === row.id ? html`<tr part="table-row"><td part="table-cell" class="details" colspan=${fields.length}><h3>${row.name} · ${row.team ?? '—'}</h3><dl>${fields.filter(id => !['driver', 'team'].includes(id)).map(id => html`<div><dt>${label(this.field(id), this.language)}</dt><dd>${this.resultCell(row, id)}</dd></div>`)}</dl></td></tr>` : ''}`)}</tbody>
    </table></div><div class="section-head" style="margin:10px 0 0"><span class="muted">${rows.length} ${this.w('of', 'av')} ${this.model.total} ${this.model.countKind === 'stints' ? this.w('stints', 'stintar') : this.model.countKind === 'stops' ? this.w('stops', 'stopp') : this.model.countKind === 'compounds' ? this.w('compounds', 'blandningar') : this.model.countKind === 'comparisons' ? this.w('comparisons', 'jämförelser') : this.model.countKind === 'events' ? this.w('events', 'händelser') : this.w('competitors', 'deltagare')}</span>
      ${this.model.total > this.module.options.rows ? html`<button data-focus="result-count" @click=${() => this.choose('rows', rows.length < this.model.total ? (['pit_stops', 'incidents', 'timeline', 'strategy', 'battles'].includes(this.module.type) ? 500 : 100) : this.module.options.rows)}>${rows.length < this.model.total ? this.w('Show all', 'Visa alla') : this.w('Show fewer', 'Visa färre')}</button>` : ''}</div>`;
  }
  strategy() {
    const rows = this.model.rows ?? [], presentation = this.module.options.presentation;
    if (this.module.options.content !== 'stints' || presentation === 'table' || !rows.length) return this.results();
    const valid = rows.filter(row => Number.isInteger(row.stint_first_lap) && Number.isInteger(row.stint_last_lap) && row.stint_first_lap > 0 && row.stint_last_lap >= row.stint_first_lap);
    const first = Math.min(...valid.map(row => row.stint_first_lap)), last = Math.max(...valid.map(row => row.stint_last_lap)), extent = last - first + 1;
    const showTable = presentation === 'both' || this.stintTable;
    return html`<div class="stint-chart"><p class="muted">${this.w('Bars span the first to last observed lap. Missing laps can exist inside a bar; sample counts show the recorded coverage.', 'Staplarna sträcker sig från första till sista observerade varvet. Varv kan saknas inom stapeln; antalet registrerade varv visar täckningen.')}</p>
      <ol class="stint-bars" tabindex="0" aria-label=${this.w('Recorded stint ranges and coverage', 'Registrerade stintintervall och underlag')}>${repeat(rows, row => row.id, row => {
        const drawable = valid.includes(row), compound = compoundMeta(row.tyre);
        const left = drawable ? (row.stint_first_lap - first) / extent * 100 : 0, width = drawable ? (row.stint_last_lap - row.stint_first_lap + 1) / extent * 100 : 0;
        return html`<li data-stint=${row.id}><div class="stint-meta"><strong>${this.settings.appearance.full_names ? row.name : row.driver} · ${this.w('Stint', 'Stint')} ${row.stint_number ?? '—'}</strong>${this.tyreCell(row.tyre)}</div>
          <p>${this.w('Laps', 'Varv')} ${row.stint_first_lap ?? '—'}–${row.stint_last_lap ?? '—'} · ${this.w('Starting tyre age', 'Däckålder vid start')}: ${row.stint_start_age ?? '—'}</p>
          ${drawable ? html`<div class="stint-lane" aria-hidden="true"><span class="stint-bar" style=${`left:${left}%;width:${width}%;--stint-color:${compound.color ?? 'var(--f1-text)'}`}></span></div><div class="stint-axis" aria-hidden="true"><span>${first}</span><span>${last}</span></div>` : html`<p>${this.w('Lap range unavailable', 'Varvintervall saknas')}</p>`}
          <p class="muted">${this.w('Clean', 'Rena')}: ${row.clean_samples ?? '—'} · ${this.w('Recorded', 'Registrerade')}: ${row.raw_samples ?? '—'} · ${this.w('Excluded', 'Uteslutna')}: ${row.excluded_samples ?? '—'}</p></li>`;
      })}</ol></div>
      ${presentation === 'chart' ? html`<button aria-expanded=${String(Boolean(showTable))} aria-controls="stint-data" @click=${() => { this.stintTable = !this.stintTable; }}>${showTable ? this.w('Hide data table', 'Dölj datatabell') : this.w('Show data table', 'Visa datatabell')}</button>` : ''}
      <div id="stint-data">${showTable ? this.results() : html`<p class="muted">${rows.length} ${this.w('of', 'av')} ${this.model.total} ${this.w('stints', 'stintar')}</p>`}</div>`;
  }
  incidents() {
    const rows = this.model.rows ?? [], fields = this.module.fields.filter(id => moduleFields(this.module).includes(id));
    if (!rows.length) return this.empty(this.model.emptyMessage ?? (this.model.filtered ? this.w('No incidents match this selection.', 'Inga incidenter matchar urvalet.') : this.module.type === 'timeline' ? this.w('No recorded events for this session yet.', 'Inga registrerade händelser för sessionen ännu.') : this.w('No recorded incidents for this session.', 'Inga registrerade incidenter för sessionen.')));
    if (!fields.length) return this.empty(this.w('Choose fields in the editor.', 'Välj fält i editorn.'));
    return html`<ol class="events incident-list" tabindex="0" aria-label=${this.module.title || this.model.title}>${repeat(rows, row => row.id, row => html`<li data-event=${row.id}>${row.derived ? html`<p class="chip">${this.w('Derived estimate', 'Härledd uppskattning')}</p>` : ''}<dl>${repeat(fields, id => id, id => html`<div><dt class="muted">${label(this.field(id), this.language)}</dt><dd>${this.resultCell(row, id)}</dd></div>`)}</dl></li>`)}</ol>
      <p class="muted">${rows.length} ${this.w('of', 'av')} ${this.model.total} ${this.w('events', 'händelser')}</p>`;
  }
  documents() {
    const allRows = this.model.rows ?? [], latest = this.module.options.presentation === 'latest';
    const rows = latest ? allRows.slice(0, 1) : allRows;
    if (!rows.length) return this.empty(this.w('No documents match this selection.', 'Inga dokument matchar urvalet.'));
    if (!this.module.fields.length) return this.empty(this.w('Choose fields in the editor.', 'Välj fält i editorn.'));
    const context = this.model.context?.meeting;
    const newTab = this.module.options.open_new_tab;
    return html`<p class="document-summary">
      ${this.module.options.show_fia_logo ? html`<strong class="chip">FIA</strong>` : ''}
      ${this.module.options.show_race_context && context ? html`<span>${context}</span>` : ''}
      ${this.module.options.show_latest_badge ? html`<span class="chip">${this.w('Latest first', 'Senaste först')}</span>` : ''}
      ${this.module.options.show_count ? html`<span>${this.model.total} ${this.w(this.model.total === 1 ? 'document' : 'documents', this.model.total === 1 ? 'dokument' : 'dokument')}</span>` : ''}
    </p><div class="documents-scroll" style=${!latest && this.module.options.list_max_height ? `max-height:${this.module.options.list_max_height}px;overflow:auto` : ''}><ol class="documents">${repeat(rows, row => row.id, row => html`<li class=${this.module.options.document_coloring ? `tone-${documentTone(row.document_title)}` : ''}>
      ${this.module.fields.includes('document_number') && row.document_number ? html`<small>${this.w('Document', 'Dokument')} ${row.document_number}</small>` : ''}
      ${this.module.fields.includes('document_title') ? row.url ? html`<a href=${row.url} target=${newTab ? '_blank' : '_self'} rel=${newTab ? 'noopener noreferrer' : ''}>${this.module.options.show_pdf_icon ? html`<ha-icon icon="mdi:file-pdf-box" aria-hidden="true"></ha-icon>` : ''}${row.document_title}${newTab ? html`<span class="sr"> · ${this.w('opens in a new tab', 'öppnas i en ny flik')}</span>` : ''}</a>` : html`<strong>${row.document_title}</strong><small>${this.w('Document link unavailable', 'Dokumentlänk saknas')}</small>` : ''}
      ${this.module.options.show_document_type ? html`<small class="document-type">${documentType(row.document_title)}</small>` : ''}
      ${this.module.fields.includes('document_time') ? html`<small>${this.w('Published', 'Publicerad')}: ${row.timestamp ? dateTime(row.document_time, this.settings, { dateStyle: 'medium', timeStyle: 'short' }) : row.document_time ?? this.w('not supplied', 'ej angivet')}</small>` : ''}
    </li>`)}</ol></div>`;
  }
  overview() {
    const items = this.model.items ?? [];
    if (!items.length) return this.empty(this.w('Waiting for information.', 'Väntar på information.'));
    return html`<div class="overview ${this.module.options.layout_mode === 'auto' ? '' : this.module.options.layout_mode}" part="metrics">${items.map(item => item.id === 'circuit_map' ? this.circuitMap(item.value) : item.id === 'circuit_history' ? this.circuitHistory(item.value) : html`<div class="metric ${item.id === 'meeting' ? 'hero' : ''}" part="metric">
      <small>${label(FIELDS[item.id], this.language)}</small><div class="metric-value">
      ${item.flag && this.settings.appearance.flags ? html`<img class="flag" src=${item.flag} alt=${item.country ?? ''} width="40" height="27" @error=${event => { event.target.hidden = true; }} @load=${event => { event.target.hidden = false; }}>` : ''}
      <strong>${item.id === 'track_status' ? this.flagCell(item.value) : item.value ?? '—'}</strong></div>${item.detail ? html`<span class="provenance">${item.detail}</span>` : ''}
    </div>`)}</div>`;
  }
  circuitMap(value = {}) {
    return html`<section class="circuit-panel" aria-label=${this.w('Circuit map', 'Bankarta')}><div class="circuit-map">${value.url ? html`<img src=${value.url} alt=${value.circuit ?? this.w('Circuit map', 'Bankarta')} loading="lazy">` : html`<div class="circuit-map-copy"><strong>${value.circuit ?? this.w('Circuit map unavailable', 'Bankarta saknas')}</strong><span class="provenance">${[value.locality, value.country, value.season ? `${this.w('Season', 'Säsong')} ${value.season}` : null].filter(Boolean).join(' · ')}</span></div>`}</div></section>`;
  }
  circuitHistory(value = {}) {
    const percent = number => Number.isFinite(Number(number)) ? `${new Intl.NumberFormat(this.language, { maximumFractionDigits: 1 }).format(Number(number))}%` : null;
    const person = item => item?.driver_name ? `${item.driver_name}${item.constructor_name ? ` · ${item.constructor_name}` : ''}${item.season ? ` · ${item.season}` : ''}` : null;
    const stats = [
      [this.w('Defending winner', 'Regerande vinnare'), person(value.defending_winner)],
      [this.w('Defending pole', 'Regerande pole'), person(value.defending_pole_sitter)],
      [this.w('Races held', 'Antal race'), value.races_held_here],
      [this.w('First F1 race', 'Första F1-race'), value.first_f1_race_here?.season],
      [this.w('Pole to win · last five', 'Pole till seger · senaste fem'), percent(value.pole_to_win_conversion_last_5)],
      [this.w('DNF rate · last five', 'Brutna lopp · senaste fem'), percent(value.dnf_rate_last_5)],
    ].filter(([, content]) => content !== null && content !== undefined && content !== '');
    const lists = [
      [this.w('Recent winners', 'Senaste vinnare'), value.last_5_winners],
      [this.w('Most driver wins here', 'Flest förarsegrar här'), value.top_5_driver_wins_here],
      [this.w('Most constructor wins here', 'Flest konstruktörssegrar här'), value.top_5_constructor_wins_here],
    ].filter(([, rows]) => Array.isArray(rows) && rows.length);
    if (!stats.length && !lists.length && !value.last_year_podium?.podium?.length) return html`<section class="circuit-panel"><p class="empty">${this.w('Circuit history is not available yet.', 'Banhistorik är inte tillgänglig ännu.')}</p></section>`;
    return html`<section class="circuit-panel" aria-label=${this.w('Circuit history', 'Banhistorik')}><div class="history-grid">${stats.map(([title, content]) => html`<div class="history-item"><small>${title}</small><strong>${content}</strong></div>`)}</div>
      ${value.last_year_podium?.podium?.length ? html`<div><h3>${this.w('Last podium', 'Senaste pall')} · ${value.last_year_podium.season ?? ''}</h3><ol class="history-list">${value.last_year_podium.podium.slice(0, 3).map(item => html`<li>${person(item) ?? '—'}</li>`)}</ol></div>` : ''}
      ${lists.map(([title, rows]) => html`<div><h3>${title}</h3><ol class="history-list">${rows.slice(0, 5).map(item => html`<li>${person(item) ?? item.constructor_name ?? item.race_name ?? '—'}${item.wins != null ? ` · ${item.wins}` : ''}</li>`)}</ol></div>`)}</section>`;
  }
  replayAction(action, value) {
    this.dispatchEvent(new CustomEvent('f1-replay-action', { bubbles: true, composed: true, detail: { module: this.module.id, action, value, context: this.model.controlContext } }));
  }
  replay() {
    const model = this.model, fields = this.module.fields, disabled = model.readonly || model.request?.pending;
    const target = this.seekDraft?.context === model.controlContext ? this.seekDraft.value : model.position;
    const stateNames = { idle: ['No replay loaded', 'Ingen replay laddad'], selected: ['Selected · ready to load', 'Vald · klar att ladda'], loading: ['Loading replay', 'Laddar replay'], ready: ['Loaded · ready to play', 'Laddad · klar att spela'], playing: ['Playing', 'Spelar'], paused: ['Paused', 'Pausad'], seeking: ['Seeking', 'Söker'], unknown: ['Replay status unavailable', 'Replaystatus saknas'] };
    const clock = value => value == null ? '—' : `${Math.floor(value / 3600)}:${String(Math.floor(value % 3600 / 60)).padStart(2, '0')}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
    const options = this.module.options, compact = options.display === 'compact';
    const showSecondary = options.secondary_selects && !compact, showStatus = options.status_details && !compact;
    const selectorFields = [...(showSecondary ? [['year', 'Replay year', 'Replayår']] : []), ['session', 'Recorded session', 'Inspelad session'], ...(showSecondary && options.start_reference ? [['reference', 'Start reference', 'Startreferens']] : [])];
    const actionSymbol = { refresh: '↻', load: '↓', play: '▶', pause: 'Ⅱ', stop: '■' };
    const actionLabel = (en, sv) => html`<span class=${options.show_button_labels ? '' : 'sr'}>${this.w(en, sv)}</span>`;
    const send = (action, en, sv, symbol = actionSymbol[action]) => html`<button class=${options.show_button_labels ? '' : 'icon-only'} data-focus=${`replay-${action}`} aria-label=${this.w(en, sv)} title=${this.w(en, sv)} ?disabled=${disabled || !model.allowed[action]} @click=${() => this.replayAction(action)}><span aria-hidden="true">${symbol}</span>${actionLabel(en, sv)}</button>`;
    return html`<p><strong>${model.selectedSession ?? this.w('Choose a recorded session', 'Välj en inspelad session')}</strong><br><span class="chip">${this.w(...stateNames[model.replayState])}</span></p>
      ${showStatus ? html`<p class="muted replay-scope">${this.w(`Controls replay for ${model.scope}. Changes affect every dashboard and the integration’s automation data.`, `Styr replay för ${model.scope}. Ändringar påverkar alla dashboarder och integrationens automationsdata.`)}</p>` : ''}
      ${(fields.includes('replay_transport') || fields.includes('replay_progress')) && model.playerStatus !== 'available' ? html`<p class="muted">${model.playerStatus === 'disabled' ? this.w('Enable the replay player entity in F1 Sensor to use playback controls.', 'Aktivera replay-spelarens entitet i F1 Sensor för att använda uppspelningskontrollerna.') : this.w('Playback controls are unavailable because the replay player has no usable state.', 'Uppspelningskontrollerna är avstängda eftersom replay-spelaren saknar användbar status.')}</p>` : ''}
      ${model.readonly ? html`<p class="muted">${model.frozen ? this.w('Resume the view to use replay controls.', 'Återuppta vyn för att använda replaykontrollerna.') : this.w('Replay controls are disabled in previews.', 'Replaykontroller är avstängda i förhandsvisningar.')}</p>` : ''}
      ${fields.includes('replay_progress') && model.duration !== null ? html`<div class="replay-progress"><span>${this.w('From replay start', 'Från replaystart')}: ${clock(model.position)} / ${clock(model.duration)}</span>
        ${fields.includes('replay_transport') && options.seek_controls ? html`<label><span class="sr">${this.w('Replay position in seconds', 'Replayposition i sekunder')}</span><input data-focus="replay-seek" type="range" aria-label=${this.w('Replay position in seconds', 'Replayposition i sekunder')} min="0" max=${model.duration} step="1" .value=${String(target)} aria-valuetext=${clock(target)} ?disabled=${disabled || !model.allowed.seek} @input=${event => { this.seekDraft = { context: model.controlContext, value: Number(event.target.value) }; }}></label><div class="replay-controls" part="controls"><span>${this.w('Go to', 'Gå till')}: ${clock(target)}</span><button class=${options.show_button_labels ? '' : 'icon-only'} data-focus="replay-apply-seek" aria-label=${this.w('Go to replay position', 'Gå till replayposition')} title=${this.w('Go to replay position', 'Gå till replayposition')} ?disabled=${disabled || !model.allowed.seek || !this.seekDraft || target === model.position} @click=${() => { this.replayAction('seek', target); this.seekDraft = null; }}><span aria-hidden="true">↦</span>${actionLabel('Go to replay position', 'Gå till replayposition')}</button></div>` : html`<progress max=${model.duration} value=${model.position} aria-label=${this.w('Replay progress', 'Replayposition')}></progress>`}
      </div>` : ''}
      ${model.replayState === 'loading' ? html`<div class="replay-progress"><span>${this.w('Download', 'Hämtning')}: ${model.download !== null && model.download >= 0 && model.download <= 100 ? `${model.download}%` : '—'}</span></div>` : ''}
      ${fields.includes('replay_transport') ? html`<div class="replay-controls" part="controls">${model.replayState === 'playing' ? send('pause', 'Pause replay', 'Pausa replay', 'Ⅱ') : send('play', 'Play replay', 'Spela replay', '▶')}
        ${options.seek_controls ? html`<button class=${options.show_button_labels ? '' : 'icon-only'} data-focus="replay-back" aria-label=${this.w('Back 30 s', 'Bakåt 30 s')} title=${this.w('Back 30 s', 'Bakåt 30 s')} ?disabled=${disabled || !model.allowed.seek || model.position <= 0} @click=${() => this.replayAction('seek', Math.max(0, model.position - 30))}><span aria-hidden="true">−30</span>${actionLabel('Back 30 s', 'Bakåt 30 s')}</button>
        <button class=${options.show_button_labels ? '' : 'icon-only'} data-focus="replay-forward" aria-label=${this.w('Forward 30 s', 'Framåt 30 s')} title=${this.w('Forward 30 s', 'Framåt 30 s')} ?disabled=${disabled || !model.allowed.seek || model.position >= model.duration} @click=${() => this.replayAction('seek', Math.min(model.duration, model.position + 30))}><span aria-hidden="true">+30</span>${actionLabel('Forward 30 s', 'Framåt 30 s')}</button>` : ''}
        ${send('stop', 'Stop replay', 'Stoppa replay', '■')}</div>` : ''}
      ${fields.includes('replay_selection') ? html`<details class="analysis-explanation"><summary>${this.w('Choose replay', 'Välj replay')}</summary>
        ${!model.canSelect ? html`<p class="muted">${this.w('Stop the loaded replay before changing its year, session or start reference.', 'Stoppa laddad replay innan du byter år, session eller startreferens.')}</p>` : ''}
        <div class="replay-picker">${selectorFields.map(([id, en, sv]) => {
          const selected = model.selectors[id];
          return html`<label><span>${this.w(en, sv)}</span><select data-focus=${`replay-${id}`} aria-label=${this.w(en, sv)} .value=${selected.state ?? ''} ?disabled=${disabled || !model.allowed[id]} @change=${event => this.replayAction(id, event.target.value)}>
            ${!selected.options.includes(selected.state) ? html`<option value="">${this.w('Choose…', 'Välj…')}</option>` : ''}
            ${selected.options.map(value => html`<option value=${value} .selected=${value === selected.state}>${value}</option>`)}
          </select></label>`;
        })}</div><div class="replay-controls" part="controls">${options.refresh ? send('refresh', 'Refresh session list', 'Uppdatera sessionslistan') : ''}${send('load', 'Load selected replay', 'Ladda vald replay')}</div>
      </details>` : ''}
      ${model.downloadError ? html`<p role="alert">${this.w('The replay download failed. Try loading the selected session again.', 'Hämtningen av replay misslyckades. Försök ladda den valda sessionen igen.')}</p>` : ''}
      ${model.indexError ? html`<p>${this.w('The session list could not be retrieved. Try refreshing it.', 'Sessionslistan kunde inte hämtas. Försök uppdatera den.')}</p>` : ''}
      ${model.request?.pending ? html`<p role="status">${this.w('Sending replay command…', 'Skickar replaykommando…')}</p>` : model.request?.error ? html`<p role="alert">${this.w('The replay command failed. Check the current status before trying again.', 'Replaykommandot misslyckades. Kontrollera aktuell status innan du försöker igen.')}</p>` : model.request?.busy ? html`<p role="status">${this.w('Command not sent: another card was sending a replay command. Check the current status before trying again.', 'Kommandot skickades inte: ett annat kort skickade redan ett replaykommando. Kontrollera aktuell status innan du försöker igen.')}</p>` : ''}
    `;
  }
  weather() {
    const items = this.model.items ?? [];
    if (!items.length) return this.empty(this.w('Choose weather fields in the editor.', 'Välj väderfält i editorn.'));
    const compact = this.module.options.presentation === 'compact_list';
    return html`<dl class=${compact ? 'weather-list' : 'overview'}>${items.map(item => html`<div class=${compact ? 'weather-item' : 'metric weather-item'}>
      <dt>${label(this.field(item.id), this.language)}</dt><dd>${this.weatherValue(item)}${item.detail ? html`<span class="provenance">${item.detail}</span>` : ''}</dd>
    </div>`)}</dl>`;
  }
  weatherValue(item) {
    if (item.value === null) return '—';
    const symbols = this.settings.accessibility.signals !== 'text';
    if (item.type === 'rain_indicator') return item.value ? this.w('Yes · rain detected', 'Ja · regn registrerat') : this.w('No rain detected', 'Inget regn registrerat');
    if (item.type === 'weather_condition') {
      const groups = [
        [[0], 'weather-sunny', 'Clear sky', 'Klar himmel', '#e5a000'], [[1, 2], 'weather-partly-cloudy', 'Partly cloudy', 'Delvis molnigt', '#d59a24'],
        [[3], 'weather-cloudy', 'Overcast', 'Mulet', '#78909c'], [[45, 48], 'weather-fog', 'Fog', 'Dimma', '#78909c'],
        [[51, 53, 55], 'weather-rainy', 'Drizzle', 'Duggregn', '#298fcb'], [[61, 63, 65, 80, 81, 82], 'weather-pouring', 'Rain', 'Regn', '#298fcb'],
        [[56, 57, 66, 67], 'weather-snowy-rainy', 'Freezing precipitation', 'Underkyld nederbörd', '#49a6c7'],
        [[71, 73, 75, 77, 85, 86], 'weather-snowy', 'Snow', 'Snö', '#49a6c7'], [[95, 96, 99], 'weather-lightning-rainy', 'Thunderstorm', 'Åska', '#9975cf'],
      ];
      const group = groups.find(([codes]) => codes.includes(item.value));
      if (!group) return this.w('Unknown condition', 'Okända väderförhållanden');
      const nightIcon = item.night && item.value <= 2;
      const icon = nightIcon ? item.value === 0 ? 'weather-night' : 'weather-night-partly-cloudy' : group[1];
      const color = this.module.options.colored_icons ? nightIcon ? '#8498cf' : group[4] : 'inherit';
      return html`<span class="weather-condition">${symbols ? html`<ha-icon class="weather-symbol" aria-hidden="true" icon=${`mdi:${icon}`} style=${`color:${color}`}></ha-icon>` : ''}<span class="weather-condition-text">${this.w(group[2], group[3])}</span></span>`;
    }
    const value = new Intl.NumberFormat(this.language, { maximumFractionDigits: 1 }).format(item.value);
    return html`${item.type === 'bearing' && symbols ? html`<span class="weather-symbol" aria-hidden="true" style=${`transform:rotate(${item.value}deg)`}>↑</span>` : ''}${value}${item.type === 'bearing' ? '' : ' '}${item.unit ?? ''}`;
  }
  calendar() {
    if (!this.model.rows?.length) return this.empty(this.model.hiddenRows ? this.w('All selected sessions are in the past and are hidden.', 'Alla valda sessioner ligger i det förflutna och är dolda.') : this.w('No published session dates or times are available.', 'Inga publicerade sessionsdatum eller tider finns tillgängliga.'));
    return html`<ol class="schedule">${this.model.rows.map(row => html`<li>
      <div class="schedule-identity">
        ${this.module.options.range === 'season' && row.flag && this.settings.appearance.flags ? html`<span><img class="flag" src=${row.flag} alt=${row.country ?? ''} width="40" height="27" loading="lazy"
          @error=${event => { event.target.hidden = true; event.target.nextElementSibling.hidden = false; }}
          @load=${event => { event.target.hidden = false; event.target.nextElementSibling.hidden = true; }}><span class="flag-fallback" hidden>${row.country ?? ''}</span></span>` : ''}
      <div class="schedule-copy"><strong>${label(row, this.language)}</strong>${this.module.options.range === 'season' ? html`<div class="muted">${row.meeting}</div>` : ''}
        ${this.module.options.details.includes('round') && row.round != null ? html`<div>${this.w('Round', 'Rond')} ${row.round}</div>` : ''}
        ${this.module.options.details.includes('circuit') && row.circuit ? html`<div>${row.circuit}</div>` : ''}
        ${this.module.options.details.includes('location') && row.location ? html`<div>${row.location}</div>` : ''}
        ${row.next && this.module.options.next === 'label' ? html`<span class="badge">${this.w('Next session', 'Nästa session')}</span>` : ''}
        ${row.past && this.module.options.past === 'dim' ? html`<span class="muted">${row.start ? this.w('Start time passed', 'Starttiden har passerat') : this.w('Published date passed', 'Det publicerade datumet har passerat')}</span>` : ''}
      </div></div>
      <div>${row.start ? html`<time datetime=${row.start}>${dateTime(row.start, this.settings, { timeZone: row.display_timezone, weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</time>
      <span class="provenance">${row.timezone_label}</span>${row.track_timezone ? html`<time datetime=${row.start}>${dateTime(row.start, this.settings, { timeZone: row.track_timezone, weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</time><span class="provenance">${this.w('Circuit time', 'Bantid')} · ${row.track_timezone}</span>` : ''}` : html`<time datetime=${row.date}>${dateTime(`${row.date}T00:00:00Z`, this.settings, { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' })}</time>
      <span class="provenance">${this.w('Start time not published', 'Starttid inte publicerad')}</span>`}</div>
    </li>`)}</ol>`;
  }
  timeCell(value) {
    const status = timingStatus(value), signal = SIGNALS[status], colors = statusColors(status, this.settings.mode, this.settings.appearance.palette);
    const signals = this.settings.accessibility.signals;
    return html`<div class="cell-stack"><span class="signal ${status}" style=${`background:${colors.background};color:${colors.color}`}>
      ${signals !== 'text' && status !== 'unknown' ? html`<span aria-hidden="true">${signal.symbol}</span>` : ''}
      <span class="time">${formatTime(value?.time)}</span>
      <span class=${signals === 'shape' ? 'sr' : ''}>${label(signal, this.language)}</span>
    </span>${value?.session_part ? html`<span class="provenance">${this.model.sessionKind === 'sprint_qualifying' ? 'SQ' : 'Q'}${value.session_part}</span>` : ''}${value?.lap ? html`<span class="provenance">${this.w('Lap', 'Varv')} ${value.lap}${status === 'previous' ? this.w(' · previous', ' · föregående') : ''}</span>` : html`<span class="sr">${this.w('Lap unknown', 'Okänt varv')}</span>`}</div>`;
  }
  driverCell(row) {
    const appearance = this.settings.appearance;
    const dimensions = logoDimensions(appearance.logo_size);
    const color = appearance.team_colors && /^#[0-9a-f]{6}$/i.test(row.team_color) ? row.team_color : 'transparent';
    const headshot = appearance.logos && !this.model.teams && this.module.options?.driver_image_type === 'headshot' ? safeImageUrl(row.headshot) : null;
    return html`<button class="driver" data-focus=${`driver-${row.id}`} style=${`--team-color:${color};--f1-logo-frame:${dimensions.frame}px;--f1-logo-image:${dimensions.image}px`} aria-expanded=${this.expanded === row.id ? 'true' : 'false'} @click=${() => { this.expanded = this.expanded === row.id ? '' : row.id; }}>
      ${headshot ? html`<img class="driver-headshot" src=${headshot} alt="" width=${dimensions.frame} height=${dimensions.frame} @error=${event => { event.target.hidden = true; event.target.nextElementSibling.hidden = false; }}><f1-team-logo hidden aria-hidden="true" .team=${row.team} .variant=${appearance.logo_style} .mode=${this.settings.mode} .size=${appearance.logo_size}></f1-team-logo>` : appearance.logos ? html`<f1-team-logo aria-hidden="true" .team=${row.team} .variant=${appearance.logo_style} .mode=${this.settings.mode} .size=${appearance.logo_size}></f1-team-logo>` : ''}
      <span>${appearance.full_names ? row.name : row.driver}<span class="sr"> · ${row.name} · ${row.team ?? ''} · ${this.w('Details', 'Detaljer')}</span></span>
    </button>`;
  }
  tyreCell(value, showName = true) {
    if (!value) return '—';
    const meta = compoundMeta(value), name = label(meta, this.language), style = this.settings.appearance.tyre_style;
    if (style === 'text') return html`<span class=${showName ? '' : 'sr'}>${name}</span>`;
    const image = ['image', 'both'].includes(style) && meta.asset;
    const url = image ? new URL(`../${meta.asset}`, import.meta.url) : null;
    if (url && version) url.searchParams.set('v', version);
    return html`<span class="tyre" role="img" aria-label=${`${this.w('Tyre', 'Däck')} · ${name}`}>
      <span class="compound ${image ? 'image' : ''}" aria-hidden="true" style=${`--compound-color:${meta.color ?? 'currentColor'}`}>
        ${meta.letter}${url ? html`<img src=${url.href} alt="" width="32" height="32" @load=${event => { event.target.hidden = false; }} @error=${event => { event.target.hidden = true; }}>` : ''}
      </span>${style === 'both' && showName ? html`<span aria-hidden="true">${name}</span>` : image ? html`<span class="tyre-letter" aria-hidden="true">${meta.letter}</span>` : ''}
    </span>`;
  }
  flagCell(value) {
    const flag = trackSignal(value);
    return flag ? html`<span class="track-signal"><span class="track-symbol" aria-hidden="true" style=${`background:${flag.color};color:${flag.ink}`}>${flag.symbol}</span><span>${label(flag, this.language)}</span></span>` : value ?? '—';
  }
  cell(row, id) {
    if (id === 'driver') return this.driverCell(row);
    if (this.field(id)?.type === 'qualifying_duration') return html`<span class="time">${formatTime(row[id]?.time)}</span><span class="provenance">${row[id]?.sprint ? 'SQ' : 'Q'}${row[id]?.part}${row[id]?.eliminated ? this.w(' · eliminated', ' · utslagen') : ''}</span>`;
    if (id === 'theoretical_lap') return html`<span class="time">${formatTime(row[id])}</span><span class="provenance">${this.w('Sum of personal-best sectors · may span laps', 'Summan av personbästa sektorer · kan avse olika varv')}</span>`;
    if (FIELDS[id]?.type === 'sector' || FIELDS[id]?.type === 'duration') return this.timeCell(row[id]);
    if (id === 'lap_delta') {
      const delta = row[id];
      return delta ? html`<span class="time">${delta.symbol} ${formatDelta(delta.value)}<span class="sr"> ${this.w(delta.status, { faster: 'snabbare', slower: 'långsammare', equal: 'oförändrat' }[delta.status])}</span></span><span class="provenance">${this.w('vs lap', 'mot varv')} ${delta.reference_lap}</span>` : '—';
    }
    if (id === 'tyre') return this.tyreCell(row.tyre, this.module.type !== 'tyres' || !this.model.statistics || this.module.options.show_compound_name);
    if (id === 'status') return this.w(({ in_pit: 'In pit', pit_out: 'Pit out', retired: 'Retired', stopped: 'Stopped', on_track: 'On track' })[row.status] ?? row.status ?? '—', ({ in_pit: 'I depå', pit_out: 'Ut ur depå', retired: 'Brutit', stopped: 'Stannat', on_track: 'På banan' })[row.status] ?? row.status ?? '—');
    return row[id] ?? '—';
  }
  timing() {
    const rows = this.model.rows ?? [], configuredFields = this.module.fields.filter(id => FIELDS[id]);
    const firstGap = configuredFields.findIndex(id => ['gap', 'interval'].includes(id));
    const showGapToggle = this.module.options.show_gap_toggle === true && firstGap >= 0;
    const fields = showGapToggle ? configuredFields.filter(id => !['gap', 'interval'].includes(id)) : configuredFields;
    if (showGapToggle) {
      const insertion = configuredFields.slice(0, firstGap).filter(id => !['gap', 'interval'].includes(id)).length;
      fields.splice(insertion, 0, this.timingGapMode === 'leader' ? 'gap' : 'interval');
    }
    if (!rows.length) return this.empty(this.model.filtered ? this.w('No drivers match this selection.', 'Inga förare matchar urvalet.') : this.w('Timing will appear when session data is available.', 'Timing visas när det finns sessionsdata.'));
    if (!fields.length) return this.empty(this.w('Choose columns in the editor.', 'Välj kolumner i editorn.'));
    const historyLimit = this.module.options.history;
    const lapNumbers = historyLimit ? [...new Set(rows.flatMap(row => row.history.map(lap => lap.lap)).filter(Number.isInteger))].sort((a, b) => a - b).slice(-historyLimit) : [];
    const gapToggle = showGapToggle ? html`<div class="timing-gap-toggle" part="controls" role="group" aria-label=${this.w('Gap mode', 'Avståndsläge')}>
      <button data-focus="timing-gap-ahead" aria-pressed=${String(this.timingGapMode === 'ahead')} @click=${() => { this.timingGapMode = 'ahead'; }}>${this.w('Ahead', 'Framför')}</button>
      <button data-focus="timing-gap-leader" aria-pressed=${String(this.timingGapMode === 'leader')} @click=${() => { this.timingGapMode = 'leader'; }}>${this.w('Leader', 'Ledaren')}</button>
    </div>` : '';
    return html`${gapToggle}<div class="table-scroll" part="table-container" tabindex="0" role="region" aria-label=${this.w('Timing table, scroll horizontally for more columns', 'Timingtabell, rulla i sidled för fler kolumner')}><table part="table">
      <caption class="sr">${this.module.title || this.model.title}</caption>
      ${this.timingHeader(fields, lapNumbers)}
      <tbody>${repeat(rows, row => row.id, row => html`<tr part="table-row" data-driver=${row.id}>${repeat(fields, id => id, id => html`<td part="table-cell">${this.cell(row, id)}</td>`)}${repeat(lapNumbers, lap => lap, (lap, index) => {
        const value = row.history.find(item => item.lap === lap);
        return html`<td part="table-cell" class=${`recent-lap ${index === 0 ? 'lap-start' : ''}`}>${this.timeCell(value ? { ...value, source: 'completed_lap', previous_lap: true } : { time: null, lap })}</td>`;
      })}</tr>
        ${this.expanded === row.id ? html`<tr part="table-row"><td part="table-cell" class="details" colspan=${fields.length + lapNumbers.length}>
          <h3>${row.name} · ${row.team ?? '—'}</h3><dl>${fields.filter(id => id !== 'driver').map(id => html`<div><dt class="muted">${label(this.field(id), this.language)}</dt><dd>${this.cell(row, id)}</dd></div>`)}</dl>
          ${row.history.length ? html`<h3 style="margin-top:16px">${this.w('Completed laps', 'Avslutade varv')}</h3><ol>${row.history.map(lap => html`<li>${this.w('Lap', 'Varv')} ${lap.lap}: ${formatTime(lap.time)}</li>`)}</ol>` : ''}
        </td></tr>` : ''}`)}</tbody>
    </table></div>${this.timingLegend()}`;
  }
  timingLegend() {
    const meanings = {
      overall: ['Fastest in the relevant session or qualifying part.', 'Snabbast i relevant session eller kvaldel.'],
      personal: ["This driver's best in the relevant comparison.", 'Förarens bästa i den aktuella jämförelsen.'],
      timed: ['Yellow means recorded, not necessarily slower than the previous lap.', 'Gul betyder registrerad, inte nödvändigtvis långsammare än föregående varv.'],
      previous: ['A completed or older lap. Read the lap number beside each time.', 'Ett avslutat eller äldre varv. Läs varvnumret vid respektive tid.'],
      deleted: ['The time has been deleted and cannot be a valid best time.', 'Tiden är raderad och får inte räknas som giltig bästa tid.'],
      invalid: ['The source marks this time as invalid.', 'Källan markerar tiden som ogiltig.'],
      unknown: ['No usable time is available. A dash does not mean zero.', 'Ingen användbar tid finns. Ett tankstreck betyder inte noll.'],
    };
    return html`<details class="timing-legend"><summary data-focus="timing-legend">${this.w('Timing explained', 'Så läser du timing')}</summary>
      <dl>${Object.entries(meanings).map(([status, explanation]) => html`<div><dt><span aria-hidden="true">${SIGNALS[status].symbol} </span><span>${label(SIGNALS[status], this.language)}</span></dt><dd>${this.w(...explanation)}</dd></div>`)}</dl>
      <p>${this.w('Deleted or invalid status takes priority over best-time markings. Older sectors use the previous-lap signal even if they were fastest when recorded.', 'Raderad eller ogiltig status går före bästmarkeringar. Äldre sektorer har signalen för föregående varv även om de var snabbast när de registrerades.')}</p>
      <p>${this.module.options.sectors === 'latest'
        ? this.w('Latest sectors can come from different laps. Each older sector is marked with its own lap; the row is not a completed lap time.', 'Senaste sektorer kan komma från olika varv. Varje äldre sektor märks med sitt eget varv; raden är inte en körd varvtid.')
        : this.w('Sectors follow the same lap. The completed lap stays until the next S1 arrives, then S2 and S3 wait for that new lap.', 'Sektorerna följer samma varv. Det avslutade varvet ligger kvar tills nästa S1 kommer; därefter väntar S2 och S3 på det nya varvet.')}</p>
      <p>${this.w('Lap change: ▼ faster, ▲ slower, = unchanged at the displayed precision, compared with the previous completed lap. Missing comparison data gives no arrow.', 'Varvskillnad: ▼ snabbare, ▲ långsammare, = oförändrat vid visad precision, jämfört med föregående avslutade varv. Saknat jämförelseunderlag ger ingen pil.')}</p>
      <p>${this.w('Personal-best sectors may come from different laps. Their sum is a theoretical lap, not a driven lap. A yellow flag is a separate track status.', 'Personbästa sektorer kan komma från olika varv. Summan är ett teoretiskt varv, inte ett kört varv. Gul flagg är en separat banstatus.')}</p>
    </details>`;
  }
  events() {
    const rows = this.module.options.presentation === 'latest_message' && this.module.options.min_display_time > 0 ? [this.raceShown].filter(Boolean) : this.model.rows ?? [];
    const height = this.module.options.presentation === 'list' ? this.module.options.list_max_height : 0;
    const request = this.model.request, canClear = this.module.options.presentation === 'list' && this.module.options.show_clear_button;
    const controls = canClear ? html`<div class="replay-controls" part="controls"><button data-focus="race-control-clear" ?disabled=${this.model.readonly || request?.pending} @click=${this.clearRaceControl}>${request?.pending ? this.w('Clearing…', 'Tömmer…') : this.clearConfirm ? this.w('Confirm clear', 'Bekräfta tömning') : this.w('Clear saved messages', 'Töm sparade meddelanden')}</button></div>
      ${request?.busy ? html`<p class="muted">${this.w('Another Race Control action is already running.', 'En annan Race Control-åtgärd pågår redan.')}</p>` : request?.error ? html`<p class="muted">${this.w('Saved messages could not be cleared.', 'De sparade meddelandena kunde inte tömmas.')}</p>` : ''}` : '';
    if (!rows.length) return html`${this.module.options.show_fia_logo ? html`<p class="document-summary"><strong class="chip">FIA</strong></p>` : ''}${this.empty(this.w('No matching messages yet.', 'Inga matchande meddelanden ännu.'))}${controls}`;
    return html`${this.module.options.show_fia_logo ? html`<p class="document-summary"><strong class="chip">FIA</strong></p>` : ''}<ol class="events" style=${height ? `max-height:${height}px` : ''} tabindex="0" aria-label="Race Control">${repeat(rows, row => row.id, row => html`<li data-event=${row.id}>
      <div class="event-meta">${this.module.fields.includes('event_time') ? html`<time datetime=${row.utc ?? ''}>${dateTime(row.utc ?? row.received_at, this.settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>` : ''}
      ${row.flag ? this.flagCell(row.flag) : ''}${row.car_number ? html`<span>${this.w('Car', 'Bil')} ${row.car_number}</span>` : ''}<span>${row.category}</span></div>
      ${this.module.fields.includes('message') ? html`<p>${row.message}</p>` : ''}
    </li>`)}</ol>${controls}`;
  }
}
if (!customElements.get('f1-module-view')) customElements.define('f1-module-view', F1ModuleView);

// A keyed image owns its loading/fallback state. Reusing a driver row for a new
// team must not inherit hidden initials or a late image event from the old team.
class F1TeamLogo extends LitElement {
  static properties = { team: {}, variant: {}, mode: {}, size: {}, loaded: { state: true }, failed: { state: true }, useFallback: { state: true } };
  static styles = css`
    :host { display:inline-flex; width:var(--f1-logo-frame,32px); height:var(--f1-logo-frame,32px); flex:0 0 var(--f1-logo-frame,32px); }
    .logo-frame { position:relative; display:flex; align-items:center; justify-content:center; width:100%; height:100%; }
    img { position:absolute; width:var(--f1-logo-image,26px); height:var(--f1-logo-image,26px); object-fit:contain; }
    .initials { font-size:.7em; color:var(--f1-muted); }
    .white { background:#222936; border-radius:5px; }
    .white .initials { color:#e9edf3; }
    .mono img { filter:grayscale(1); }
  `;
  willUpdate() {
    this.dimensions = logoDimensions(this.size);
    const logo = getTeamLogoMeta(this.team, this.dimensions.request, this.variant === 'mono' ? 'white' : this.variant === 'auto' ? 'color' : this.variant, this.mode === 'light');
    this.primary = safeImageUrl(logo?.src); this.fallback = safeImageUrl(logo?.fallback);
    const key = JSON.stringify([this.primary, this.fallback]);
    if (this.imageKey !== key) { this.imageKey = key; this.loaded = false; this.failed = false; this.useFallback = false; }
    this.imageSource = this.useFallback ? this.fallback : this.primary;
  }
  render() {
    const src = this.imageSource, initials = String(this.team ?? '?').trim().split(/\s+/).slice(0, 2).map(word => word[0]).join('') || '?';
    return html`<span class="logo-frame ${/logowhite|logolight/.test(src ?? '') ? 'white' : ''} ${this.variant === 'mono' ? 'mono' : ''}">
      <span class="initials" ?hidden=${this.loaded && !this.failed}>${initials}</span>
      ${repeat(src ? [src] : [], url => url, url => html`<img src=${url} alt="" width=${this.dimensions.image} height=${this.dimensions.image} ?hidden=${this.failed}
        @load=${() => { if (this.imageSource === url) this.loaded = true; }}
        @error=${() => { if (this.imageSource !== url) return; if (!this.useFallback && this.fallback && this.fallback !== url) { this.loaded = false; this.useFallback = true; } else { this.loaded = false; this.failed = true; } }}>`)}
    </span>`;
  }
}
if (!customElements.get('f1-team-logo')) customElements.define('f1-team-logo', F1TeamLogo);
