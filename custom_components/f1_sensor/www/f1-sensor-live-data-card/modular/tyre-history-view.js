const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, css, repeat }, { sharedStyles, words }, { compoundMeta }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./view.js'), load('./semantics.js'),
]);

export class F1TyreHistoryView extends LitElement {
  static properties = { model: { attribute: false }, module: { attribute: false }, settings: { attribute: false }, expanded: { state: true } };
  static styles = [sharedStyles, css`
    :host { container-type:inline-size; }
    .lap-progress { text-align:end; font-size:.85em; margin-bottom:12px; color:var(--f1-muted); }
    .history { --identity-width:7rem; --age-width:4.5rem; }
    .history.no-age { --age-width:0px; }
    .history-axis,.driver-row { display:grid; grid-template-columns:var(--identity-width) minmax(0,1fr) var(--age-width); gap:10px; align-items:center; }
    .history-axis { padding:0 7px; margin:0 0 10px; font-size:.8em; color:var(--f1-muted); }
    .history-axis > :last-child { text-align:end; white-space:normal; }
    .axis { position:relative; height:28px; margin-top:4px; border-bottom:1px solid var(--f1-divider); }
    .axis span { position:absolute; transform:translateX(-50%); font-variant-numeric:tabular-nums; }
    .axis span:first-child { transform:none; }
    .axis span:last-child { transform:translateX(-100%); }
    .drivers { list-style:none; padding:0; margin:0; }
    .drivers > li { margin:0; padding:0; }
    .driver-row { width:100%; min-width:0; min-height:28px; padding:3px 6px; border:1px solid transparent; border-radius:5px; background:transparent; text-align:start; font-size:.9em; line-height:1.25; }
    .driver-row[aria-expanded=true] { border-color:var(--f1-border); background:var(--f1-hover); }
    .driver-identity { display:flex; align-items:center; gap:6px; min-width:0; }
    .position { min-width:1.3em; color:var(--f1-muted); font-size:.9em; font-variant-numeric:tabular-nums; }
    .team-accent { width:3px; height:16px; flex:0 0 3px; border-radius:2px; background:var(--team-color,var(--f1-border)); }
    .driver-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .chevron { width:10px; flex:0 0 10px; --mdc-icon-size:12px; }
    .lane { position:relative; display:block; height:1.25em; min-height:16px; min-width:0; overflow:hidden; border-radius:2px; background:var(--f1-panel); }
    .segment { position:absolute; top:0; bottom:0; display:flex; align-items:center; padding:0 4px; overflow:hidden; background:var(--compound-color,var(--f1-border)); color:#111; font-size:max(.85em,11px); line-height:1.2; font-weight:750; font-variant-numeric:tabular-nums; box-shadow:inset 1px 0 color-mix(in srgb,var(--f1-surface) 75%,transparent); }
    .segment span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .segment.unknown { color:var(--f1-text); }
    .segment.used { background-image:repeating-linear-gradient(135deg,transparent,transparent 4px,rgba(0,0,0,.2) 4px,rgba(0,0,0,.2) 6px); }
    .cursor { position:absolute; top:0; bottom:0; border-inline-start:2px dashed var(--f1-text); pointer-events:none; }
    .age { text-align:end; font-variant-numeric:tabular-nums; font-weight:650; }
    .missing-range { display:block; overflow:hidden; text-overflow:ellipsis; font-size:.7em; white-space:nowrap; padding:3px 5px; color:var(--f1-muted); }
    .driver-detail { padding:10px 8px 16px; border-bottom:1px solid var(--f1-divider); margin-bottom:8px; }
    .detail-scroll { overflow:auto; scrollbar-gutter:stable; }
    .stints { min-width:450px; font-size:.85em; }
    .stints caption { text-align:start; margin-bottom:6px; }
    .stints th { background:transparent; white-space:normal; }
    .stints th,.stints td { padding:8px 10px; }
    .stints th:not(:first-child),.stints td:not(:first-child) { text-align:end; }
    .stints tbody tr { background:transparent; }
    .stints tbody tr:last-child td { border-bottom:1px solid var(--f1-divider); }
    .compound { display:inline-flex; justify-content:center; align-items:center; min-width:24px; height:24px; padding:0 4px; border-radius:4px; background:var(--compound-color,var(--f1-panel)); color:#111; font-weight:750; flex:0 0 auto; }
    .compound.unknown { color:var(--f1-text); }
    .stint-identity { display:flex; align-items:center; gap:8px; }
    .stint-status { display:block; margin-inline-start:32px; color:var(--f1-muted); font-size:.9em; }
    .partial { margin-top:8px; font-size:.8em; color:var(--f1-muted); }
    .legend { display:flex; flex-wrap:wrap; gap:8px 18px; list-style:none; padding:14px 0 0; margin:14px 0 0; border-top:1px solid var(--f1-divider); font-size:.8em; }
    .legend li { display:flex; align-items:center; gap:6px; }
    .used-key { display:inline-block; width:24px; height:20px; background:repeating-linear-gradient(135deg,transparent,transparent 3px,var(--f1-muted) 3px,var(--f1-muted) 5px); }
    @container (max-width:420px) {
      .history { --identity-width:5.2rem; --age-width:3.3rem; }
      .history.no-age { --age-width:0px; }
      .history-axis,.driver-row { gap:5px; padding-inline:2px; }
      .history-axis { padding-inline:3px; }
      .driver-identity { gap:4px; }
      .driver-name { max-width:3.5em; }
      .team-accent { width:3px; flex-basis:3px; }
      .axis .minor { display:none; }
      .segment { padding-inline:2px; font-size:max(.8em,11px); }
      .driver-detail { padding-inline:0; }
    }
    @media (forced-colors:active) {
      .segment,.compound { forced-color-adjust:none; background:Canvas!important; color:CanvasText!important; box-shadow:inset 0 0 0 1px CanvasText; }
      .segment.used { background:repeating-linear-gradient(135deg,Canvas,Canvas 4px,GrayText 4px,GrayText 6px)!important; }
      .lane { background:Canvas; outline:1px solid GrayText; }
      .driver-row[aria-expanded=true] { border-color:Highlight; }
      .team-accent { background:CanvasText!important; }
    }
  `];
  constructor() { super(); this.expanded = ''; }
  w(key, replacements = {}) { return words(this.settings?.language ?? 'en', key, replacements); }
  value(value) { return value == null ? '—' : new Intl.NumberFormat(this.settings?.language ?? 'en').format(value); }
  willUpdate() {
    const context = JSON.stringify([this.module?.id, this.model?.context?.key, this.model?.selectionGeneration]);
    if (context !== this.context) { this.context = context; this.expanded = ''; }
    if (!(this.model?.rows ?? []).some(row => row.id === this.expanded)) this.expanded = '';
    this.focusKey = this.shadowRoot?.activeElement?.dataset?.driver ?? null;
  }
  updated() {
    if (this.focusKey && this.shadowRoot?.activeElement?.dataset?.driver !== this.focusKey) {
      [...this.shadowRoot.querySelectorAll('button[data-driver]')].find(button => button.dataset.driver === this.focusKey)?.focus({ preventScroll: true });
    }
  }
  badge(value) {
    const compound = compoundMeta(value);
    return html`<span class=${`compound ${compound.color ? '' : 'unknown'}`} style=${`--compound-color:${compound.color ?? 'var(--f1-panel)'}`} aria-label=${this.w(compound.label)}>${compound.letter}</span>`;
  }
  detail(row, id) {
    const stints = row.stints ?? [];
    return html`<div class="driver-detail" id=${id} part="tyre-history-detail">
      ${stints.length ? html`<div class="detail-scroll" tabindex="0"><table class="stints">
        <caption class="sr">${this.w('modular.tyre_history_known_stints')}</caption>
        <thead><tr><th scope="col">${this.w('modular.stint')}</th><th scope="col">${this.w('modular.tyre_history_race_laps')}</th><th scope="col">${this.w('modular.tyre_history_in_stint')}</th><th scope="col">${this.w('modular.tyre_history_before_stint')}</th><th scope="col">${this.w('modular.tyre_history_total_age')}</th></tr></thead>
        <tbody>${repeat(stints, stint => stint.id, stint => html`<tr data-stint=${stint.id}><td><span class="stint-identity">${this.badge(stint.tyre)}<strong>${this.value(stint.stint_number)} · ${this.w(compoundMeta(stint.tyre).label)}</strong></span><span class="stint-status">${stint.status == null ? '—' : this.w(stint.status === 'current' ? 'modular.tyre_history_current' : 'modular.tyre_history_completed')}${stint.start_age > 0 || stint.tyre_new === false ? ` · ${this.w('modular.tyre_history_used')}` : ''}</span></td>
          <td>${stint.first_lap == null || stint.last_lap == null ? '—' : `${this.value(stint.first_lap)}–${this.value(stint.last_lap)}`}</td><td>${this.value(stint.stint_laps)}</td><td>${this.value(stint.start_age)}</td><td>${this.value(stint.total_age)}</td></tr>`)}</tbody>
      </table></div>` : html`<p class="muted">${this.w('modular.tyre_history_missing')}</p>`}
      ${!row.history_complete ? html`<p class="partial">${this.w('modular.tyre_history_partial')}</p>` : ''}
    </div>`;
  }
  render() {
    const rows = this.model?.rows ?? [];
    if (!rows.length) return html`<p class="empty">${this.w('modular.tyre_history_missing')}</p>`;
    const axis = this.model.axis ?? {}, knownAxis = Number.isFinite(axis.max) && axis.max > 0;
    const max = knownAxis ? axis.max : 1, current = axis.current;
    const showAge = this.module.fields.includes('tyre_age'), showPosition = this.module.fields.includes('position');
    const step = Math.max(1, Math.ceil(max / 6 / 5) * 5);
    const ticks = [0];
    for (let tick = step; tick < max; tick += step) if (max - tick >= max * .12) ticks.push(tick);
    ticks.push(max);
    return html`<div class=${`history ${showAge ? '' : 'no-age'}`}>
      ${current != null ? html`<p class="lap-progress">${this.w('modular.tyre_history_lap_progress', { current: this.value(current), total: this.value(axis.total) })}</p>` : ''}
      <div class="history-axis"><span class="sr">${this.w('modular.tyre_history_axis')}</span><span></span><div class="axis" aria-hidden="true">${knownAxis ? ticks.map((tick, index) => html`<span class=${index > 0 && index < ticks.length - 1 ? 'minor' : ''} style=${`left:${tick / max * 100}%`}>${this.value(tick)}</span>`) : ''}</div>${showAge ? html`<span>${this.w('modular.tyre_history_total_age')}</span>` : ''}</div>
      <ol class="drivers">${repeat(rows, row => row.id, row => {
        const open = this.expanded === row.id, detailId = `stints-${encodeURIComponent(row.id)}`;
        const name = this.settings?.appearance?.full_names ? row.name : row.driver;
        const drawable = knownAxis ? (row.stints ?? []).filter(stint => stint.drawable) : [];
        return html`<li data-tyre-driver=${row.id}><button class="driver-row" part="tyre-history-row" data-driver=${row.id} aria-expanded=${String(open)} aria-controls=${detailId} aria-describedby=${`${detailId}-summary`} aria-label=${this.w(open ? 'modular.tyre_history_collapse' : 'modular.tyre_history_expand', { driver: name })} @click=${() => { this.expanded = open ? '' : row.id; }}>
          <span class="driver-identity">${showPosition ? html`<span class="position">${this.value(row.position)}</span>` : ''}<span class="team-accent" style=${`--team-color:${this.settings?.appearance?.team_colors !== false ? row.team_color ?? 'var(--f1-border)' : 'var(--f1-border)'}`}></span><strong class="driver-name">${name}</strong><ha-icon class="chevron" icon=${open ? 'mdi:chevron-down' : 'mdi:chevron-right'} aria-hidden="true"></ha-icon></span>
          <span class="lane" aria-hidden="true">${repeat(drawable, stint => stint.id, stint => {
            const compound = compoundMeta(stint.tyre), left = (stint.first_lap - 1) / max * 100, width = (stint.last_lap - stint.first_lap + 1) / max * 100;
            return html`<span class=${`segment ${stint.start_age > 0 || stint.tyre_new === false ? 'used' : ''} ${compound.color ? '' : 'unknown'}`} data-stint=${stint.id} style=${`left:${left}%;width:${width}%;--compound-color:${compound.color ?? 'var(--f1-border)'}`}><span>${compound.letter} ${this.value(stint.stint_laps)}</span></span>`;
          })}${!drawable.length ? html`<span class="missing-range">${this.w('modular.tyre_history_no_range')}</span>` : ''}${current != null && current <= max ? html`<span class="cursor" style=${`left:${current / max * 100}%`}></span>` : ''}</span>
          ${showAge ? html`<span class="age">${this.value(row.tyre_age)}</span>` : ''}
        </button><span class="sr" id=${`${detailId}-summary`}>${this.w('modular.tyre_history_total_age')}: ${this.value(row.tyre_age)}. ${(row.stints ?? []).map(stint => this.w('modular.tyre_history_segment', { compound: this.w(compoundMeta(stint.tyre).label), laps: this.value(stint.stint_laps) })).join('. ')}</span>${open ? this.detail(row, detailId) : html`<div id=${detailId} hidden></div>`}</li>`;
      })}</ol>
      ${this.module.options.show_legend !== false ? html`<ul class="legend" part="tyre-history-legend">${['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET'].map(value => html`<li>${this.badge(value)}<span>${this.w(compoundMeta(value).label)}</span></li>`)}<li><span class="used-key" aria-hidden="true"></span><span>${this.w('modular.tyre_history_used')}</span></li></ul>` : ''}
    </div>`;
  }
}
if (!customElements.get('f1-tyre-history-view')) customElements.define('f1-tyre-history-view', F1TyreHistoryView);
