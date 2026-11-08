const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
let chartLoading, mapLoading, telemetryLoading, teamRadioLoading, tyreHistoryLoading;
const [{ LitElement, html, css, repeat }, { FIELDS, fieldDefinition, moduleFields, moduleFocusKinds, INCIDENT_SIGNALS, label, translatePlural, words }, { formatTime, formatTimingGap, formatDelta, timingStatus, SIGNALS, statusColors, safeImageUrl, compoundMeta, trackSignal, logoDimensions }, { getTeamLogoMeta }, { resolvePresentation }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./catalog.js'), load('./semantics.js'), load('../platform/branding.js'), load('./config.js'),
]);

export { translatePlural, words };
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
  ha-icon.rain-risk-symbol { --mdc-icon-size:1em; vertical-align:-.15em; margin-right:.25em; }
  .rain-risk-details { font-size:.8rem; font-weight:400; line-height:1.5; margin-top:4px; }
  .rain-risk-details summary { width:fit-content; min-height:24px; cursor:pointer; color:var(--f1-muted); }
  .rain-risk-details summary:focus-visible { outline:3px solid var(--f1-focus); outline-offset:3px; }
  .rain-risk-details p { margin:6px 0; }
  .rain-risk-details time { color:var(--f1-muted); }

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
  .minisector-cell { display:flex; flex-direction:column; align-items:stretch; gap:6px; width:max-content; }
  .minisector-cell > .cell-stack { width:100%; align-items:stretch; }
  .minisector-cell .signal { box-sizing:border-box; width:100%; justify-content:center; }
  .minisector-cell .provenance { text-align:center; }
  .minisector-strip { display:inline-flex; align-items:center; gap:3px; min-width:max-content; min-height:22px; padding:2px 0; }
  .minisector-block { width:11px; height:20px; flex:0 0 11px; display:grid; place-items:center; border:1px solid color-mix(in srgb,currentColor 45%,transparent); border-radius:4px; font-size:7px; line-height:1; font-weight:900; }
  .minisector-block[data-status=overall] .minisector-mark { transform:rotate(45deg); }
  .minisector-block[data-status=unset],.minisector-block[data-status=special],.minisector-block[data-status=unknown] { background:var(--f1-panel)!important; color:var(--f1-muted)!important; }
  .minisector-empty { color:var(--f1-muted); }
  .minisector-legend { display:flex; flex-wrap:wrap; gap:8px 16px; margin:8px 0 0; padding:0; list-style:none; }
  .minisector-legend li { display:flex; align-items:center; gap:6px; }
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
  .timing-detail-actions { display:flex; justify-content:flex-end; margin-bottom:8px; }
  .push-label { display:block; font-size:.8em; font-weight:650; white-space:nowrap; }
  .push-result { display:block; font-variant-numeric:tabular-nums; }
  .push-delta { display:block; width:max-content; margin-top:4px; padding:2px 0; color:var(--f1-text); font-size:.85em; font-weight:700; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .push-delta.unknown { color:var(--f1-muted); padding-inline:0; }
  .push-delta-reference { display:block; max-width:22ch; margin-top:4px; color:var(--f1-muted); font-size:.75em; font-weight:400; white-space:normal; }
  tr[data-push-group=active] > td:first-child { border-left:3px solid var(--f1-focus,#56aaff); }
  .push-group th { text-align:left; background:var(--f1-panel); padding:8px 12px; font-size:.85em; white-space:normal; }
  .push-group .provenance { display:block; font-weight:400; }
  .timing-detail-row > td { padding:0; white-space:normal; background:var(--f1-panel); }
  .timing-detail { min-width:0; padding:14px; border-left:4px solid var(--team-color,var(--f1-border)); }
  .timing-detail-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:12px; }
  .timing-detail dl { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,135px),1fr)); gap:12px; margin:0; }
  .timing-detail dt { color:var(--f1-muted); font-size:.85em; }
  .timing-detail dd { margin:2px 0 0; overflow-wrap:anywhere; }
  .timing-detail ol { margin:6px 0 0; padding-left:22px; }
  .timing-position { display:inline-flex; align-items:center; gap:7px; }
  .position-change { display:inline-block; min-width:2.5em; font-size:.8em; color:var(--f1-muted); }
  .position-change.gain { color:var(--f1-gain,#176b36); }
  .position-change.loss { color:var(--f1-loss,#ab2424); }
  :host([data-mode=dark]) { --f1-gain:#75dc94; --f1-loss:#ffb3b3; }
  .driver-badges { display:inline-flex; align-items:center; flex-wrap:wrap; gap:4px; }
  .driver-badge { display:inline-block; padding:1px 5px; border:1px solid var(--f1-divider); border-radius:4px; font-size:.72em; line-height:1.4; font-weight:700; color:var(--f1-text); background:var(--f1-panel); }
  .driver-badge[data-kind=time_penalty],.driver-badge[data-kind=drive_through],.driver-badge[data-kind=stop_go] { color:#745900; background:#fff3c4; }
  .driver-badge[data-kind=in_pit],.driver-badge[data-kind=pit_out] { color:#005db5; background:#e5f1ff; }
  :host([data-mode=dark]) .driver-badge[data-kind=time_penalty],:host([data-mode=dark]) .driver-badge[data-kind=drive_through],:host([data-mode=dark]) .driver-badge[data-kind=stop_go] { color:#f6d65c; background:#3c3218; }
  :host([data-mode=dark]) .driver-badge[data-kind=in_pit],:host([data-mode=dark]) .driver-badge[data-kind=pit_out] { color:#a4d0ff; background:#1b3554; }
  tr[data-retired=true] > td { color:var(--f1-muted); }
  tr[data-retired=true] .driver { font-weight:500; }
  :host([data-presentation=minimal]) tr[data-retired=true] .signal { color:var(--f1-muted)!important; }
  tr[data-retired=true] .compound,tr[data-retired=true] .driver { filter:grayscale(1); }
  .gap-stack { display:flex; flex-direction:column; gap:0; align-items:flex-end; line-height:1.35; font-variant-numeric:tabular-nums; }
  .gap-stack .secondary { color:var(--f1-muted); font-size:.8em; }
  .timing-decisions { list-style:none; padding:0; margin:10px 0 0; }
  .timing-decisions li { padding:5px 0; overflow-wrap:anywhere; }
  .timing-decisions small { display:block; color:var(--f1-muted); }
  .driver-disclosure { --mdc-icon-size:16px; flex:0 0 16px; }
  .tyre-inline { display:inline-grid; width:100%; grid-template-columns:minmax(max-content,1fr) minmax(2ch,max-content); align-items:center; gap:5px; font-variant-numeric:tabular-nums; }
  .tyre-inline > :last-child { text-align:end; }
  :host([data-presentation=minimal]) { font-size:max(.875rem,14px); }
  :host([data-presentation=minimal]) h2 { font-size:1.07em; font-weight:600; }
  :host([data-presentation=minimal][data-auto-font=true]) h2 { font-family:var(--ha-font-family-heading,var(--ha-font-family-body,inherit)); text-transform:none; }
  :host([data-presentation=minimal]) .section-head { margin-bottom:8px; }
  :host([data-presentation=minimal]) .module-context { margin-bottom:8px; }
  :host([data-presentation=minimal]) .empty { padding:12px 10px; border-radius:6px; }
  :host([data-presentation=minimal]) .chip { border:0; padding:0; color:var(--f1-muted); }
  :host([data-presentation=minimal]) .table-scroll { border:0; border-radius:0; scrollbar-gutter:auto; }
  :host([data-presentation=minimal]) th { background:transparent; }
  :host([data-presentation=minimal]) th,:host([data-presentation=minimal]) .provenance { font-size:.857em; }
  :host([data-presentation=minimal]) th,:host([data-presentation=minimal]) td { padding:4px 8px; }
  :host([data-presentation=minimal]) [data-field] { text-align:right; }
  :host([data-presentation=minimal]) [data-field=driver],:host([data-presentation=minimal]) [data-field=position],:host([data-presentation=minimal]) [data-field=team] { text-align:left; }
  :host([data-presentation=minimal]) .cell-stack { align-items:flex-end; gap:0; }
  :host([data-presentation=minimal]) :is([data-field-type=text],[data-field-type=status],[data-field-type=battle_status],[data-field-type=incident_status],[data-field-type=strategy_outcome],[data-field-type=exchange_positions],[data-field-type=reason_counts],[data-field-type=driver_paces],[data-field-type=driver_laps],[data-field-type=penalty_summary],[data-field-type=warning_indicator]) { text-align:left; }
  :host([data-presentation=minimal]) :is([data-field-type=text],[data-field-type=status],[data-field-type=battle_status],[data-field-type=incident_status],[data-field-type=strategy_outcome],[data-field-type=penalty_summary]) { white-space:normal; overflow-wrap:anywhere; }
  :host([data-presentation=minimal]) :is([data-field-type=text],[data-field-type=status],[data-field-type=incident_status]) .cell-stack { align-items:flex-start; }

  :host([data-presentation=minimal]) .compact-minisectors td[data-field] { vertical-align:top; }
  :host([data-presentation=minimal]) .minisector-cell { margin-inline-start:auto; gap:2px; }
  :host([data-presentation=minimal]) .minisector-cell .signal { justify-content:flex-end; }
  :host([data-presentation=minimal]) .minisector-cell .provenance { text-align:end; }
  :host([data-presentation=minimal]) .minisector-strip { min-height:6px; padding:0; gap:1px; justify-content:flex-end; }
  :host([data-presentation=minimal]) .minisector-strip > .minisector-block { width:6px; height:6px; flex-basis:6px; border-radius:1px; font-size:4px; }
  :host([data-presentation=minimal]) .minisector-empty { display:block; min-height:6px; line-height:6px; font-size:.75em; text-align:end; }
  :host([data-presentation=minimal]) .signal { border:0; padding:0; border-radius:0; gap:3px; }
  :host([data-presentation=minimal]) .signal > span[aria-hidden] { font-size:.7em; }
  :host([data-presentation=minimal]) .driver { min-height:28px; min-width:0; gap:6px; padding:0 5px; font-weight:500; }
  :host([data-presentation=minimal]) .compound,:host([data-presentation=minimal]) .compound img { width:20px; height:20px; }
  :host([data-presentation=minimal]) .compound { flex-basis:20px; border-width:2px; font-size:.75em; }
  :host([data-presentation=minimal]) .driver-headshot { width:22px; height:22px; }
  :host([data-presentation=minimal]) .timing-detail-row > td { padding:0; background:transparent; }
  :host([data-presentation=minimal]) .timing-detail { padding:10px 8px; border-left-width:2px; }
  :host([data-presentation=minimal]) .timing-detail dl { gap:8px; }
  :host([data-presentation=minimal]) .timing-detail-heading { margin-bottom:6px; }
  :host([data-presentation=minimal]) .overview { gap:8px 16px; }
  :host([data-presentation=minimal]) .metric.weather-item dt { font-size:.857em; margin-bottom:3px; }
  :host([data-presentation=minimal]) .metric.weather-item dd { font-size:1em; line-height:1.45; font-weight:500; }
  :host([data-presentation=minimal]) .metric.weather-item .provenance { font-size:.857em; }
  :host([data-presentation=minimal]) .weather-item dd { font-weight:500; }
  :host([data-presentation=minimal]) .weather-list .weather-item { padding:6px 0; gap:4px 14px; }
  :host([data-presentation=minimal]) .analysis-explanation { margin-top:8px; }
  :host([data-presentation=minimal]) .analysis-explanation summary { min-height:28px; padding:4px 0; }
  :host([data-presentation=minimal]) h3 { font-weight:600; }
  :host([data-presentation=minimal]) .metric small { font-size:.857em; margin-bottom:2px; }
  :host([data-presentation=minimal]) .metric strong { font-size:1.07em; line-height:1.4; font-weight:500; }
  :host([data-presentation=minimal]) .metric.hero strong { font-size:1.15rem; letter-spacing:0; }
  :host([data-presentation=minimal]) .metric-value { gap:8px; }
  :host([data-presentation=minimal]) .metric.hero:has(.flag:not([hidden])) > small { margin-inline-start:36px; }
  :host([data-presentation=minimal]) .flag { width:28px; height:19px; flex-basis:28px; margin-top:2px; }
  :host([data-presentation=minimal]) .circuit-panel { gap:8px; }
  :host([data-presentation=minimal]) .history-item { padding:7px 8px; border-radius:4px; }
  :host([data-presentation=minimal]) .track-signal { font-size:1em; gap:6px; }
  :host([data-presentation=minimal]) .track-symbol { min-width:22px; padding:0 3px; font-size:.857em; }
  :host([data-presentation=minimal]) .schedule li { gap:6px 12px; padding:7px 0; }
  :host([data-presentation=minimal]) .schedule-identity { gap:8px; }
  :host([data-presentation=minimal]) .schedule strong,:host([data-presentation=minimal]) .schedule time { font-weight:500; }
  :host([data-presentation=minimal]) .result-grid { gap:8px; }
  :host([data-presentation=minimal]) .result-grid li { border:0; border-bottom:1px solid var(--f1-divider); border-radius:0; padding:8px; }
  :host([data-presentation=minimal]) .result-grid dl { gap:4px 8px; }
  :host([data-presentation=minimal]) .result-grid dt { font-size:.857em; }
  :host([data-presentation=minimal]) .details { padding:8px; }
  :host([data-presentation=minimal]) .details dl { gap:8px; }
  :host([data-presentation=minimal]) .details dt { font-size:.857em; color:var(--f1-muted); }
  :host([data-presentation=minimal]) .incident-list li { border-left:0; border-bottom:1px solid var(--f1-divider); margin:0; padding:8px 0; }
  :host([data-presentation=minimal]) .incident-list dl { gap:4px 16px; }
  :host([data-presentation=minimal]) .incident-list dt { font-size:.857em; }
  :host([data-presentation=minimal]) .stint-chart { margin-bottom:8px; }
  :host([data-presentation=minimal]) .stint-chart > p { margin-bottom:8px; }
  :host([data-presentation=minimal]) .stint-bars li { margin-bottom:8px; padding:8px; border:0; border-bottom:1px solid var(--f1-divider); border-radius:0; }
  :host([data-presentation=minimal]) .stint-meta strong { font-weight:500; }
  :host([data-presentation=minimal]) .stint-axis { font-size:.857em; }
  :host([data-presentation=minimal]) .strategy-evidence { margin-bottom:8px; font-size:1em; }
  :host([data-presentation=minimal]) .strategy-evidence summary { min-height:28px; padding:4px 0; cursor:pointer; }
  :host([data-presentation=minimal]) .strategy-evidence summary:focus-visible { outline:3px solid var(--f1-focus); outline-offset:3px; }
  :host([data-presentation=minimal]) .documents li { padding:7px 0; }
  :host([data-presentation=minimal]) .documents li[class^="tone-"] { padding-left:8px; }
  :host([data-presentation=minimal]) .documents a,:host([data-presentation=minimal]) .documents strong { font-weight:500; }
  :host([data-presentation=minimal]) .documents small { font-size:.857em; }
  :host([data-presentation=minimal]) .documents .document-type { font-size:.857em; font-weight:500; border:0; padding:0; border-radius:0; }
  :host([data-presentation=minimal]) .document-summary { gap:4px 10px; margin-bottom:4px; font-size:.857em; }
  :host([data-presentation=minimal]) .module-picker { margin-bottom:8px; }
  :host([data-presentation=minimal]) .archive-pickers { gap:0 8px; }
  :host([data-presentation=minimal]) .replay-scope { margin:6px 0 8px; }
  :host([data-presentation=minimal]) .replay-controls { gap:6px; margin:8px 0; }
  :host([data-presentation=minimal]) .replay-controls button { padding:6px 10px; }
  :host([data-presentation=minimal]) .replay-picker { gap:8px; margin:8px 0; }
  :host([data-presentation=minimal]) .replay-progress { gap:4px; }
  .compact-events > li { display:grid; grid-template-columns:minmax(0,1fr); gap:6px 10px; border-left:0; border-bottom:1px solid var(--f1-divider); margin:0; padding:7px 0; }
  .compact-events > li.has-time { grid-template-columns:5.2em minmax(0,1fr); }
  .compact-events > li:last-child { border-bottom:0; }
  .compact-event-time { color:var(--f1-muted); font-size:.857em; font-variant-numeric:tabular-nums; padding-top:1px; }
  .compact-event-content { min-width:0; }
  .compact-event-message { font-weight:400; line-height:1.45; overflow-wrap:anywhere; }
  .compact-event-meta { display:flex; flex-wrap:wrap; align-items:baseline; gap:3px 8px; margin-top:3px; font-size:.857em; color:var(--f1-muted); }
  .compact-event-meta .track-signal { font-size:1em; gap:5px; }
  .compact-event-meta .track-symbol { min-width:20px; padding:0 3px; }
  .compact-event-details summary { cursor:pointer; min-height:24px; padding:0; color:var(--f1-focus); }
  .compact-event-details summary:focus-visible { outline:3px solid var(--f1-focus); outline-offset:3px; }
  .compact-event-timestamp { display:block; margin:3px 0; color:var(--f1-muted); }
  .timing-summary th,.timing-summary td { padding:4px 6px; }
  .timing-summary .driver { min-height:36px; }
  .timing-summary .driver-badges { max-width:8em; }
  @media (pointer:coarse) {
    :host([data-presentation=minimal]) .driver,.timing-summary .driver { min-height:44px; }
    :host([data-presentation=minimal]) button.driver,.timing-summary button.driver { min-width:44px; }
    :host([data-presentation=minimal]) .analysis-explanation summary,:host([data-presentation=minimal]) .strategy-evidence summary,.compact-event-details summary { min-height:44px; padding-block:10px; }
  }
  @media (forced-colors:active) {
    .driver-badge { color:CanvasText!important; background:Canvas!important; border-color:CanvasText; }
    .position-change { color:CanvasText!important; }
  }
  @media (prefers-reduced-motion:reduce) { *,*::before,*::after { animation:none!important; transition:none!important; scroll-behavior:auto!important; } }
  @media (forced-colors:active) { :host,ha-card { --f1-surface:Canvas!important; --f1-panel:Canvas!important; --f1-text:CanvasText!important; --f1-muted:CanvasText!important; --f1-border:CanvasText!important; --f1-divider:GrayText!important; --f1-focus:Highlight!important; } :host,ha-card { color:CanvasText!important; background:Canvas!important; } .signal,.chip,.compound,.track-symbol,.minisector-block { forced-color-adjust:auto; border-color:CanvasText!important; color:CanvasText!important; background:Canvas!important; } button { border:1px solid ButtonText; } .driver { border-left-color:CanvasText; } .muted,th,.provenance,.event-meta { color:CanvasText; } }
`;

export class F1ModuleView extends LitElement {
  static properties = { module: { attribute: false }, model: { attribute: false }, settings: { attribute: false }, expanded: { state: true }, timingExpanded: { state: true }, stintTable: { state: true }, seekDraft: { state: true }, syncDraft: { state: true }, clearConfirm: { state: true }, timingGapMode: { state: true } };
  static styles = sharedStyles;
  constructor() { super(); this.expanded = ''; this.timingExpanded = []; this.clearConfirm = false; this.raceQueue = []; }
  disconnectedCallback() {
    super.disconnectedCallback(); clearTimeout(this.raceTimer); clearTimeout(this.clearTimer);
    // Hidden/disabled nodes are reused by the card. They must not retain a
    // Race Trace snapshot while source/protection updates bypass their render.
    // Lit also disconnects nodes while moving them within the same render.
    queueMicrotask(() => {
      if (!this.isConnected && this.model?.metric === 'cumulative_lap_delta') this.model = null;
    });
  }
  get language() { return this.settings?.language ?? 'en'; }
  get compactPresentation() { return resolvePresentation(this.settings?.appearance, this.module) === 'compact'; }
  get minimalTiming() { return ['timing', 'minisectors'].includes(this.module?.type) && this.compactPresentation; }
  w(source, replacements = {}) { return words(this.language, source, replacements); }
  willUpdate() {
    if (this.seekDraft && this.seekDraft.context !== this.model?.controlContext) this.seekDraft = null;
    if (this.syncDraft && this.syncDraft.context !== this.model?.controlContext) this.syncDraft = null;
    if (this.module?.type === 'timing') {
      const context = JSON.stringify([this.module.id, this.model?.context?.key, this.model?.selectionGeneration]);
      let selectionCleared = false;
      if (context !== this.timingSelectionContext) {
        this.timingSelectionContext = context;
        selectionCleared = this.timingExpanded.length > 0;
        this.timingExpanded = [];
      }
      const visible = new Set((this.model?.rows ?? []).map(row => row.id));
      const detailsDisabled = this.module.options?.show_driver_details === false && !this.module.options?.narrow_layout;
      if (detailsDisabled || this.timingExpanded.some(id => !visible.has(id))) {
        const kept = detailsDisabled ? [] : this.timingExpanded.filter(id => visible.has(id));
        selectionCleared ||= kept.length !== this.timingExpanded.length;
        this.timingExpanded = kept;
      }
      if (selectionCleared) queueMicrotask(() => { if (this.isConnected) this.dispatchEvent(new CustomEvent('f1-driver-details-change', { bubbles: true, composed: true })); });
    }
    const configuredGap = this.module?.fields?.includes('interval') ? 'ahead' : this.module?.fields?.includes('gap') ? 'leader' : '';
    const timingGapContext = `${this.module?.id ?? ''}|${configuredGap}|${this.module?.options?.show_gap_toggle === true}`;
    if (timingGapContext !== this.timingGapContext) {
      this.timingGapContext = timingGapContext;
      this.timingGapMode = configuredGap || 'ahead';
    }
    this.syncRaceControlMessage();
    this.setAttribute('density', this.settings?.appearance?.density ?? 'comfortable');
    this.setAttribute('data-presentation', this.compactPresentation ? 'minimal' : 'current');
    this.setAttribute('data-auto-font', String(this.settings?.configuredFont === 'auto'));
    this.setAttribute('data-mode', this.settings?.mode ?? 'dark');
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
      const target = [...this.shadowRoot.querySelectorAll('[data-focus]')].find(node => node.dataset.focus === this.focusKey)
        ?? (this.focusKey === 'timing-close-all' ? this.shadowRoot.querySelector('tbody button.driver') : null);
      target?.focus({ preventScroll: true });
    }
  }
  render() {
    if (!this.module || !this.model) return html``;
    const title = this.module.title || this.model.title;
    return html`<section part="module-content" aria-label=${title}>
      ${this.module.show_header !== false || this.model.badge ? html`<div class="section-head" part="module-header"><h2 part="module-title" class=${this.module.show_header === false ? 'sr' : ''}>${title}</h2>${this.model.badge ? html`<span class="chip" part="module-badge">${words(this.language, this.model.badge, this.model.badge)}</span>` : ''}</div>` : html`<h2 class="sr" part="module-title">${title}</h2>`}
      ${this.module.focus_mode === 'independent' && moduleFocusKinds(this.module).length ? html`<p class="muted module-focus">${this.w('modular.own_selection')}</p>` : ''}
      ${this.model.blocked ? this.empty(this.model.blocked) : html`${this.contextLine()}${this.coverageLine()}${this.content()}`}
      ${this.module.options.show_explanation !== false && this.model.explanation ? html`<details class="analysis-explanation"><summary>${this.model.explanationTitle ?? this.w('modular.about_this_analysis')}</summary><p class="muted">${this.model.explanation}</p></details>` : ''}
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
      case 'minisectors': return this.timing();
      case 'tyres': return this.module.options.content === 'history' ? this.tyreHistory() : this.results();
      case 'results': case 'standings': case 'pit_stops': return this.results();
      case 'strategy': return this.strategy();
      case 'battles': case 'timeline': case 'incidents': return this.model.summary || this.module.options.presentation === 'table' ? this.results() : this.incidents();
      case 'documents': return this.documents();
      case 'progression': case 'lap_chart': return this.chart();
      case 'map': return this.map();
      case 'replay': return this.replay();
      case 'archive': return this.archive();
      case 'telemetry': return this.telemetry();
      case 'team_radio': return this.teamRadio();
      case 'race_control': return this.events();
      default: return this.empty(this.w('modular.this_module_needs_a_newer_card_version_its_settings_are_preserved'));
    }
  }
  tyreHistory() {
    if (!this.tyreHistoryNode) {
      this.tyreHistoryNode = document.createElement('f1-tyre-history-view');
      this.tyreHistoryNode.setAttribute('part', 'tyre-history');
      tyreHistoryLoading ??= load('./tyre-history-view.js').catch(error => { tyreHistoryLoading = null; throw error; });
      tyreHistoryLoading.catch(() => { this.tyreHistoryError = true; this.requestUpdate(); });
    }
    if (this.tyreHistoryError) return this.empty(this.w('modular.this_module_needs_a_newer_card_version_its_settings_are_preserved'));
    this.tyreHistoryNode.module = this.module; this.tyreHistoryNode.model = this.model; this.tyreHistoryNode.settings = this.settings;
    this.tyreHistoryNode.presentation = this.compactPresentation ? 'compact' : 'current';
    return this.tyreHistoryNode;
  }
  map() {
    if (!this.mapNode) {
      this.mapNode = document.createElement('f1-track-map-view');
      this.mapNode.setAttribute('part', 'map');
      mapLoading ??= load('./map-view.js').catch(error => { mapLoading = null; throw error; });
      mapLoading.catch(() => { this.mapError = true; this.requestUpdate(); });
    }
    if (this.mapError) return this.empty(this.w('modular.the_map_could_not_be_loaded_reload_this_dashboard_to_try_again'));
    this.mapNode.model = this.model; this.mapNode.module = this.module; this.mapNode.settings = this.settings;
    this.mapNode.presentation = this.compactPresentation ? 'compact' : 'current';
    return this.mapNode;
  }
  chart() {
    if (!this.module.fields.includes(['lap_chart', 'archive'].includes(this.module.type) ? 'lap_series' : 'progression')) return this.empty(this.w('modular.choose_fields_in_the_editor'));
    if (!this.chartNode) {
      this.chartNode = document.createElement('f1-series-chart');
      this.chartNode.setAttribute('part', 'chart');
      chartLoading ??= load('./chart.js').catch(error => { chartLoading = null; throw error; });
      chartLoading.catch(() => { this.chartError = true; this.requestUpdate(); });
    }
    if (this.chartError) return this.empty(this.w('modular.the_chart_could_not_be_loaded_reload_this_dashboard_to_try_again'));
    this.chartNode.model = this.model; this.chartNode.module = this.module; this.chartNode.settings = this.settings;
    this.chartNode.presentation = this.compactPresentation ? 'compact' : 'current';
    return this.chartNode;
  }
  telemetry() {
    if (!this.telemetryNode) {
      this.telemetryNode = document.createElement('f1-telemetry-view');
      this.telemetryNode.setAttribute('part', 'telemetry');
      telemetryLoading ??= load('./telemetry-view.js').catch(error => { telemetryLoading = null; throw error; });
      telemetryLoading.catch(() => { this.telemetryError = true; this.requestUpdate(); });
    }
    if (this.telemetryError) return this.empty(this.w('modular.telemetry_view_could_not_be_loaded_reload_the_dashboard'));
    this.telemetryNode.model = this.model; this.telemetryNode.module = this.module; this.telemetryNode.settings = this.settings;
    this.telemetryNode.presentation = this.compactPresentation ? 'compact' : 'current';
    return this.telemetryNode;
  }
  teamRadio() {
    if (!this.teamRadioNode) {
      this.teamRadioNode = document.createElement('f1-team-radio-view');
      this.teamRadioNode.setAttribute('part', 'team-radio');
      teamRadioLoading ??= load('./team-radio-view.js').catch(error => { teamRadioLoading = null; throw error; });
      teamRadioLoading.catch(() => { this.teamRadioError = true; this.requestUpdate(); });
    }
    if (this.teamRadioError) return this.empty(this.w('modular.team_radio_view_could_not_be_loaded_reload_the_dashboard'));
    this.teamRadioNode.model = this.model; this.teamRadioNode.module = this.module; this.teamRadioNode.settings = this.settings;
    this.teamRadioNode.presentation = this.compactPresentation ? 'compact' : 'current';
    return this.teamRadioNode;
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
    if (selectedRound && !meetingChoices.some(([id]) => id === selectedRound)) meetingChoices.push([selectedRound, `${selectedRound} · ${this.w('modular.saved_selection_unavailable')}`]);
    if (selectedSession && !sessionChoices.some(([id]) => id === selectedSession)) sessionChoices.push([selectedSession, this.w('modular.saved_session_unavailable')]);
    const errorMessage = model.disconnected ? this.w('modular.home_assistant_is_disconnected_the_archive_will_reload_after_reconnection') : model.error ? this.w('modular.the_archive_could_not_be_loaded_try_again_when_the_source_is_available') : null;
    const showPicker = options.show_session_selector || this.archivePickerOpen;
    return html`${showPicker ? html`<div class="archive-pickers">
      ${picker('year', this.w('modular.year'), model.year, years)}
      ${picker('round', this.w('modular.grand_prix'), selectedRound, [['', this.w('modular.latest_started_event')], ...meetingChoices])}
      ${picker('session_key', this.w('modular.session'), selectedSession, [['', this.w('modular.latest_supported_session')], ...sessionChoices])}
    </div>` : ''}
    ${model.session?.cancelled === true ? html`<p class="provenance">${this.w('modular.archive_session_cancelled')}</p>` : ''}
    ${errorMessage ? html`${this.empty(errorMessage)}${!model.disconnected ? html`<button @click=${() => this.choose('retry', true)}>${this.w('modular.retry_archive')}</button>` : ''}`
      : model.loading ? this.empty(this.w('modular.loading_archive'))
      : !model.session ? html`${this.empty(this.w('modular.no_session_matches_this_selection_choose_another_event_or_session'))}
        ${!showPicker && model.sessions.length ? html`<button @click=${async () => {
          this.archivePickerOpen = true; this.requestUpdate();
          await this.updateComplete;
          this.renderRoot.querySelector('[data-focus="archive-session_key"]')?.focus();
        }}>${this.w('modular.choose_a_recorded_session')}</button>` : ''}`
      : model.unsupported ? this.empty(options.content === 'classification' ? this.w('modular.this_source_provides_race_sprint_and_qualifying_results_results_for_this_session_are_unavailable') : this.w('modular.historical_lap_times_and_positions_are_available_for_races_only'))
      : model.invalidIdentity ? this.empty(this.w('modular.the_returned_lap_data_belongs_to_a_different_session_reload_the_archive'))
      : model.invalidRange ? this.empty(this.w('modular.the_first_lap_is_after_the_last_lap_adjust_the_range_in_the_editor'))
      : options.content === 'classification' ? this.results() : this.chart()}`;
  }
  contextLine() {
    const context = this.model.context;
    if (!context) return '';
    const details = this.module.options?.show_context === false ? [] : [context?.meeting, context?.session ? words(this.language, context.session) : null, context?.season, context?.round ? `${this.w('modular.round')} ${context.round}` : null].filter(Boolean);
    const status = this.module.options?.show_status === false ? null : context?.status;
    const rawSource = this.module.options?.show_source ? context?.source : null;
    const sourceNames = { live_timing_gridpos: 'GridPos', live_timing_qualifying: 'Live qualifying', live_timing_archive: 'Archive' };
    const sourceLabel = rawSource ? sourceNames[rawSource] ? this.w(sourceNames[rawSource]) : String(rawSource).replaceAll('_', ' ') : null;
    if (!details.length && !status && !sourceLabel) return '';
    return html`<p class="module-context">${details.join(' · ')}
      ${status ? html`<span class="provenance">${this.w('modular.grid_status')}: ${this.w(({ confirmed: 'Confirmed', provisional: 'Provisional', completed: 'Completed', unavailable: 'Unavailable', pending: 'Pending' })[status] ?? status)}</span>` : ''}
      ${sourceLabel ? html`<span class="provenance">${this.w('modular.source')}: ${sourceLabel}</span>` : ''}
    </p>`;
  }
  coverageLine() {
    const coverage = this.model.coverage;
    if (!coverage) return '';
    return html`<p class="module-context">${this.w('modular.session_coverage_all_drivers')}<br>${this.w('modular.clean_laps')}: ${coverage.clean_laps ?? '—'} · ${this.w('modular.recorded')}: ${coverage.raw_laps ?? '—'} · ${this.w('modular.excluded')}: ${coverage.excluded_laps ?? '—'}</p>`;
  }
  choose(key, value) { this.dispatchEvent(new CustomEvent('f1-module-choice', { bubbles: true, composed: true, detail: { module: this.module.id, key, value } })); }
  field(id) {
    const field = fieldDefinition(this.module, id);
    if (this.module.type === 'pit_stops' && id === 'status') return { ...field, label: 'modular.current_driver_status' };
    return this.model?.sessionKind === 'sprint_qualifying' && /^q[123]_/.test(id) ? { ...field, label: field.label.replace('Q', 'SQ') } : field;
  }
  resultCell(row, id) {
    const type = this.field(id)?.type;
    if (id === 'analysis_source') {
      const names = { f1_live: 'Live timing', f1_replay: 'Recorded replay', jolpica: 'Published results', TimingData: 'Timing', RaceControlMessages: 'Race Control message', pit_context: 'Pit stop context', pit_state: 'Pit status', close_gap: 'Small gap', consecutive_gap_frames: 'Repeated gap observations', penalty_context: 'Penalty context', lap_difference: 'Different laps', track_status: 'Track status', gap_opened: 'Gap increased', SessionStatus: 'Session status', session_finished: 'Session finished', stint_transition: 'Stint change', lap_position_before: 'Position before stops', lap_position_after: 'Position after stops' };
      return [row.source_provider, ...(row.source_signals ?? [])].filter(Boolean).map(value => names[value] ? this.w(names[value]) : value).join(' · ') || '—';
    }
    if (type === 'compound_list') return row[id]?.length ? html`<div class="cell-stack">${row[id].map(compound => this.tyreCell(compound))}</div>` : '—';
    if (type === 'driver_paces' || type === 'driver_laps') return row[id]?.length ? html`<ul class="stint-runs">${row[id].map(item => html`<li>${item.driver}: ${type === 'driver_paces' ? formatTime(item.value) : item.value ?? '—'}</li>`)}</ul>` : '—';
    if (type === 'lap_age') return row[id] == null ? '—' : `${new Intl.NumberFormat(this.language, { maximumFractionDigits: 1 }).format(row[id])} ${this.w('modular.laps')}`;
    if (type === 'lap_range') return row[id] ? `${row[id].map(value => new Intl.NumberFormat(this.language, { maximumFractionDigits: 1 }).format(value)).join('–')} ${this.w('modular.laps')}` : '—';
    if (id === 'pace_leader' && row.equal_pace) return this.w('modular.equal_median_pace');
    if (type === 'strategy_outcome') {
      const labels = { order_held: 'Order held', undercut_succeeded: 'Undercut observed', overcut_succeeded: 'Overcut observed' };
      return labels[row[id]] ? this.w(labels[row[id]]) : row[id] ?? '—';
    }
    if (type === 'battle_status') {
      const states = { active_battle: ['●', 'Active battle estimate'], battle_started: ['▶', 'Battle started'], battle_ended: ['■', 'Battle ended'], position_exchange: ['↔', 'Position exchange'], likely_on_track_overtake: ['↑', 'Likely on-track overtake'] };
      const signal = states[row[id]];
      return html`<span class="chip"><span aria-hidden="true">${signal?.[0] ?? '·'}</span><span>${signal ? this.w(signal[1]) : row[id] ?? '—'}</span></span>`;
    }
    if (type === 'exchange_positions') return row[id]?.length ? html`<ul class="stint-runs">${row[id].map(item => html`<li>${item.driver}: ${item.before ?? '—'} → ${item.after ?? '—'}</li>`)}</ul>` : '—';
    if (type === 'degradation') return row[id] == null ? '—' : html`<span class="time">${formatDelta(row[id])} ${this.w('modular.s_lap')}</span>`;
    if (type === 'reason_counts') return row[id]?.length ? html`<ul class="stint-runs">${row[id].map(item => html`<li>${item.reason.replaceAll('_', ' ')}: ${item.count}</li>`)}</ul>` : '—';
    if (type === 'confidence') return row[id] == null ? '—' : new Intl.NumberFormat(this.language, { style: 'percent', maximumFractionDigits: 0 }).format(row[id]);
    if (type === 'lap_duration') return html`<span class="time">${formatTime(row[id])}</span>`;
    if (type === 'seconds_duration' || type === 'seconds_delta') return row[id] == null ? '—' : html`<span class="time">${type === 'seconds_delta' ? formatDelta(row[id]) : new Intl.NumberFormat(this.language, { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(row[id])} s</span>`;
    if (type === 'points_delta') return row[id] == null ? '—' : html`<span>${row[id] > 0 ? '+' : ''}${new Intl.NumberFormat(this.language, { maximumFractionDigits: 2 }).format(row[id])}</span><span class="provenance">${this.w('modular.points')}</span>`;
    if (type === 'warning_indicator') return row[id] === null ? '—' : row[id] ? html`<span class="chip"><span aria-hidden="true">△</span>${this.w('modular.warning_recorded')}</span>` : this.w('modular.no_warning_recorded');
    if (type === 'penalty_summary') return row[id] ?? (row.penalty_known ? this.w('modular.no_penalty_recorded') : '—');
    if (type === 'boolean') return row[id] == null ? '—' : row[id] ? this.w('modular.new') : this.w('modular.used');
    if (id === 'event_time') return html`<time datetime=${row.event_time ?? ''}>${dateTime(row.event_time, this.settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>${row.decision_time ? html`<span class="provenance">${this.w('modular.decision_time')}</span>` : ''}`;
    if (id === 'incident_status') {
      const signal = INCIDENT_SIGNALS[row.incident_status];
      return html`<span class="chip"><span aria-hidden="true">${signal?.symbol ?? '·'}</span><span>${label(signal, this.language) || row.incident_status || '—'}</span></span>${row.after_race ? html`<span class="provenance">${this.w('modular.after_the_race')}</span>` : ''}`;
    }
    if (id === 'incident_location' && this.model.trackLimits && row[id]) return `${this.w('modular.turn')} ${row[id]}`;
    if (id === 'best_runs') return row.best_runs?.length ? html`<ol class="stint-runs">${row.best_runs.map(run => html`<li><span class="time">${formatTime(run.time)}</span> · ${run.name || run.driver}${run.stint !== null ? html`<span class="provenance">${this.w('modular.stint')} ${run.stint + 1}${run.new_tyre === true ? this.w('modular.new_set') : run.new_tyre === false ? this.w('modular.used_set') : ''}</span>` : ''}</li>`)}</ol>` : '—';
    if (id === 'result_time') return html`<span class="time">${row.result_time ?? '—'}</span>${row.result_status && row.result_status.toLowerCase() !== 'finished' && !this.module.fields.includes('result_status') ? html`<span class="provenance">${row.result_status}</span>` : ''}`;

    if (this.module.type === 'archive' && /^q[123]_time$/.test(id)) return html`<span class="time">${formatTime(row[id])}</span>`;
    if (id === 'qualifying_time') return html`<span class="time">${formatTime(row[id])}</span>`;
    if (id === 'grid_position') return row[id] === 0 ? this.w('modular.pit_lane') : row[id] ?? '—';
    if (id === 'grid_delta') {
      const change = row[id];
      if (change == null) return '—';
      return html`<span>${change > 0 ? '+' : ''}${change}</span><span class="provenance">${this.w('modular.from_qualifying_position')}</span><span class="sr">${change === 0 ? this.w('modular.unchanged') : change > 0 ? this.w('modular.places_lost') : this.w('modular.places_gained')}</span>`;
    }
    if (id === 'position_change') {
      const change = row[id];
      return change ? html`<span>${change.symbol} ${Math.abs(change.value)}</span><span class="provenance">${this.w('modular.from_starting_grid')}</span><span class="sr">${this.w(({ gain: 'places gained', loss: 'places lost', equal: 'unchanged' })[change.status])}</span>` : '—';
    }
    if (id === 'team' && this.model.teams) return this.driverCell({ ...row, driver: row.team, name: row.team });
    return this.cell(row, id);
  }
  tableHeader(fields, labels = {}) {
    const hidden = this.module.show_table_header === false;
    // Keep native column relationships when only the visible labels are hidden.
    return html`<thead part="table-header" class=${hidden ? 'labels-hidden' : ''}><tr part="table-row">${repeat(fields, id => id, id => html`<th part="table-cell" data-field=${id} data-field-type=${this.field(id)?.type ?? ''} scope="col"><span class=${hidden ? 'sr' : ''}>${labels[id] ?? label(this.field(id), this.language)}</span></th>`)}</tr></thead>`;
  }
  timingHeader(fields, laps) {
    const hidden = this.module.show_table_header === false;
    return html`<thead part="table-header" class=${hidden ? 'labels-hidden' : ''}><tr part="table-row">
      ${repeat(fields, id => id, id => html`<th part="table-cell" data-field=${id} data-field-type=${this.field(id)?.type ?? ''} scope="col"><span class=${hidden ? 'sr' : ''}>${id === 'timing_gap' ? this.timingGapHeader() : this.timingFieldLabel(id)}</span></th>`)}
      ${repeat(laps, lap => lap, (lap, index) => html`<th part="table-cell" scope="col" class=${`recent-lap ${index === 0 ? 'lap-start' : ''}`}><span class=${hidden ? 'sr' : ''}>${this.w('modular.lap')} ${lap}</span></th>`)}
    </tr></thead>`;
  }
  eventFocusButton(row) {
    if (this.module.type !== 'timeline' || !this.module.options.event_focus) return '';
    return html`<button data-focus=${`event-${row.eventId}`} aria-label=${this.w('modular.event_focus_select')} title=${row.focusAvailable ? this.w('modular.event_focus_select') : this.w('modular.event_focus_unavailable')} ?disabled=${!row.focusAvailable || this.model.eventFocusReadonly} @click=${() => this.dispatchEvent(new CustomEvent('f1-event-focus', { bubbles: true, composed: true, detail: { eventId: row.eventId } }))}>${this.w('modular.event_focus_select')}</button>`;
  }
  results() {
    const rows = this.model.rows ?? [];
    const fields = this.module.fields.filter(id => moduleFields(this.module).includes(id));
    const countSummary = this.module.type === 'pit_stops' ? this.pitCountSummary() : '';
    const selector = this.module.options.show_selector && this.model.choices?.length ? html`<label class="module-picker"><span>${this.w('modular.round')}</span><select aria-label=${this.w('modular.round')} data-focus="result-round" .value=${this.model.selected} @change=${event => this.choose('round', event.target.value)}>${this.model.choices.map(item => html`<option value=${item.id} .selected=${item.id === this.model.selected}>${item.id} · ${item.name}</option>`)}</select></label>` : '';
    if (!rows.length && this.model.countRows?.length) return countSummary;
    if (!rows.length) return html`${selector}${this.empty(this.model.filtered ? this.w('modular.no_competitors_match_this_selection') : this.model.emptyMessage ?? this.w('modular.no_data_is_available_for_this_selection_yet'))}`;
    if (!fields.length) return this.empty(this.w('modular.choose_columns_in_the_editor'));
    if (this.module.type === 'results' && this.module.options.presentation === 'grid') return html`${selector}<ol class="result-grid" part="result-grid" aria-label=${this.module.title || this.model.title}>${repeat(rows, row => `${this.model.context?.season}:${this.model.context?.round}:${this.model.context?.session}:${row.id}`, row => html`<li part="result-card" data-driver=${row.id}><dl>${repeat(fields, id => id, id => html`<div><dt>${label(this.field(id), this.language)}</dt><dd>${this.resultCell(row, id)}</dd></div>`)}</dl></li>`)}</ol><p class="muted" style="margin-top:10px">${rows.length} ${this.w('modular.of')} ${this.model.total} ${this.w('modular.competitors')}</p>`;
    return html`${selector}${countSummary}${this.model.countRows?.length ? html`<h3>${this.w('modular.recorded_stop_details')}</h3>` : ''}<div class="table-scroll" part="table-container" tabindex="0" role="region" aria-label=${`${this.module.title || this.model.title} · ${this.w('modular.scroll_horizontally_for_more_columns')}`}><table part="table">
      <caption class="sr">${this.module.title || this.model.title}</caption>${this.tableHeader(fields)}
      <tbody>${repeat(rows, row => `${this.model.context?.season}:${this.model.context?.round}:${this.model.context?.session}:${row.id}`, row => html`<tr part="table-row" data-driver=${row.id}>${repeat(fields, id => id, id => html`<td part="table-cell" data-field=${id} data-field-type=${this.field(id)?.type ?? ''}>${row.derived && id === fields[0] ? html`<span class="provenance">${this.w('modular.derived_estimate')}</span>` : ''}${this.module.type === 'pit_stops' && row.source === 'PitLaneTimeCollection' && id === fields[0] ? html`<span class="provenance">${this.w('modular.pit_lane_timing_only')}</span>` : ''}${this.resultCell(row, id)}${id === fields[0] ? this.eventFocusButton(row) : ''}</td>`)}</tr>
      ${this.expanded === row.id ? html`<tr part="table-row"><td part="table-cell" class="details" colspan=${fields.length}><h3>${row.name} · ${row.team ?? '—'}</h3><dl>${fields.filter(id => !['driver', 'team'].includes(id)).map(id => html`<div><dt>${label(this.field(id), this.language)}</dt><dd>${this.resultCell(row, id)}</dd></div>`)}</dl></td></tr>` : ''}`)}</tbody>
    </table></div><div class="section-head" style="margin:10px 0 0"><span class="muted">${rows.length} ${this.w('modular.of')} ${this.model.total} ${this.model.countKind === 'stints' ? this.w('modular.stints') : this.model.countKind === 'stops' ? this.w('modular.stops') : this.model.countKind === 'compounds' ? this.w('modular.compounds') : this.model.countKind === 'comparisons' ? this.w('modular.comparisons') : this.model.countKind === 'events' ? this.w('modular.events') : this.w('modular.competitors')}</span>
      ${this.model.total > this.module.options.rows ? html`<button data-focus="result-count" @click=${() => this.choose('rows', rows.length < this.model.total ? (['pit_stops', 'incidents', 'timeline', 'strategy', 'battles'].includes(this.module.type) ? 500 : 100) : this.module.options.rows)}>${rows.length < this.model.total ? this.w('modular.show_all') : this.w('modular.show_fewer')}</button>` : ''}</div>`;
  }
  pitCountSummary() {
    const rows = this.model.countRows ?? [];
    if (!rows.length) return '';
    // These are driver summaries, never synthetic stop events. Keep identity and
    // the reported count visible even when only timing columns were configured.
    const fields = ['driver', ...this.module.fields.filter(id => ['team', 'status'].includes(id)), 'pit_count'];
    const title = this.w('modular.reported_pit_visits');
    return html`<h3>${title}</h3><div class="table-scroll" part="table-container" tabindex="0" role="region" aria-label=${title}><table part="table" class="pit-count-summary">
      <caption class="sr">${title}</caption>${this.tableHeader(fields, { pit_count: title })}
      <tbody>${repeat(rows, row => `${this.model.context?.key}:${row.id}`, row => html`<tr part="table-row" data-count-driver=${row.id}>${repeat(fields, id => id, id => html`<td part="table-cell" data-field=${id} data-field-type=${this.field(id)?.type ?? ''}>${this.resultCell(row, id)}</td>`)}</tr>`)}</tbody>
    </table></div><div class="section-head" style="margin:10px 0"><span class="muted">${rows.length} ${this.w('modular.of')} ${this.model.countTotal} ${this.w('modular.competitors')}</span>
      ${this.model.countTotal > this.module.options.rows ? html`<button data-focus="pit-count-expand" @click=${() => this.choose('rows', 500)}>${this.w('modular.show_all')}</button>` : ''}</div>`;
  }
  strategyEvidence() {
    const rows = this.model.rows ?? [], content = this.module.options.content;
    if (!rows.length || content === 'pit_outcomes') return '';
    return html`<details class="strategy-evidence"><summary>${this.w('modular.strategy_method_and_supporting_laps')}</summary>
      ${['compound_comparison', 'crossover'].includes(content) ? html`<p>${this.w('modular.strategy_descriptive_only')}</p>`
        : html`<ul>${repeat(rows, row => row.id, row => {
          if (content === 'teammates') {
            const evidence = row.comparison_evidence;
            return html`<li><strong>${row.incident_drivers}</strong>
              ${evidence?.status === 'descriptive' ? html`<p>${this.w('modular.strategy_descriptive_only')}</p>` : html`
                <p>${this.w('modular.strategy_matched_method')}</p>
                <p>${this.w('modular.strategy_pairs')}: ${evidence.used_pairs ?? '—'} / ${evidence.possible_pairs ?? '—'} · ${this.w('modular.laps')}: ${evidence.lap_range?.join('–') ?? '—'}</p>
                ${evidence.status !== 'ready' ? html`<p>${this.w('modular.strategy_insufficient_evidence')}</p>` : ''}
                <p>${this.w('modular.strategy_spread')}: ${evidence.spread ? evidence.spread.map(formatDelta).join(' – ') + ' s' : '—'}</p>
                ${evidence.exclusion_reasons.length ? html`<ul>${evidence.exclusion_reasons.map(item => html`<li>${this.w(`modular.strategy_reason_${item.reason}`)}: ${item.count}</li>`)}</ul>` : ''}
                ${evidence.pairs.length ? html`<ul>${evidence.pairs.map(pair => html`<li>${this.w('modular.lap')} ${pair.lap}: ${pair.first_time !== null && pair.second_time !== null ? `${formatTime(pair.first_time)} − ${formatTime(pair.second_time)} = ` : ''}${formatDelta(pair.delta)} s</li>`)}</ul>` : ''}
              `}</li>`;
          }
          const trend = row.trend_evidence, pit = row.pit_evidence;
          return html`<li><strong>${row.driver} · ${this.w('modular.stint')} ${row.stint_number ?? '—'}</strong>
            <p>${this.w('modular.strategy_trend_method')}</p>
            <p>${this.w('modular.laps')}: ${trend?.laps?.join(', ') || '—'}</p>
            ${trend?.status !== 'ready' ? html`<p>${this.w(trend?.status === 'descriptive' ? 'modular.strategy_descriptive_only' : 'modular.strategy_insufficient_evidence')}</p>` : ''}
            <p>${this.w('modular.strategy_pit_method')}</p>
            <p>${this.w('modular.strategy_transition_lap')}: ${pit?.transition_lap ?? '—'} · ${this.w('modular.strategy_baseline')}: ${formatTime(pit?.baseline_seconds)}</p>
            <p>${this.w('modular.laps')}: ${pit?.baseline_laps?.join(', ') || '—'}</p>
            ${pit?.status !== 'ready' ? html`<p>${this.w('modular.strategy_insufficient_evidence')}</p>` : ''}</li>`;
        })}</ul>`}</details>`;
  }
  strategy() {
    const rows = this.model.rows ?? [], presentation = this.module.options.presentation;
    if (this.module.options.content !== 'stints' || presentation === 'table' || !rows.length) return html`${this.strategyEvidence()}${this.results()}`;
    const valid = rows.filter(row => Number.isInteger(row.stint_first_lap) && Number.isInteger(row.stint_last_lap) && row.stint_first_lap > 0 && row.stint_last_lap >= row.stint_first_lap);
    const first = Math.min(...valid.map(row => row.stint_first_lap)), last = Math.max(...valid.map(row => row.stint_last_lap)), extent = last - first + 1;
    const showTable = presentation === 'both' || this.stintTable;
    return html`${this.strategyEvidence()}<div class="stint-chart"><p class="muted">${this.w('modular.bars_span_the_first_to_last_observed_lap_missing_laps_can_exist_inside_a')}</p>
      <ol class="stint-bars" tabindex="0" aria-label=${this.w('modular.recorded_stint_ranges_and_coverage')}>${repeat(rows, row => row.id, row => {
        const drawable = valid.includes(row), compound = compoundMeta(row.tyre);
        const left = drawable ? (row.stint_first_lap - first) / extent * 100 : 0, width = drawable ? (row.stint_last_lap - row.stint_first_lap + 1) / extent * 100 : 0;
        return html`<li data-stint=${row.id}><div class="stint-meta"><strong>${this.settings.appearance.full_names ? row.name : row.driver} · ${this.w('modular.stint')} ${row.stint_number ?? '—'}</strong>${this.tyreCell(row.tyre)}</div>
          <p>${this.w('modular.laps_2f246a06')} ${row.stint_first_lap ?? '—'}–${row.stint_last_lap ?? '—'} · ${this.w('modular.starting_tyre_age')}: ${row.stint_start_age ?? '—'}</p>
          ${drawable ? html`<div class="stint-lane" aria-hidden="true"><span class="stint-bar" style=${`left:${left}%;width:${width}%;--stint-color:${compound.color ?? 'var(--f1-text)'}`}></span></div><div class="stint-axis" aria-hidden="true"><span>${first}</span><span>${last}</span></div>` : html`<p>${this.w('modular.lap_range_unavailable')}</p>`}
          <p class="muted">${this.w('modular.clean')}: ${row.clean_samples ?? '—'} · ${this.w('modular.recorded')}: ${row.raw_samples ?? '—'} · ${this.w('modular.excluded')}: ${row.excluded_samples ?? '—'}</p></li>`;
      })}</ol></div>
      ${presentation === 'chart' ? html`<button aria-expanded=${String(Boolean(showTable))} aria-controls="stint-data" @click=${() => { this.stintTable = !this.stintTable; }}>${showTable ? this.w('modular.hide_data_table') : this.w('modular.show_data_table')}</button>` : ''}
      <div id="stint-data">${showTable ? this.results() : html`<p class="muted">${rows.length} ${this.w('modular.of')} ${this.model.total} ${this.w('modular.stints')}</p>`}</div>`;
  }
  incidents() {
    const rows = this.model.rows ?? [], fields = this.module.fields.filter(id => moduleFields(this.module).includes(id));
    if (!rows.length) return this.empty(this.model.emptyMessage ?? (this.model.filtered ? this.w('modular.no_incidents_match_this_selection') : this.module.type === 'timeline' ? this.w('modular.no_recorded_events_for_this_session_yet') : this.w('modular.no_recorded_incidents_for_this_session')));
    if (!fields.length) return this.empty(this.w('modular.choose_fields_in_the_editor'));
    return html`<ol class="events incident-list" tabindex="0" aria-label=${this.module.title || this.model.title}>${repeat(rows, row => row.id, row => html`<li data-event=${row.id}>${row.derived ? html`<p class="chip">${this.w('modular.derived_estimate')}</p>` : ''}<dl>${repeat(fields, id => id, id => html`<div><dt class="muted">${label(this.field(id), this.language)}</dt><dd>${this.resultCell(row, id)}</dd></div>`)}</dl>${this.eventFocusButton(row)}</li>`)}</ol>
      <p class="muted">${rows.length} ${this.w('modular.of')} ${this.model.total} ${this.w('modular.events')}</p>`;
  }
  documents() {
    const allRows = this.model.rows ?? [], latest = this.module.options.presentation === 'latest';
    const rows = latest ? allRows.slice(0, 1) : allRows;
    if (!rows.length) return this.empty(this.w('modular.no_documents_match_this_selection'));
    if (!this.module.fields.length) return this.empty(this.w('modular.choose_fields_in_the_editor'));
    const context = this.model.context?.meeting;
    const newTab = this.module.options.open_new_tab;
    return html`<p class="document-summary">
      ${this.module.options.show_fia_logo ? html`<strong class="chip">FIA</strong>` : ''}
      ${this.module.options.show_race_context && context ? html`<span>${context}</span>` : ''}
      ${this.module.options.show_latest_badge ? html`<span class="chip">${this.w('modular.latest_first')}</span>` : ''}
      ${this.module.options.show_count ? html`<span>${this.model.total} ${this.w(this.model.total === 1 ? 'document' : 'documents')}</span>` : ''}
    </p><div class="documents-scroll" style=${!latest && this.module.options.list_max_height ? `max-height:${this.module.options.list_max_height}px;overflow:auto` : ''}><ol class="documents">${repeat(rows, row => row.id, row => html`<li class=${this.module.options.document_coloring ? `tone-${documentTone(row.document_title)}` : ''}>
      ${this.module.fields.includes('document_number') && row.document_number ? html`<small>${this.w('modular.document')} ${row.document_number}</small>` : ''}
      ${this.module.fields.includes('document_title') ? row.url ? html`<a href=${row.url} target=${newTab ? '_blank' : '_self'} rel=${newTab ? 'noopener noreferrer' : ''}>${this.module.options.show_pdf_icon ? html`<ha-icon icon="mdi:file-pdf-box" aria-hidden="true"></ha-icon>` : ''}${row.document_title}${newTab ? html`<span class="sr"> · ${this.w('modular.opens_in_a_new_tab')}</span>` : ''}</a>` : html`<strong>${row.document_title}</strong><small>${this.w('modular.document_link_unavailable')}</small>` : ''}
      ${this.module.options.show_document_type ? html`<small class="document-type">${documentType(row.document_title)}</small>` : ''}
      ${this.module.fields.includes('document_time') ? html`<small>${this.w('modular.published')}: ${row.timestamp ? dateTime(row.document_time, this.settings, { dateStyle: 'medium', timeStyle: 'short' }) : row.document_time ?? this.w('modular.not_supplied')}</small>` : ''}
    </li>`)}</ol></div>`;
  }
  overview() {
    const items = this.model.items ?? [];
    if (!items.length) return this.empty(this.w('modular.waiting_for_information'));
    return html`<div class="overview ${this.module.options.layout_mode === 'auto' ? '' : this.module.options.layout_mode}" part="metrics">${items.map(item => item.id === 'circuit_map' ? this.circuitMap(item.value) : item.id === 'circuit_history' ? this.circuitHistory(item.value) : html`<div class="metric ${item.id === 'meeting' ? 'hero' : ''}" part="metric">
      <small>${item.rainRisk ? this.rainRiskLabel() : label(FIELDS[item.id], this.language)}</small><div class="metric-value">
      ${item.flag && this.settings.appearance.flags ? html`<img class="flag" src=${item.flag} alt=${item.country ?? ''} width="40" height="27" @error=${event => { event.target.hidden = true; }} @load=${event => { event.target.hidden = false; }}>` : ''}
      <strong>${item.id === 'track_status' ? this.flagCell(item.value) : item.value ?? '—'}</strong></div>${item.rainRisk ? this.rainRiskDetails(item) : ''}${item.detail ? html`<span class="provenance">${item.detail}</span>` : ''}
    </div>`)}</div>`;
  }
  rainRiskLabel() {
    return html`${this.settings.accessibility.signals !== 'text' ? html`<ha-icon class="rain-risk-symbol" icon="mdi:weather-rainy" aria-hidden="true"></ha-icon>` : ''}${this.w('modular.session_rain_risk')}`;
  }
  rainRiskDetails(item) {
    return html`<details class="rain-risk-details"><summary>${this.w(item.session)}</summary>
      <p>${this.w('modular.rain_risk_details')}</p>
      ${item.message ? html`<p>${item.message}</p>` : ''}
      ${item.utc ? html`<time datetime=${item.utc}>${dateTime(item.utc, this.settings, { timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'medium' })} UTC</time>` : ''}
    </details>`;
  }
  circuitMap(value = {}) {
    return html`<section class="circuit-panel" aria-label=${this.w('modular.circuit_map')}><div class="circuit-map">${value.url ? html`<img src=${value.url} alt=${value.circuit ?? this.w('modular.circuit_map')} loading="lazy">` : html`<div class="circuit-map-copy"><strong>${value.circuit ?? this.w('modular.circuit_map_unavailable')}</strong><span class="provenance">${[value.locality, value.country, value.season ? `${this.w('modular.season')} ${value.season}` : null].filter(Boolean).join(' · ')}</span></div>`}</div></section>`;
  }
  circuitHistory(value = {}) {
    const percent = number => Number.isFinite(Number(number)) ? `${new Intl.NumberFormat(this.language, { maximumFractionDigits: 1 }).format(Number(number))}%` : null;
    const person = item => item?.driver_name ? `${item.driver_name}${item.constructor_name ? ` · ${item.constructor_name}` : ''}${item.season ? ` · ${item.season}` : ''}` : null;
    const stats = [
      [this.w('modular.defending_winner'), person(value.defending_winner)],
      [this.w('modular.defending_pole'), person(value.defending_pole_sitter)],
      [this.w('modular.races_held'), value.races_held_here],
      [this.w('modular.first_f1_race'), value.first_f1_race_here?.season],
      [this.w('modular.pole_to_win_last_five'), percent(value.pole_to_win_conversion_last_5)],
      [this.w('modular.dnf_rate_last_five'), percent(value.dnf_rate_last_5)],
    ].filter(([, content]) => content !== null && content !== undefined && content !== '');
    const lists = [
      [this.w('modular.recent_winners'), value.last_5_winners],
      [this.w('modular.most_driver_wins_here'), value.top_5_driver_wins_here],
      [this.w('modular.most_constructor_wins_here'), value.top_5_constructor_wins_here],
    ].filter(([, rows]) => Array.isArray(rows) && rows.length);
    if (!stats.length && !lists.length && !value.last_year_podium?.podium?.length) return html`<section class="circuit-panel"><p class="empty">${this.w('modular.circuit_history_is_not_available_yet')}</p></section>`;
    return html`<section class="circuit-panel" aria-label=${this.w('modular.circuit_history')}><div class="history-grid">${stats.map(([title, content]) => html`<div class="history-item"><small>${title}</small><strong>${content}</strong></div>`)}</div>
      ${value.last_year_podium?.podium?.length ? html`<div><h3>${this.w('modular.last_podium')} · ${value.last_year_podium.season ?? ''}</h3><ol class="history-list">${value.last_year_podium.podium.slice(0, 3).map(item => html`<li>${person(item) ?? '—'}</li>`)}</ol></div>` : ''}
      ${lists.map(([title, rows]) => html`<div><h3>${title}</h3><ol class="history-list">${rows.slice(0, 5).map(item => html`<li>${person(item) ?? item.constructor_name ?? item.race_name ?? '—'}${item.wins != null ? ` · ${item.wins}` : ''}</li>`)}</ol></div>`)}</section>`;
  }
  replayAction(action, value) {
    this.dispatchEvent(new CustomEvent('f1-replay-action', { bubbles: true, composed: true, detail: { module: this.module.id, action, value, context: this.model.controlContext } }));
  }
  replay() {
    const model = this.model, fields = this.module.fields, disabled = model.readonly || model.request?.pending;
    const target = this.seekDraft?.context === model.controlContext ? this.seekDraft.value : model.position;
    const syncTarget = this.syncDraft?.context === model.controlContext && model.syncPoints.some(point => point.id === this.syncDraft.value)
      ? this.syncDraft.value : model.syncPoints[0]?.id ?? '';
    const syncLabel = point => point.kind === 'lap' ? this.w('modular.lap_number_starts', { lap: point.value })
      : point.kind === 'sprint_qualifying_part' ? this.w('modular.sprint_qualifying_part_starts', { part: point.value })
        : this.w('modular.qualifying_part_starts', { part: point.value });
    const stateNames = { idle: 'No replay loaded', selected: 'Selected · ready to load', loading: 'Loading replay', ready: 'Loaded · ready to play', playing: 'Playing', paused: 'Paused', seeking: 'Seeking', unknown: 'Replay status unavailable' };
    const clock = value => value == null ? '—' : `${Math.floor(value / 3600)}:${String(Math.floor(value % 3600 / 60)).padStart(2, '0')}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
    const options = this.module.options, compact = options.display === 'compact';
    const showSecondary = options.secondary_selects && !compact, showStatus = options.status_details && !compact;
    const selectorFields = [...(showSecondary ? [['year', 'Replay year']] : []), ['session', 'Recorded session'], ...(showSecondary && options.start_reference ? [['reference', 'Start reference']] : [])];
    const actionSymbol = { refresh: '↻', load: '↓', play: '▶', pause: 'Ⅱ', stop: '■' };
    const actionLabel = sourceText => html`<span class=${options.show_button_labels ? '' : 'sr'}>${this.w(sourceText)}</span>`;
    const send = (action, sourceText, symbol = actionSymbol[action]) => html`<button class=${options.show_button_labels ? '' : 'icon-only'} data-focus=${`replay-${action}`} aria-label=${this.w(sourceText)} title=${this.w(sourceText)} ?disabled=${disabled || !model.allowed[action]} @click=${() => this.replayAction(action)}><span aria-hidden="true">${symbol}</span>${actionLabel(sourceText)}</button>`;
    return html`<p><strong>${model.selectedSession ?? this.w('modular.choose_a_recorded_session')}</strong><br><span class="chip">${this.w(stateNames[model.replayState])}</span></p>
      ${showStatus ? html`<p class="muted replay-scope">${this.w('modular.controls_replay_for_scope_changes_affect_every_dashboard_and_the_integration_s_automation_data', { scope: model.scope })}</p>` : ''}
      ${(fields.includes('replay_transport') || fields.includes('replay_progress')) && model.playerStatus !== 'available' ? html`<p class="muted">${model.playerStatus === 'disabled' ? this.w('modular.enable_the_replay_player_entity_in_f1_sensor_to_use_playback_controls') : this.w('modular.playback_controls_are_unavailable_because_the_replay_player_has_no_usable_state')}</p>` : ''}
      ${model.readonly ? html`<p class="muted">${model.frozen ? this.w('modular.resume_the_view_to_use_replay_controls') : this.w('modular.replay_controls_are_disabled_in_previews')}</p>` : ''}
      ${fields.includes('replay_progress') && model.duration !== null ? html`<div class="replay-progress"><span>${this.w('modular.from_replay_start')}: ${clock(model.position)} / ${clock(model.duration)}</span>
        ${fields.includes('replay_transport') && options.seek_controls ? html`<label><span class="sr">${this.w('modular.replay_position_in_seconds')}</span><input data-focus="replay-seek" type="range" aria-label=${this.w('modular.replay_position_in_seconds')} min="0" max=${model.duration} step="1" .value=${String(target)} aria-valuetext=${clock(target)} ?disabled=${disabled || !model.allowed.seek} @input=${event => { this.seekDraft = { context: model.controlContext, value: Number(event.target.value) }; }}></label><div class="replay-controls" part="controls"><span>${this.w('modular.go_to')}: ${clock(target)}</span><button class=${options.show_button_labels ? '' : 'icon-only'} data-focus="replay-apply-seek" aria-label=${this.w('modular.go_to_replay_position')} title=${this.w('modular.go_to_replay_position')} ?disabled=${disabled || !model.allowed.seek || !this.seekDraft || target === model.position} @click=${() => { this.replayAction('seek', target); this.seekDraft = null; }}><span aria-hidden="true">↦</span>${actionLabel('Go to replay position')}</button></div>` : html`<progress max=${model.duration} value=${model.position} aria-label=${this.w('modular.replay_progress')}></progress>`}
      </div>` : ''}
      ${model.replayState === 'loading' ? html`<div class="replay-progress"><span>${this.w('modular.download')}: ${model.download !== null && model.download >= 0 && model.download <= 100 ? `${model.download}%` : '—'}</span></div>` : ''}
      ${fields.includes('replay_transport') ? html`<div class="replay-controls" part="controls">${model.replayState === 'playing' ? send('pause', 'Pause replay', 'Ⅱ') : send('play', 'Play replay', '▶')}
        ${options.seek_controls ? html`<button class=${options.show_button_labels ? '' : 'icon-only'} data-focus="replay-back" aria-label=${this.w('modular.back_30_s')} title=${this.w('modular.back_30_s')} ?disabled=${disabled || !model.allowed.seek || model.position <= 0} @click=${() => this.replayAction('seek', Math.max(0, model.position - 30))}><span aria-hidden="true">−30</span>${actionLabel('Back 30 s')}</button>
        <button class=${options.show_button_labels ? '' : 'icon-only'} data-focus="replay-forward" aria-label=${this.w('modular.forward_30_s')} title=${this.w('modular.forward_30_s')} ?disabled=${disabled || !model.allowed.seek || model.position >= model.duration} @click=${() => this.replayAction('seek', Math.min(model.duration, model.position + 30))}><span aria-hidden="true">+30</span>${actionLabel('Forward 30 s')}</button>` : ''}
        ${send('stop', 'Stop replay', '■')}</div>` : ''}
      ${fields.includes('replay_transport') && options.seek_controls && model.syncPoints.length ? html`<div class="replay-picker"><label><span>${this.w('modular.replay_sync_point')}</span><select data-focus="replay-sync" aria-label=${this.w('modular.replay_sync_point')} .value=${syncTarget} ?disabled=${disabled || !model.allowed.sync} @change=${event => { this.syncDraft = { context: model.controlContext, value: event.target.value }; }}>
        ${model.syncPoints.map(point => html`<option value=${point.id}>${syncLabel(point)} · ${clock(point.position)}</option>`)}
      </select></label></div><div class="replay-controls" part="controls"><span class="muted">${this.w('modular.choose_the_matching_lap_or_qualifying_part_when_it_starts_on_your_broadcast')}</span><button data-focus="replay-apply-sync" aria-label=${this.w('modular.sync_replay_to_point')} title=${this.w('modular.sync_replay_to_point')} ?disabled=${disabled || !model.allowed.sync || !syncTarget} @click=${() => { this.replayAction('sync', syncTarget); this.syncDraft = null; }}><span aria-hidden="true">↦</span>${actionLabel('modular.sync_replay_to_point')}</button></div>` : ''}
      ${fields.includes('replay_selection') ? html`<details class="analysis-explanation"><summary>${this.w('modular.choose_replay')}</summary>
        ${!model.canSelect ? html`<p class="muted">${this.w('modular.stop_the_loaded_replay_before_changing_its_year_session_or_start_reference')}</p>` : ''}
        <div class="replay-picker">${selectorFields.map(([id, sourceText]) => {
          const selected = model.selectors[id];
          return html`<label><span>${this.w(sourceText)}</span><select data-focus=${`replay-${id}`} aria-label=${this.w(sourceText)} .value=${selected.state ?? ''} ?disabled=${disabled || !model.allowed[id]} @change=${event => this.replayAction(id, event.target.value)}>
            ${!selected.options.includes(selected.state) ? html`<option value="">${this.w('modular.choose')}</option>` : ''}
            ${selected.options.map(value => html`<option value=${value} .selected=${value === selected.state}>${value}</option>`)}
          </select></label>`;
        })}</div><div class="replay-controls" part="controls">${options.refresh ? send('refresh', 'Refresh session list') : ''}${send('load', 'Load selected replay')}</div>
      </details>` : ''}
      ${model.downloadError ? html`<p role="alert">${this.w(model.downloadErrorCode === 'archive_identity_conflict' ? 'modular.replay_identity_conflict' : model.downloadErrorCode === 'cache_normalization_incompatible' ? 'modular.replay_cache_incompatible' : 'modular.the_replay_download_failed_try_loading_the_selected_session_again')}</p>` : ''}
      ${showStatus && model.loaded && model.archiveIdentity === 'missing' ? html`<p class="muted">${this.w('modular.replay_identity_missing')}</p>` : ''}
      ${model.indexError ? html`<p>${this.w('modular.the_session_list_could_not_be_retrieved_try_refreshing_it')}</p>` : ''}
      ${model.request?.pending ? html`<p role="status">${this.w('modular.sending_replay_command')}</p>` : model.request?.error ? html`<p role="alert">${this.w('modular.the_replay_command_failed_check_the_current_status_before_trying_again')}</p>` : model.request?.busy ? html`<p role="status">${this.w('modular.command_not_sent_another_card_was_sending_a_replay_command_check_the_current_status')}</p>` : ''}
    `;
  }
  weather() {
    const items = this.model.items ?? [];
    if (!items.length) return this.empty(this.w('modular.choose_weather_fields_in_the_editor'));
    const compact = this.module.options.presentation === 'compact_list';
    return html`<dl class=${compact ? 'weather-list' : 'overview'}>${items.map(item => html`<div class=${compact ? 'weather-item' : 'metric weather-item'}>
      <dt>${item.rainRisk ? this.rainRiskLabel() : label(this.field(item.id), this.language)}</dt><dd>${this.weatherValue(item)}${item.rainRisk ? this.rainRiskDetails(item) : ''}${item.detail ? html`<span class="provenance">${item.detail}</span>` : ''}</dd>
    </div>`)}</dl>`;
  }
  weatherValue(item) {
    if (item.value === null) return '—';
    const symbols = this.settings.accessibility.signals !== 'text';
    if (item.type === 'rain_indicator') return item.value ? this.w('modular.yes_rain_detected') : this.w('modular.no_rain_detected');
    if (item.type === 'weather_condition') {
      const groups = [
        [[0], 'weather-sunny', 'Clear sky', '#e5a000'], [[1, 2], 'weather-partly-cloudy', 'Partly cloudy', '#d59a24'],
        [[3], 'weather-cloudy', 'Overcast', '#78909c'], [[45, 48], 'weather-fog', 'Fog', '#78909c'],
        [[51, 53, 55], 'weather-rainy', 'Drizzle', '#298fcb'], [[61, 63, 65, 80, 81, 82], 'weather-pouring', 'Rain', '#298fcb'],
        [[56, 57, 66, 67], 'weather-snowy-rainy', 'Freezing precipitation', '#49a6c7'],
        [[71, 73, 75, 77, 85, 86], 'weather-snowy', 'Snow', '#49a6c7'], [[95, 96, 99], 'weather-lightning-rainy', 'Thunderstorm', '#9975cf'],
      ];
      const group = groups.find(([codes]) => codes.includes(item.value));
      if (!group) return this.w('modular.unknown_condition');
      const nightIcon = item.night && item.value <= 2;
      const icon = nightIcon ? item.value === 0 ? 'weather-night' : 'weather-night-partly-cloudy' : group[1];
      const color = this.module.options.colored_icons ? nightIcon ? '#8498cf' : group[3] : 'inherit';
      return html`<span class="weather-condition">${symbols ? html`<ha-icon class="weather-symbol" aria-hidden="true" icon=${`mdi:${icon}`} style=${`color:${color}`}></ha-icon>` : ''}<span class="weather-condition-text">${this.w(group[2])}</span></span>`;
    }
    const value = new Intl.NumberFormat(this.language, { maximumFractionDigits: 1 }).format(item.value);
    return html`${item.type === 'bearing' && symbols ? html`<span class="weather-symbol" aria-hidden="true" style=${`transform:rotate(${item.value}deg)`}>↑</span>` : ''}${value}${item.type === 'bearing' ? '' : ' '}${item.unit ?? ''}`;
  }
  calendar() {
    if (!this.model.rows?.length) return this.empty(this.model.hiddenRows ? this.w('modular.all_selected_sessions_are_in_the_past_and_are_hidden') : this.w('modular.no_published_session_dates_or_times_are_available'));
    return html`<ol class="schedule">${this.model.rows.map(row => html`<li>
      <div class="schedule-identity">
        ${this.module.options.range === 'season' && row.flag && this.settings.appearance.flags ? html`<span><img class="flag" src=${row.flag} alt=${row.country ?? ''} width="40" height="27" loading="lazy"
          @error=${event => { event.target.hidden = true; event.target.nextElementSibling.hidden = false; }}
          @load=${event => { event.target.hidden = false; event.target.nextElementSibling.hidden = true; }}><span class="flag-fallback" hidden>${row.country ?? ''}</span></span>` : ''}
      <div class="schedule-copy"><strong>${label(row, this.language)}</strong>${this.module.options.range === 'season' ? html`<div class="muted">${row.meeting}</div>` : ''}
        ${this.module.options.details.includes('round') && row.round != null ? html`<div>${this.w('modular.round_231a3036')} ${row.round}</div>` : ''}
        ${this.module.options.details.includes('circuit') && row.circuit ? html`<div>${row.circuit}</div>` : ''}
        ${this.module.options.details.includes('location') && row.location ? html`<div>${row.location}</div>` : ''}
        ${row.next && this.module.options.next === 'label' ? html`<span class="badge">${this.w('modular.next_session')}</span>` : ''}
        ${row.past && this.module.options.past === 'dim' ? html`<span class="muted">${row.start ? this.w('modular.start_time_passed') : this.w('modular.published_date_passed')}</span>` : ''}
      </div></div>
      <div>${row.start ? html`<time datetime=${row.start}>${dateTime(row.start, this.settings, { timeZone: row.display_timezone, weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</time>
      <span class="provenance">${row.timezone_label}</span>${row.track_timezone ? html`<time datetime=${row.start}>${dateTime(row.start, this.settings, { timeZone: row.track_timezone, weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</time><span class="provenance">${this.w('modular.circuit_time')} · ${row.track_timezone}</span>` : ''}` : html`<time datetime=${row.date}>${dateTime(`${row.date}T00:00:00Z`, this.settings, { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' })}</time>
      <span class="provenance">${this.w('modular.start_time_not_published')}</span>`}${row.estimated ? html`<span class="provenance">${this.w('modular.provisional_start_time')}</span>` : ''}</div>
    </li>`)}</ol>`;
  }
  qualifyingFocusPart() {
    if (!['qualifying', 'sprint_qualifying'].includes(this.model?.sessionKind)) return null;
    const focus = this.module.options.qualifying_focus;
    return /^q[123]$/.test(focus) ? Number(focus.at(-1)) : focus === 'current' ? this.model.qualifying_part ?? this.model.currentPart ?? null : null;
  }
  timingFieldLabel(id) {
    const sector = this.minimalTiming && /^sector_([123])_with_minisectors$/.exec(id);
    if (sector) return html`<span aria-hidden="true">${label(this.field(`sector_${sector[1]}`), this.language)}</span><span class="sr">${label(this.field(id), this.language)}</span>`;
    const part = id === 'qualifying_gap' ? this.qualifyingFocusPart() : null;
    return part ? this.w('modular.timing_part_gap', { part: `${this.model.sessionKind === 'sprint_qualifying' ? 'SQ' : 'Q'}${part}` }) : label(this.field(id), this.language);
  }
  timingGapOrder() { return this.module.options.gap_primary === 'gap' ? ['gap', 'interval'] : ['interval', 'gap']; }
  timingGapHeader() {
    const [primary, secondary] = this.timingGapOrder();
    return html`<span class="gap-stack"><span>${this.w(primary === 'interval' ? 'modular.timing_int_short' : 'modular.timing_gap_short')}</span><span class="secondary">${this.w(secondary === 'interval' ? 'modular.timing_int_short' : 'modular.timing_gap_short')}</span></span>`;
  }
  combinedGapCell(row) {
    if (['race', 'sprint'].includes(this.model.sessionKind) && row.position === 1) return html`<span class="gap-stack" part="timing-gap"><span>${this.w('modular.leader')}</span></span>`;
    const [primary, secondary] = this.timingGapOrder();
    const name = id => label(this.field(id), this.language);
    const value = id => row[id] === null || row[id] === undefined || row[id] === '' ? '—' : formatTimingGap(row[id], this.w('modular.lap'));
    return html`<span class="gap-stack" part="timing-gap"><span data-gap=${primary}><span class="sr">${name(primary)}: </span>${value(primary)}</span><span class="secondary" data-gap=${secondary}><span class="sr">${name(secondary)}: </span>${value(secondary)}</span></span>`;
  }
  timingPosition(row) {
    if (this.module.options.position_change !== 'grid') return row.position ?? '—';
    const change = row.position_change;
    const description = change ? `${this.w('modular.timing_position_reference')} · ${Math.abs(change.value)} ${this.w(({ gain: 'places gained', loss: 'places lost', equal: 'unchanged' })[change.status])}` : this.w('modular.timing_position_unknown');
    return html`<span class="timing-position"><span>${row.position ?? '—'}</span><span class="position-change ${change?.status ?? 'unknown'}" title=${description}><span aria-hidden="true">${change?.value ? `${change.symbol}${Math.abs(change.value)}` : '—'}</span><span class="sr">${description}</span></span></span>`;
  }
  timingBadge(badge) {
    const codes = { penalty: 'penalty', drive_through: 'drive_through', stop_go: 'stop_go', under_investigation: 'investigation', noted: 'noted', in_pit: 'pit', pit_out: 'pit_out', retired: 'retired', stopped: 'stopped' };
    const names = { drive_through: 'Drive-through penalty', stop_go: 'Stop-and-go penalty', under_investigation: 'Under investigation', noted: 'Noted', in_pit: 'In pit', pit_out: 'Pit out', retired: 'Retired', stopped: 'Stopped', penalty: 'Penalty' };
    const text = badge.type === 'time_penalty' && badge.seconds > 0 ? this.w('modular.timing_penalty_seconds', { seconds: badge.seconds }) : this.w(`modular.timing_badge_${codes[badge.type] ?? 'penalty'}`);
    const description = [badge.service_status === 'unknown' ? this.w('modular.timing_penalty_unknown') : badge.type === 'time_penalty' ? this.w('modular.timing_penalty_time', { seconds: badge.seconds }) : this.w(names[badge.type] ?? 'Penalty'), badge.after_race ? this.w('modular.timing_investigation_after_session') : ''].filter(Boolean).join(' · ');
    return { text, description, detail: [badge.penalty, badge.reason].filter(Boolean).join(' · ') };
  }
  driverBadges(row) {
    if (this.module.type !== 'timing' || !this.module.options.driver_badges || !row.badges?.length) return '';
    return html`<span class="driver-badges" part="driver-status">${row.badges.map(badge => {
      const value = this.timingBadge(badge);
      return html`<span class="driver-badge" data-kind=${badge.type} title=${[value.description, value.detail].filter(Boolean).join(' · ')}><span aria-hidden="true">${value.text}</span><span class="sr">${value.description}${value.detail ? ` · ${value.detail}` : ''}</span></span>`;
    })}</span>`;
  }
  driverDecisions(row) {
    if (!this.module.options.driver_badges || !row.badges?.length) return '';
    return html`<div class="timing-status-details"><h3>${this.w('modular.timing_status_details')}</h3><ul class="timing-decisions">${row.badges.map(badge => {
      const value = this.timingBadge(badge);
      return html`<li><strong>${value.description}</strong>${value.detail ? html`<div>${value.detail}</div>` : ''}${badge.event_time ? html`<small><time datetime=${badge.event_time}>${dateTime(badge.event_time, this.settings, { hour: '2-digit', minute: '2-digit' })}</time>${badge.lap ? html` · ${this.w('modular.lap')} ${badge.lap}` : ''}</small>` : ''}</li>`;
    })}</ul></div>`;
  }
  timeCell(value) {
    const status = timingStatus(value), signal = SIGNALS[status], colors = statusColors(status, this.settings.mode, this.settings.appearance.palette);
    const signals = this.settings.accessibility.signals, contextClass = this.module.options.show_time_context !== false ? 'provenance' : 'sr';
    return html`<div class="cell-stack"><span class="signal ${status}" style=${this.compactPresentation ? `background:transparent;color:${colors.background}` : `background:${colors.background};color:${colors.color}`}>
      ${this.module.options.show_time_status_icon !== false && signals !== 'text' && status !== 'unknown' ? html`<span aria-hidden="true">${signal.symbol}</span>` : ''}
      <span class="time">${formatTime(value?.time)}</span>
      <span class=${signals === 'shape' ? 'sr' : ''}>${label(signal, this.language)}</span>
    </span>${value?.session_part ? html`<span class=${contextClass}>${this.model.sessionKind === 'sprint_qualifying' ? 'SQ' : 'Q'}${value.session_part}</span>` : ''}${value?.lap ? html`<span class=${contextClass}>${this.w('modular.lap')} ${value.lap}${status === 'previous' ? this.w('modular.previous') : ''}</span>` : html`<span class="sr">${this.w('modular.lap_unknown')}</span>`}</div>`;
  }
  driverCell(row) {
    const appearance = this.settings.appearance;
    const dimensions = this.compactPresentation ? { frame: 22, image: 18 } : logoDimensions(appearance.logo_size);
    const color = appearance.team_colors && /^#[0-9a-f]{6}$/i.test(row.team_color) ? row.team_color : 'transparent';
    const headshot = appearance.logos && !this.model.teams && this.module.options?.driver_image_type === 'headshot' ? safeImageUrl(row.headshot) : null;
    const interactive = this.module.type !== 'timing' || this.timingDetailRows?.has(row.id);
    const open = this.module.type === 'timing' ? this.timingExpanded.includes(row.id) : this.expanded === row.id;
    const content = html`
      ${headshot ? html`<img class="driver-headshot" src=${headshot} alt="" width=${dimensions.frame} height=${dimensions.frame} @error=${event => { event.target.hidden = true; event.target.nextElementSibling.hidden = false; }}><f1-team-logo hidden aria-hidden="true" .team=${row.team} .variant=${appearance.logo_style} .mode=${this.settings.mode} .size=${appearance.logo_size}></f1-team-logo>` : appearance.logos ? html`<f1-team-logo aria-hidden="true" .team=${row.team} .variant=${appearance.logo_style} .mode=${this.settings.mode} .size=${appearance.logo_size}></f1-team-logo>` : ''}
      <span>${appearance.full_names ? row.name : row.driver}<span class="sr"> · ${row.name} · ${row.team ?? ''}${interactive ? ` · ${this.w('modular.details')}` : ''}</span>${this.pushLapMarker(row)}</span>${this.driverBadges(row)}${interactive && this.module.type === 'timing' && this.module.options.narrow_layout ? html`<ha-icon class="driver-disclosure" aria-hidden="true" icon=${open ? 'mdi:chevron-up' : 'mdi:chevron-down'}></ha-icon>` : ''}`;
    const style = `--team-color:${color};--f1-logo-frame:${dimensions.frame}px;--f1-logo-image:${dimensions.image}px`;
    if (!interactive) return html`<span class="driver" style=${style}>${content}</span>`;
    return html`<button class="driver" data-focus=${`driver-${row.id}`} style=${style} aria-expanded=${open ? 'true' : 'false'} aria-controls=${this.module.type === 'timing' && open ? `driver-detail-${row.id}` : ''} @click=${() => { if (this.module.type === 'timing') this.toggleTimingDriver(row.id); else this.expanded = open ? '' : row.id; }}>${content}</button>`;
  }
  pushLapMarker(row) {
    if (!this.model.pushMode || this.model.pushMode === 'off' || !['active', 'completed'].includes(row.push_group)) return '';
    const key = row.push_lap.state === 'completed' ? 'modular.push_lap_complete' : row.push_lap.state === 'probable_push' ? 'modular.possible_push' : 'modular.push';
    return html`<span class="push-label" part="push-lap-status">${this.w(key)}${row.push_lap.completed ? html`<span class="push-result"> · ${formatTime(row.push_lap.last_lap_time)}</span>` : ''}</span>${row.push_lap_delta ? html`<span class="push-delta-reference">${row.push_lap_delta.reference ? this.w('modular.push_delta_reference', { driver: row.push_lap_delta.reference.driver, time: formatTime(row.push_lap_delta.reference.time), part: `${this.model.sessionKind === 'sprint_qualifying' ? 'SQ' : 'Q'}${row.push_lap_delta.reference.part}` }) : this.w(row.push_lap_delta.status === 'unavailable' ? 'modular.push_delta_unavailable' : 'modular.push_delta_waiting')}</span>` : ''}`;
  }
  pushDeltaCell(row, sector) {
    const comparison = row.push_lap_delta;
    if (!comparison) return '';
    const value = comparison[`sector_${sector}`];
    const description = value === null ? this.w('modular.push_delta_unknown', { sector }) : this.w('modular.push_delta_checkpoint', { sector, delta: formatDelta(value) });
    if (value === null) return html`<span class="push-delta unknown" data-sector=${sector} aria-label=${description}>—</span>`;
    return html`<span class="push-delta" data-sector=${sector} aria-label=${description}>Δ ${formatDelta(value)}</span>`;
  }
  toggleTimingDriver(id) {
    this.timingExpanded = this.timingExpanded.includes(id) ? this.timingExpanded.filter(value => value !== id) : [...this.timingExpanded, id];
    this.dispatchEvent(new CustomEvent('f1-driver-details-change', { bubbles: true, composed: true }));
  }
  clearTimingDrivers() {
    if (!this.timingExpanded.length) return;
    this.timingExpanded = [];
    this.dispatchEvent(new CustomEvent('f1-driver-details-change', { bubbles: true, composed: true }));
  }
  timingDetailPanel(row, fields, detailLaps, tableLapNumbers) {
    const color = this.settings.appearance.team_colors && /^#[0-9a-f]{6}$/i.test(row.team_color) ? row.team_color : 'var(--f1-border)';
    const history = (row.history ?? []).slice(0, detailLaps).filter(lap => !tableLapNumbers.includes(lap.lap));
    return html`<section class="timing-detail" part="driver-detail" id=${`driver-detail-${row.id}`} style=${`--team-color:${color}`} aria-label=${`${row.name} · ${this.w('modular.details')}`}>
      <div class="timing-detail-heading"><h3>${row.name} · ${row.team ?? '—'}</h3><button data-focus=${`driver-${row.id}`} @click=${() => this.toggleTimingDriver(row.id)} aria-label=${`${this.w('modular.close_driver_details')} · ${row.name}`}>×</button></div>
      ${fields.length ? html`<dl>${fields.map(id => html`<div><dt>${this.timingFieldLabel(id)}</dt><dd>${this.cell(row, id)}</dd></div>`)}</dl>` : ''}
      ${this.driverDecisions(row)}
      ${history.length ? html`<h3 style="margin-top:12px">${this.w('modular.completed_laps')}</h3><ol>${history.map(lap => html`<li>${this.w('modular.lap')} ${lap.lap}: ${formatTime(lap.time)}</li>`)}</ol>` : ''}
    </section>`;
  }
  tyreCell(value, showName = true) {
    if (!value) return '—';
    const meta = compoundMeta(value), name = label(meta, this.language), style = this.settings.appearance.tyre_style;
    if (style === 'text') return html`<span class=${showName ? '' : 'sr'}>${name}</span>`;
    const image = ['image', 'both'].includes(style) && meta.asset;
    const url = image ? new URL(`../${meta.asset}`, import.meta.url) : null;
    if (url && version) url.searchParams.set('v', version);
    return html`<span class="tyre" role="img" aria-label=${`${this.w('modular.tyre')} · ${name}`}>
      <span class="compound ${image ? 'image' : ''}" aria-hidden="true" style=${`--compound-color:${meta.color ?? 'currentColor'}`}>
        ${meta.letter}${url ? html`<img src=${url.href} alt="" width="32" height="32" @load=${event => { event.target.hidden = false; }} @error=${event => { event.target.hidden = true; }}>` : ''}
      </span>${style === 'both' && showName ? html`<span aria-hidden="true">${name}</span>` : image ? html`<span class="tyre-letter" aria-hidden="true">${meta.letter}</span>` : ''}
    </span>`;
  }
  flagCell(value) {
    const flag = trackSignal(value);
    return flag ? html`<span class="track-signal"><span class="track-symbol" aria-hidden="true" style=${`background:${flag.color};color:${flag.ink}`}>${flag.symbol}</span><span>${label(flag, this.language)}</span></span>` : value ?? '—';
  }
  minisectorStatus(raw) {
    if (raw === 2051) return { id: 'overall', timing: 'overall', symbol: '◆', key: 'modular.minisector_overall_best' };
    if (raw === 2049) return { id: 'personal', timing: 'personal', symbol: '●', key: 'modular.minisector_personal_best' };
    if (raw === 2048) return { id: 'recorded', timing: 'timed', symbol: '■', key: 'modular.minisector_recorded' };
    if (raw === 0 || raw === null) return { id: 'unset', timing: 'unknown', symbol: '–', key: 'modular.minisector_not_set' };
    if (raw === 2064) return { id: 'special', timing: 'unknown', symbol: '·', key: 'modular.minisector_special_status' };
    return { id: 'unknown', timing: 'unknown', symbol: '?', key: 'modular.minisector_unknown_status' };
  }
  minisectorStrip(segments, sector = null) {
    if (!Array.isArray(segments) || !segments.length) return html`<span class="minisector-empty" aria-label=${this.w('modular.no_minisector_status_available')}>—</span>`;
    return html`<span class="minisector-strip" role="list" aria-label=${sector ? `${this.w('modular.sector')} ${sector}` : this.w('modular.minisectors')}>
      ${segments.map(segment => {
        const status = this.minisectorStatus(segment.raw), colors = statusColors(status.timing, this.settings.mode, this.settings.appearance.palette);
        const raw = status.id === 'unknown' ? ` · ${segment.raw}` : '';
        return html`<span class="minisector-block" role="listitem" data-status=${status.id} style=${`background:${colors.background};color:${colors.color}`} aria-label=${`${this.w('modular.minisector')} ${segment.index + 1}: ${this.w(status.key)}${raw}`}><span class="minisector-mark" aria-hidden="true">${status.symbol}</span></span>`;
      })}
    </span>`;
  }
  cell(row, id) {
    if (id === 'driver') return this.driverCell(row);
    if (id === 'position' && this.module.type === 'timing') return this.timingPosition(row);
    if (id === 'timing_gap') return this.combinedGapCell(row);
    if (id === 'gap' || id === 'interval') return formatTimingGap(row[id], this.w('modular.lap'));
    if (this.field(id)?.type === 'seconds_delta') {
      const part = id === 'qualifying_gap' ? this.qualifyingFocusPart() : null, value = part ? row[`q${part}_gap`] : row[id];
      return value == null ? '—' : html`<span class="time">${formatDelta(value)}</span>`;
    }
    if (this.field(id)?.type === 'qualifying_duration') {
      const value = row[id], best = this.minimalTiming && value?.overall_fastest === true;
      const colors = best ? statusColors('overall', this.settings.mode, this.settings.appearance.palette) : null;
      return html`<span class="time ${best ? 'qualifying-best' : ''}" style=${best ? `color:${colors.background}` : ''}>${best && this.settings.accessibility.signals !== 'text' ? html`<span aria-hidden="true">◆ </span>` : ''}${formatTime(value?.time)}${best ? html`<span class=${this.settings.accessibility.signals === 'shape' ? 'sr' : ''}> ${label(SIGNALS.overall, this.language)}</span>` : ''}</span><span class=${this.module.options.show_time_context !== false ? 'provenance' : 'sr'}>${value?.sprint ? 'SQ' : 'Q'}${value?.part ?? id[1]}${value?.eliminated ? this.w('modular.eliminated') : ''}</span>`;
    }
    if (id === 'theoretical_lap') return html`<span class="time">${formatTime(row[id])}</span><span class=${this.module.options.show_time_context !== false ? 'provenance' : 'sr'}>${this.w('modular.sum_of_personal_best_sectors_may_span_laps')}</span>`;
    if (/^minisector_[123]$/.test(id)) return this.minisectorStrip(row[id], Number(id.at(-1)));
    if (/^sector_[123]_with_minisectors$/.test(id)) {
      const sector = Number(id.match(/^sector_([123])/)[1]), value = row[id] ?? {};
      return html`<div class="minisector-cell">${this.timeCell(value.time)}${this.pushDeltaCell(row, sector)}${this.minisectorStrip(value.segments, sector)}</div>`;
    }
    if (/^sector_[123]$/.test(id)) return html`${this.timeCell(row[id])}${this.pushDeltaCell(row, Number(id.at(-1)))}`;
    if (FIELDS[id]?.type === 'sector' || FIELDS[id]?.type === 'duration') return this.timeCell(row[id]);
    if (id === 'lap_delta') {
      const delta = row[id];
      return delta ? html`<span class="time">${delta.symbol} ${formatDelta(delta.value)}<span class="sr"> ${this.w(({ faster: 'faster', slower: 'slower', equal: 'unchanged' })[delta.status] ?? delta.status)}</span></span><span class=${this.module.options.show_time_context !== false ? 'provenance' : 'sr'}>${this.w('modular.vs_lap')} ${delta.reference_lap}</span>` : '—';
    }
    if (id === 'tyre') return this.module.type === 'timing' && this.module.options.tyre_age_inline ? html`<span class="tyre-inline">${this.tyreCell(row.tyre)}<span title=${label(this.field('tyre_age'), this.language)}><span class="sr">${label(this.field('tyre_age'), this.language)}: </span>${row.tyre_age ?? '—'}</span></span>` : this.tyreCell(row.tyre, this.module.type !== 'tyres' || !this.model.statistics || this.module.options.show_compound_name);
    if (id === 'status') return this.w(({ in_pit: 'In pit', pit_out: 'Pit out', retired: 'Retired', stopped: 'Stopped', on_track: 'On track' })[row.status] ?? row.status ?? '—');
    return row[id] ?? '—';
  }
  timing() {
    const rows = this.model.rows ?? [], options = this.module.options;
    const configuredFields = this.module.fields.filter(id => FIELDS[id]);
    const narrow = this.module.type === 'timing' && options.narrow_layout === true;
    const part = this.qualifyingFocusPart();
    let fields = [...configuredFields];
    if (part && fields.some(id => /^q[123]_time$/.test(id))) {
      const first = fields.findIndex(id => /^q[123]_time$/.test(id));
      fields = fields.filter(id => !/^q[123]_time$/.test(id));
      fields.splice(first, 0, `q${part}_time`);
    }
    const firstGap = fields.findIndex(id => ['gap', 'interval'].includes(id));
    const combined = firstGap >= 0 && (options.gap_display === 'combined' || narrow);
    const showGapToggle = options.show_gap_toggle === true && firstGap >= 0 && !combined && !narrow;
    if (combined || showGapToggle) {
      const insertion = fields.slice(0, firstGap).filter(id => !['gap', 'interval'].includes(id)).length;
      fields = fields.filter(id => !['gap', 'interval'].includes(id));
      fields.splice(insertion, 0, combined ? 'timing_gap' : this.timingGapMode === 'leader' ? 'gap' : 'interval');
    }
    if (options.tyre_age_inline && fields.includes('tyre')) fields = fields.filter(id => id !== 'tyre_age');
    if (narrow) {
      // Summary is an explicit layout choice. Keep all saved timing columns in
      // the expandable driver details rather than changing the saved fields.
      fields = ['position', 'driver', ...fields.filter(id => ['timing_gap', 'qualifying_gap', 'best_lap_gap', 'tyre'].includes(id))];
    }
    if (!rows.length) {
      if (this.model.pushMode === 'only') {
        const key = ({ waiting: 'modular.push_laps_waiting', unavailable: 'modular.push_laps_unavailable', unsupported: 'modular.push_laps_unsupported' })[this.model.pushStatus]
          ?? (this.model.filtered ? 'modular.push_laps_no_match' : 'modular.push_laps_none');
        return this.empty(this.w(key));
      }
      return this.empty(this.model.filtered ? this.w('modular.no_drivers_match_this_selection') : this.w('modular.timing_will_appear_when_session_data_is_available'));
    }
    if (!fields.length) return this.empty(this.w('modular.choose_columns_in_the_editor'));
    const historyLimit = options.history;
    const detailsEnabled = this.module.type === 'timing' && (narrow || options.show_driver_details !== false);
    const represented = id => fields.includes(id) || combined && ['gap', 'interval'].includes(id) || options.tyre_age_inline && fields.includes('tyre') && id === 'tyre_age';
    const detailFields = detailsEnabled ? [...new Set([...(narrow || part ? configuredFields : []), ...(this.module.detail_fields ?? [])])]
      .filter(id => FIELDS[id] && id !== 'driver' && !represented(id)) : [];
    const detailLaps = detailsEnabled ? Math.max(options.detail_laps ?? 0, narrow ? historyLimit ?? 0 : 0) : 0;
    const lapNumbers = historyLimit && !narrow ? [...new Set(rows.flatMap(row => (row.history ?? []).map(lap => lap.lap)).filter(Number.isInteger))].sort((a, b) => a - b).slice(-historyLimit) : [];
    this.timingDetailRows = new Set(rows.filter(row => detailsEnabled && (detailFields.length > 0 || options.driver_badges && row.badges?.length || (row.history ?? []).slice(0, detailLaps).some(lap => !lapNumbers.includes(lap.lap)))).map(row => row.id));
    const gapToggle = showGapToggle ? html`<div class="timing-gap-toggle" part="controls" role="group" aria-label=${this.w('modular.gap_mode')}>
      <button data-focus="timing-gap-ahead" aria-pressed=${String(this.timingGapMode === 'ahead')} @click=${() => { this.timingGapMode = 'ahead'; }}>${this.w('modular.ahead')}</button>
      <button data-focus="timing-gap-leader" aria-pressed=${String(this.timingGapMode === 'leader')} @click=${() => { this.timingGapMode = 'leader'; }}>${this.w('modular.leader')}</button>
    </div>` : '';
    const closeAll = this.module.type === 'timing' && this.timingExpanded.length ? html`<div class="timing-detail-actions" part="controls"><button data-focus="timing-close-all" @click=${() => this.clearTimingDrivers()}>${this.w('modular.close_all_driver_details')}</button></div>` : '';
    const focusContext = part ? html`<p class="module-context">${this.w('modular.timing_qualifying_focus_context', { part: `${this.model.sessionKind === 'sprint_qualifying' ? 'SQ' : 'Q'}${part}` })}</p>` : '';
    return html`${focusContext}${gapToggle}${closeAll}<div class=${`table-scroll ${narrow ? 'timing-summary' : ''} ${this.minimalTiming && fields.some(id => /^sector_[123]_with_minisectors$|^minisector_[123]$/.test(id)) ? 'compact-minisectors' : ''}`} part="table-container" tabindex="0" role="region" aria-label=${this.w(narrow ? 'modular.timing_summary_label' : 'modular.timing_table_scroll_horizontally_for_more_columns')}><table part="table">
      <caption class="sr">${this.module.title || this.model.title}</caption>
      ${this.timingHeader(fields, lapNumbers)}
      <tbody>${repeat(rows, row => row.id, (row, index) => html`${this.model.pushMode !== 'off' && row.push_group && (index === 0 || row.push_group !== rows[index - 1].push_group) ? html`<tr class="push-group" data-group=${row.push_group}><th colspan=${fields.length + lapNumbers.length} scope="colgroup">${this.w(({ active: 'modular.push_laps', completed: 'modular.completed_attempts', other: 'modular.other_drivers' })[row.push_group])}${row.push_group === 'active' ? html`<span class="provenance">${this.w(this.model.pushOrderUnknown ? 'modular.push_laps_order_incomplete' : 'modular.push_laps_order')}</span>` : ''}</th></tr>` : ''}<tr part="table-row" data-driver=${row.id} data-push-group=${row.push_group ?? ''} data-retired=${String(options.dim_retired === true && row.retired === true)}>${repeat(fields, id => id, id => html`<td part="table-cell" data-field=${id} data-field-type=${this.field(id)?.type ?? ''}>${this.cell(row, id)}${!fields.includes('driver') && id === fields[0] ? this.pushLapMarker(row) : ''}</td>`)}${repeat(lapNumbers, lap => lap, (lap, index) => {
        const value = (row.history ?? []).find(item => item.lap === lap);
        return html`<td part="table-cell" class=${`recent-lap ${index === 0 ? 'lap-start' : ''}`}>${this.timeCell(value ? { ...value, source: 'completed_lap', previous_lap: true } : { time: null, lap })}</td>`;
      })}</tr>
        ${this.module.type === 'timing' && this.timingExpanded.includes(row.id) && this.timingDetailRows.has(row.id) ? html`<tr class="timing-detail-row" part="table-row driver-detail-row"><td part="table-cell" colspan=${fields.length + lapNumbers.length}>${this.timingDetailPanel(row, detailFields, detailLaps, lapNumbers)}</td></tr>` : ''}
        ${this.module.type !== 'timing' && this.expanded === row.id ? html`<tr part="table-row"><td part="table-cell" class="details" colspan=${fields.length + lapNumbers.length}>
          <h3>${row.name} · ${row.team ?? '—'}</h3><dl>${fields.filter(id => id !== 'driver').map(id => html`<div><dt class="muted">${label(this.field(id), this.language)}</dt><dd>${this.cell(row, id)}</dd></div>`)}</dl>
          ${row.history?.length ? html`<h3 style="margin-top:16px">${this.w('modular.completed_laps')}</h3><ol>${row.history.map(lap => html`<li>${this.w('modular.lap')} ${lap.lap}: ${formatTime(lap.time)}</li>`)}</ol>` : ''}
        </td></tr>` : ''}`)}</tbody>
    </table></div>${this.timingLegend([...fields, ...detailFields])}`;
  }
  timingLegend(fields = []) {
    const hasMinisectors = fields.some(id => /^minisector_[123]$|^sector_[123]_with_minisectors$/.test(id));
    if (this.module.type === 'minisectors' && this.module.options.show_legend === false) return '';
    const meanings = {
      overall: ['Fastest in the relevant session or qualifying part.', 'Snabbast i relevant session eller kvaldel.'],
      personal: ["This driver's best in the relevant comparison."],
      timed: ['Yellow means recorded, not necessarily slower than the previous lap.'],
      previous: ['A completed or older lap. Read the lap number beside each time.'],
      deleted: ['The time has been deleted and cannot be a valid best time.'],
      invalid: ['The source marks this time as invalid.'],
      unknown: ['No usable time is available. A dash does not mean zero.'],
    };
    return html`<details class="timing-legend"><summary data-focus="timing-legend">${hasMinisectors ? this.w('modular.timing_and_minisector_status_explained') : this.w('modular.timing_explained')}</summary>
      <dl>${Object.entries(meanings).map(([status, explanation]) => html`<div><dt><span aria-hidden="true">${SIGNALS[status].symbol} </span><span>${label(SIGNALS[status], this.language)}</span></dt><dd>${this.w(...explanation)}</dd></div>`)}</dl>
      ${hasMinisectors ? html`<p>${this.w('modular.minisectors_provider_status_only')}</p>
        <ul class="minisector-legend">${[2051, 2049, 2048, 0, 2064, -1].map(raw => { const status = this.minisectorStatus(raw), colors = statusColors(status.timing, this.settings.mode, this.settings.appearance.palette); return html`<li><span class="minisector-block" data-status=${status.id} style=${`background:${colors.background};color:${colors.color}`} aria-hidden="true"><span class="minisector-mark">${status.symbol}</span></span><span>${this.w(status.key)}</span></li>`; })}</ul>` : ''}
      <p>${this.w('modular.deleted_or_invalid_status_takes_priority_over_best_time_markings_older_sectors_use_the')}</p>
      <p>${this.module.options.sectors === 'latest'
        ? this.w('modular.latest_sectors_can_come_from_different_laps_each_older_sector_is_marked_with_its')
        : this.w('modular.sectors_follow_the_same_lap_the_completed_lap_stays_until_the_next_s1_arrives')}</p>
      <p>${this.w('modular.lap_change_faster_slower_unchanged_at_the_displayed_precision_compared_with_the_previous_completed')}</p>
      <p>${this.w('modular.personal_best_sectors_may_come_from_different_laps_their_sum_is_a_theoretical_lap')}</p>
      ${this.model.pushDeltas ? html`<p>${this.w('modular.push_delta_explained')}</p>` : ''}
    </details>`;
  }
  events() {
    const rows = this.module.options.presentation === 'latest_message' && this.module.options.min_display_time > 0 ? [this.raceShown].filter(Boolean) : this.model.rows ?? [];
    const height = this.module.options.presentation === 'list' ? this.module.options.list_max_height : 0;
    const request = this.model.request, canClear = this.module.options.presentation === 'list' && this.module.options.show_clear_button;
    const controls = canClear ? html`<div class="replay-controls" part="controls"><button data-focus="race-control-clear" ?disabled=${this.model.readonly || request?.pending} @click=${this.clearRaceControl}>${request?.pending ? this.w('modular.clearing') : this.clearConfirm ? this.w('modular.confirm_clear') : this.w('modular.clear_saved_messages')}</button></div>
      ${request?.busy ? html`<p class="muted">${this.w('modular.another_race_control_action_is_already_running')}</p>` : request?.error ? html`<p class="muted">${this.w('modular.saved_messages_could_not_be_cleared')}</p>` : ''}` : '';
    if (!rows.length) return html`${this.module.options.show_fia_logo ? html`<p class="document-summary"><strong class="chip">FIA</strong></p>` : ''}${this.empty(this.w('modular.no_matching_messages_yet'))}${controls}`;
    if (this.compactPresentation) return html`${this.module.options.show_fia_logo ? html`<p class="document-summary"><strong class="chip">FIA</strong></p>` : ''}${this.compactEvents(rows, height)}${controls}`;
    return html`${this.module.options.show_fia_logo ? html`<p class="document-summary"><strong class="chip">FIA</strong></p>` : ''}<ol class="events" style=${height ? `max-height:${height}px` : ''} tabindex="0" aria-label="Race Control">${repeat(rows, row => row.id, row => html`<li data-event=${row.id}>
      <div class="event-meta">${this.module.fields.includes('event_time') ? html`<time datetime=${row.utc ?? ''}>${dateTime(row.utc ?? row.received_at, this.settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>` : ''}
      ${row.flag ? this.flagCell(row.flag) : ''}${row.car_number ? html`<span>${this.w('modular.car')} ${row.car_number}</span>` : ''}<span>${row.category}</span></div>
      ${this.module.fields.includes('message') ? html`<p>${row.message}</p>` : ''}
    </li>`)}</ol>${controls}`;
  }
  compactEvents(rows, height) {
    const showTime = this.module.fields.includes('event_time'), showMessage = this.module.fields.includes('message');
    return html`<ol class="events compact-events" style=${height ? `max-height:${height}px` : ''} tabindex="0" aria-label="Race Control">${repeat(rows, row => row.id, row => {
      const timestamp = row.utc ?? row.received_at;
      const knownTime = timestamp !== null && timestamp !== undefined && timestamp !== '' && Number.isFinite(new Date(timestamp).getTime());
      return html`<li class=${showTime ? 'has-time' : ''} data-event=${row.id}>
        ${showTime ? html`<time class="compact-event-time" datetime=${row.utc ?? ''}>${dateTime(timestamp, this.settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>` : ''}
        <div class="compact-event-content">${showMessage ? html`<p class="compact-event-message">${row.message}</p>` : ''}
          <div class="compact-event-meta">${row.flag ? this.flagCell(row.flag) : ''}${row.car_number ? html`<span>${this.w('modular.car')} ${row.car_number}</span>` : ''}<span>${row.category}</span>
            ${showTime && knownTime ? html`<details class="compact-event-details"><summary data-focus=${`race-control-details-${row.id}`}>${this.w('modular.details')}</summary><time class="compact-event-timestamp" datetime=${timestamp}>${dateTime(timestamp, this.settings, { dateStyle: 'medium', timeStyle: 'long' })}</time></details>` : ''}
          </div>
        </div>
      </li>`;
    })}</ol>`;
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
