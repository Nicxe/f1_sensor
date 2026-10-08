const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, svg, css }, { sharedStyles, words }, { CHANNELS, telemetrySegments }, { chartAxis }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./view.js'), load('./telemetry-data.js'), load('./season-data.js'),
]);
const patterns = ['', '9 4', '2 4', '10 3 2 3'];
const colors = { dark: ['#75baff', '#ffb673', '#92d99f', '#d9a7ff'], light: ['#145f9e', '#994100', '#226a33', '#77409b'] };
const symbols = ['●', '■', '▲', '◆'];
export class F1TelemetryView extends LitElement {
  static properties = { model: { attribute: false }, module: { attribute: false }, settings: { attribute: false }, pickerOnly: { type: Boolean }, draftDriver: { state: true }, draftLap: { state: true }, table: { state: true }, width: { state: true }, textSize: { state: true } };
  static styles = [sharedStyles, css`
    details > summary { cursor:pointer; min-height:44px; display:list-item; padding:10px 0; font-weight:650; }
    .pickers { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin:14px 0; }
    label { display:grid; gap:4px; min-width:0; position:relative; }
    label::after { content:"⌄"; position:absolute; right:12px; bottom:10px; pointer-events:none; }
    select { appearance:none; width:100%; min-height:44px; padding:8px 32px 8px 8px; border:1px solid var(--f1-border); background:var(--f1-surface); border-radius:8px; }
    .selections { list-style:none; padding:0; margin:12px 0; }
    .selections li { display:flex; align-items:center; flex-wrap:wrap; gap:8px; padding:5px 0; overflow-wrap:anywhere; }
    .selections li span { flex:1; min-width:120px; }
    .controls { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin:12px 0; }
    .plot { width:100%; height:auto; display:block; }
    .axis { font-size:.8em; fill:var(--f1-muted); }
    .grid { stroke:var(--f1-divider); }
    .curve { fill:none; stroke-width:2.5; stroke-linecap:round; stroke-linejoin:round; }
    .legend { list-style:none; padding:0; display:flex; flex-wrap:wrap; gap:8px 18px; font-size:.85em; }
    .legend li { display:flex; align-items:center; gap:6px; }
    .sample { width:32px; height:16px; }
    h3 { margin:22px 0 8px; font-size:1em; }
    .muted { font-size:.85em; }
    .table-scroll { max-height:28rem; }
    @media(forced-colors:active) { .curve,.dot { stroke:CanvasText!important; } .dot { fill:Canvas!important; } .axis { fill:CanvasText; } .grid { stroke:GrayText; } }
  `];
  constructor() { super(); this.draftDriver = ''; this.draftLap = ''; this.table = ''; this.width = 620; this.textSize = 16; }
  connectedCallback() {
    super.connectedCallback(); this.observer = new ResizeObserver(entries => {
      const width = Math.round(entries[0]?.contentRect.width ?? 0);
      if (width > 0) this.width = Math.max(280, width);
      this.textSize = parseFloat(getComputedStyle(this).fontSize) || 16;
    }); this.observer.observe(this);
  }
  disconnectedCallback() { super.disconnectedCallback(); this.observer?.disconnect(); }
  willUpdate() {
    if (this.session !== this.model?.replay?.sessionId) { this.session = this.model?.replay?.sessionId; this.draftDriver = ''; this.draftLap = ''; this.table = ''; }
  }
  w(en, sv) { return words(this.settings?.language, en, sv); }
  value(value) { return value == null ? '—' : new Intl.NumberFormat(this.settings?.language ?? 'en', { maximumFractionDigits: 3 }).format(value); }
  title(key) { const field = CHANNELS[key]; return field ? `${this.w(field.en, field.sv)}${field.unit ? ` (${field.unit})` : ''}` : ''; }
  seriesName(item) { return `${item.name} · ${this.w('modular.lap_300caf91')} ${item.lap}`; }
  send(type, values = {}) { this.dispatchEvent(new CustomEvent(`f1-telemetry-${type}`, { bubbles: true, composed: true, detail: { module: this.module.id, sessionId: this.model.replay.sessionId, ...values } })); }
  select(selected) { this.send('selection', { selected }); }
  picker() {
    const model = this.model, disabled = Boolean(model.readonly || !model.replay.loaded || model.loading || model.error || model.disconnected || model.selectionChanged);
    const driver = model.drivers.find(driver => driver.id === this.draftDriver), lap = driver?.laps.includes(Number(this.draftLap)) ? this.draftLap : String(driver?.laps[0] ?? '');
    const candidate = driver && lap ? `${driver.id}:${lap}` : '';
    return html`<p><strong>${model.replay.selectedSession ?? this.w('modular.replay_session')}</strong></p>
      ${!model.replay.loaded ? html`<p class="empty">${this.w('modular.load_a_replay_to_choose_recorded_laps_the_replay_status_and_player_entities_must')}</p>` : ''}
      ${model.selectionChanged ? html`<p class="empty">${this.w('modular.saved_laps_belong_to_another_replay_clear_them_before_choosing_laps_from_this_session')}</p><button ?disabled=${model.readonly} @click=${() => this.select([])}>${this.w('modular.clear_saved_laps')}</button>` : ''}
      ${model.loading ? html`<p role="status">${this.w('modular.reading_recorded_lap_list')}</p>` : model.error || model.disconnected ? html`<p class="empty">${this.w('modular.the_lap_list_is_unavailable_check_the_replay_and_f1_sensor_version')}</p>${!model.disconnected ? html`<button ?disabled=${model.readonly} @click=${() => this.send('retry')}>${this.w('modular.retry_lap_list')}</button>` : ''}` : ''}
      ${model.selected.length ? html`<ul class="selections">${model.selected.map(id => { const [driverId, lapId] = id.split(':'), driver = model.drivers.find(driver => driver.id === driverId); return html`<li><span>${driver?.name ?? driverId} · ${this.w('modular.lap_300caf91')} ${lapId}${model.missing.includes(id) && !model.selectionChanged ? ` · ${this.w('modular.not_recorded')}` : ''}</span><button aria-label=${`${this.w('modular.remove_lap')} ${id}`} ?disabled=${model.readonly || model.selectionChanged} @click=${() => this.select(model.selected.filter(item => item !== id))}>${this.w('modular.remove')}</button></li>`; })}</ul>` : ''}
      ${model.replay.loaded && !model.selectionChanged ? html`<div class="pickers"><label><span>${this.w('modular.driver_to_add')}</span><select aria-label=${this.w('modular.driver_to_add')} .value=${driver?.id ?? ''} ?disabled=${disabled || model.selected.length >= 4} @change=${event => { this.draftDriver = event.target.value; this.draftLap = ''; }}><option value="">${this.w('modular.choose_driver')}</option>${model.drivers.map(driver => html`<option value=${driver.id}>${driver.name}</option>`)}</select></label>
      <label><span>${this.w('modular.recorded_lap')}</span><select aria-label=${this.w('modular.recorded_lap')} .value=${lap} ?disabled=${disabled || !driver || model.selected.length >= 4} @change=${event => { this.draftLap = event.target.value; }}>${(driver?.laps ?? []).map(lap => html`<option value=${String(lap)}>${lap}</option>`)}</select></label></div>
      <button ?disabled=${disabled || !candidate || model.selected.includes(candidate) || model.selected.length >= 4} @click=${() => this.select([...model.selected, candidate])}>${this.w('modular.add_lap')}</button>` : ''}
      <p class="muted">${this.w('modular.choose_up_to_four_laps_the_list_confirms_recorded_lap_boundaries_telemetry_availability_is')}</p>`;
  }
  plot(channel) {
    const model = this.model, axis = model.options.axis, colorsForMode = colors[this.settings?.mode] ?? colors.dark;
    const plotted = model.series.map(item => ({ ...item, segments: telemetrySegments(item.samples, channel, axis) }));
    const points = plotted.flatMap(item => item.segments.flat());
    if (!points.length) return html`<p class="empty">${this.w('modular.no_recorded_values_for_this_curve')}</p>`;
    const { low, high, ticks } = chartAxis(points.map(point => point.y), ['gear', 'drs'].includes(channel), ['throttle', 'brake'].includes(channel));
    const first = Math.min(...points.map(point => point.x)), last = Math.max(...points.map(point => point.x)), width = this.width, font = this.textSize;
    const left = Math.min(width * .35, Math.max(52, font * 4)), right = width - 22, height = Math.max(230, font * 13), bottom = height - font * 3.5, top = font;
    const x = value => last === first ? (left + right) / 2 : left + (value - first) / (last - first) * (right - left), y = value => bottom - (value - low) / (high - low) * (bottom - top);
    const xLabel = axis === 'distance' ? this.w('modular.estimated_distance_m') : this.w('modular.time_from_lap_start_s');
    return html`<svg class="plot" viewBox=${`0 0 ${width} ${height}`} role="img" aria-label=${`${this.title(channel)}. ${xLabel}. ${this.w('modular.recorded_samples_and_gaps_are_available_in_the_data_table')}`}><title>${this.title(channel)}</title>
      ${ticks.map(value => svg`<line class="grid" x1=${left} x2=${right} y1=${y(value)} y2=${y(value)}/><text class="axis" x=${left - 8} y=${y(value) + 4} text-anchor="end">${this.value(value)}</text>`)}
      ${[first, ...(width > 460 ? [(first + last) / 2] : []), last].map(value => svg`<text class="axis" x=${x(value)} y=${bottom + font * 1.4} text-anchor="middle">${this.value(Math.round(value * 10) / 10)}</text>`)}
      <text class="axis" x=${(left + right) / 2} y=${height - font * .5} text-anchor="middle">${xLabel}</text>
      ${plotted.map((item, index) => svg`<g data-series=${item.id} aria-hidden="true">${item.segments.map(segment => segment.length === 1 ? svg`<circle class="dot" cx=${x(segment[0].x)} cy=${y(segment[0].y)} r="3" style=${`fill:${colorsForMode[index]};stroke:${colorsForMode[index]}`}/>` : svg`<path class="curve" d=${segment.map((point, i) => i && ['gear', 'drs', 'brake'].includes(channel) ? `H${x(point.x)}V${y(point.y)}` : `${i ? 'L' : 'M'}${x(point.x)},${y(point.y)}`).join(' ')} style=${`stroke:${colorsForMode[index]};stroke-dasharray:${patterns[index]}`}/>` )}</g>`)}
      </svg><ul class="legend">${model.series.map((item, index) => html`<li><svg class="sample" viewBox="0 0 32 16" aria-hidden="true"><path class="curve" d="M1 8 L31 8" style=${`stroke:${colorsForMode[index]};stroke-dasharray:${patterns[index]}`}/></svg><span>${symbols[index]} ${this.seriesName(item)}</span></li>`)}</ul>`;
  }
  dataTable(item, channels) {
    return html`<div class="table-scroll" role="region" tabindex="0" aria-label=${this.seriesName(item)}><table><caption>${this.seriesName(item)} · ${this.w('modular.bounded_recorded_samples')}</caption><thead><tr><th scope="col">${this.w('modular.time_s')}</th><th scope="col">${this.w('modular.estimated_distance_m')}</th>${channels.map(channel => html`<th scope="col">${this.title(channel)}</th>`)}<th scope="col">${this.w('modular.recorded_gap')}</th></tr></thead><tbody>${item.samples.map((sample, index) => html`<tr><th scope="row">${this.value(sample.time_s)}</th><td>${this.value(sample.distance)}</td>${channels.map(channel => html`<td>${this.value(sample[channel])}</td>`)}<td>${sample.gap_before || index && sample.time_s - item.samples[index - 1].time_s > 2 ? this.w('modular.gap_before_sample') : '—'}</td></tr>`)}</tbody></table></div>`;
  }
  render() {
    if (!this.model || !this.module) return html``;
    const model = this.model, channels = model.fields.map(id => id.replace(/^telemetry_/, '')).filter(id => CHANNELS[id]);
    const presentation = model.options.presentation, tab = model.series.find(item => item.id === this.table) ?? model.series[0];
    return html`<details ?open=${!model.compared || this.pickerOnly}><summary>${this.w('modular.selected_laps')} · ${model.selected.length}</summary>${this.picker()}</details>${this.pickerOnly ? '' : html`
      <div class="controls"><button ?disabled=${!model.canCompare || model.readonly || model.comparing} @click=${() => this.send('compare')}>${this.w('modular.compare_selected_laps')}</button>${model.comparing ? html`<span role="status">${this.w('modular.fetching_selected_telemetry')}</span>` : ''}</div>
      ${model.compareError || model.compareDisconnected ? html`<p role="alert">${this.w('modular.the_comparison_could_not_be_loaded_for_this_session_check_the_replay_and_try')}</p>` : ''}
      ${model.compared ? html`${model.options.show_explanation !== false ? html`<details><summary>${this.w('modular.about_the_telemetry')}</summary><p class="muted">${this.w('modular.up_to_500_samples_per_lap_gaps_stay_open_brake_is_a_signal_not')}</p>
      ${channels.includes('delta_s') || model.options.axis === 'distance' ? html`<p class="muted">${this.w('modular.distance_is_estimated_from_continuous_speed_samples_the_first_sample_may_be_up_to')}: ${model.series[0] ? this.seriesName(model.series[0]) : '—'}.</p>` : ''}
      </details>` : ''}${!channels.length ? html`<p class="empty">${this.w('modular.choose_curves_in_the_editor')}</p>` : html`${presentation !== 'table' ? channels.map(channel => html`<h3>${this.title(channel)}</h3>${this.plot(channel)}`) : ''}
      ${presentation === 'chart' ? html`<button aria-expanded=${String(Boolean(this.table))} @click=${() => { this.table = this.table ? '' : model.series[0]?.id ?? ''; }}>${this.table ? this.w('modular.hide_data_table') : this.w('modular.show_data_table')}</button>` : ''}
      ${(presentation !== 'chart' || this.table) && tab ? html`<div class="controls"><label><span>${this.w('modular.table_for_lap')}</span><select aria-label=${this.w('modular.table_for_lap')} .value=${tab.id} @change=${event => { this.table = event.target.value; }}>${model.series.map(item => html`<option value=${item.id}>${this.seriesName(item)}</option>`)}</select></label></div>${this.dataTable(tab, channels)}` : ''}`}` : ''}`}`;
  }
}
if (!customElements.get('f1-telemetry-view')) customElements.define('f1-telemetry-view', F1TelemetryView);
