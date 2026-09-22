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
  seriesName(item) { return `${item.name} · ${this.w('lap', 'varv')} ${item.lap}`; }
  send(type, values = {}) { this.dispatchEvent(new CustomEvent(`f1-telemetry-${type}`, { bubbles: true, composed: true, detail: { module: this.module.id, sessionId: this.model.replay.sessionId, ...values } })); }
  select(selected) { this.send('selection', { selected }); }
  picker() {
    const model = this.model, disabled = Boolean(model.readonly || !model.replay.loaded || model.loading || model.error || model.disconnected || model.selectionChanged);
    const driver = model.drivers.find(driver => driver.id === this.draftDriver), lap = driver?.laps.includes(Number(this.draftLap)) ? this.draftLap : String(driver?.laps[0] ?? '');
    const candidate = driver && lap ? `${driver.id}:${lap}` : '';
    return html`<p><strong>${model.replay.selectedSession ?? this.w('Replay session', 'Replaysession')}</strong></p>
      ${!model.replay.loaded ? html`<p class="empty">${this.w('Load a replay to choose recorded laps. The replay status and player entities must be available and agree on the loaded session.', 'Ladda en replay för att välja registrerade varv. Entiteterna för replaystatus och spelare måste vara tillgängliga och visa samma laddade session.')}</p>` : ''}
      ${model.selectionChanged ? html`<p class="empty">${this.w('Saved laps belong to another replay. Clear them before choosing laps from this session.', 'Sparade varv hör till en annan replay. Rensa dem innan du väljer varv från den här sessionen.')}</p><button ?disabled=${model.readonly} @click=${() => this.select([])}>${this.w('Clear saved laps', 'Rensa sparade varv')}</button>` : ''}
      ${model.loading ? html`<p role="status">${this.w('Reading recorded lap list…', 'Läser listan över registrerade varv…')}</p>` : model.error || model.disconnected ? html`<p class="empty">${this.w('The lap list is unavailable. Check the replay and F1 Sensor version.', 'Varvlistan är inte tillgänglig. Kontrollera replay och F1 Sensor-version.')}</p>${!model.disconnected ? html`<button ?disabled=${model.readonly} @click=${() => this.send('retry')}>${this.w('Retry lap list', 'Hämta varvlistan igen')}</button>` : ''}` : ''}
      ${model.selected.length ? html`<ul class="selections">${model.selected.map(id => { const [driverId, lapId] = id.split(':'), driver = model.drivers.find(driver => driver.id === driverId); return html`<li><span>${driver?.name ?? driverId} · ${this.w('lap', 'varv')} ${lapId}${model.missing.includes(id) && !model.selectionChanged ? ` · ${this.w('not recorded', 'saknas i inspelningen')}` : ''}</span><button aria-label=${`${this.w('Remove lap', 'Ta bort varv')} ${id}`} ?disabled=${model.readonly || model.selectionChanged} @click=${() => this.select(model.selected.filter(item => item !== id))}>${this.w('Remove', 'Ta bort')}</button></li>`; })}</ul>` : ''}
      ${model.replay.loaded && !model.selectionChanged ? html`<div class="pickers"><label><span>${this.w('Driver to add', 'Förare att lägga till')}</span><select aria-label=${this.w('Driver to add', 'Förare att lägga till')} .value=${driver?.id ?? ''} ?disabled=${disabled || model.selected.length >= 4} @change=${event => { this.draftDriver = event.target.value; this.draftLap = ''; }}><option value="">${this.w('Choose driver', 'Välj förare')}</option>${model.drivers.map(driver => html`<option value=${driver.id}>${driver.name}</option>`)}</select></label>
      <label><span>${this.w('Recorded lap', 'Registrerat varv')}</span><select aria-label=${this.w('Recorded lap', 'Registrerat varv')} .value=${lap} ?disabled=${disabled || !driver || model.selected.length >= 4} @change=${event => { this.draftLap = event.target.value; }}>${(driver?.laps ?? []).map(lap => html`<option value=${String(lap)}>${lap}</option>`)}</select></label></div>
      <button ?disabled=${disabled || !candidate || model.selected.includes(candidate) || model.selected.length >= 4} @click=${() => this.select([...model.selected, candidate])}>${this.w('Add lap', 'Lägg till varv')}</button>` : ''}
      <p class="muted">${this.w('Choose up to four laps. The list confirms recorded lap boundaries; telemetry availability is checked when you compare.', 'Välj upp till fyra varv. Listan bekräftar registrerade varvgränser; telemetritäckningen kontrolleras när du jämför.')}</p>`;
  }
  plot(channel) {
    const model = this.model, axis = model.options.axis, colorsForMode = colors[this.settings?.mode] ?? colors.dark;
    const plotted = model.series.map(item => ({ ...item, segments: telemetrySegments(item.samples, channel, axis) }));
    const points = plotted.flatMap(item => item.segments.flat());
    if (!points.length) return html`<p class="empty">${this.w('No recorded values for this curve.', 'Registrerade värden saknas för den här kurvan.')}</p>`;
    const { low, high, ticks } = chartAxis(points.map(point => point.y), ['gear', 'drs'].includes(channel), ['throttle', 'brake'].includes(channel));
    const first = Math.min(...points.map(point => point.x)), last = Math.max(...points.map(point => point.x)), width = this.width, font = this.textSize;
    const left = Math.min(width * .35, Math.max(52, font * 4)), right = width - 22, height = Math.max(230, font * 13), bottom = height - font * 3.5, top = font;
    const x = value => last === first ? (left + right) / 2 : left + (value - first) / (last - first) * (right - left), y = value => bottom - (value - low) / (high - low) * (bottom - top);
    const xLabel = axis === 'distance' ? this.w('Estimated distance (m)', 'Uppskattat avstånd (m)') : this.w('Time from lap start (s)', 'Tid från varvstart (s)');
    return html`<svg class="plot" viewBox=${`0 0 ${width} ${height}`} role="img" aria-label=${`${this.title(channel)}. ${xLabel}. ${this.w('Recorded samples and gaps are available in the data table.', 'Registrerade mätvärden och luckor finns i datatabellen.')}`}><title>${this.title(channel)}</title>
      ${ticks.map(value => svg`<line class="grid" x1=${left} x2=${right} y1=${y(value)} y2=${y(value)}/><text class="axis" x=${left - 8} y=${y(value) + 4} text-anchor="end">${this.value(value)}</text>`)}
      ${[first, ...(width > 460 ? [(first + last) / 2] : []), last].map(value => svg`<text class="axis" x=${x(value)} y=${bottom + font * 1.4} text-anchor="middle">${this.value(Math.round(value * 10) / 10)}</text>`)}
      <text class="axis" x=${(left + right) / 2} y=${height - font * .5} text-anchor="middle">${xLabel}</text>
      ${plotted.map((item, index) => svg`<g data-series=${item.id} aria-hidden="true">${item.segments.map(segment => segment.length === 1 ? svg`<circle class="dot" cx=${x(segment[0].x)} cy=${y(segment[0].y)} r="3" style=${`fill:${colorsForMode[index]};stroke:${colorsForMode[index]}`}/>` : svg`<path class="curve" d=${segment.map((point, i) => i && ['gear', 'drs', 'brake'].includes(channel) ? `H${x(point.x)}V${y(point.y)}` : `${i ? 'L' : 'M'}${x(point.x)},${y(point.y)}`).join(' ')} style=${`stroke:${colorsForMode[index]};stroke-dasharray:${patterns[index]}`}/>` )}</g>`)}
      </svg><ul class="legend">${model.series.map((item, index) => html`<li><svg class="sample" viewBox="0 0 32 16" aria-hidden="true"><path class="curve" d="M1 8 L31 8" style=${`stroke:${colorsForMode[index]};stroke-dasharray:${patterns[index]}`}/></svg><span>${symbols[index]} ${this.seriesName(item)}</span></li>`)}</ul>`;
  }
  dataTable(item, channels) {
    return html`<div class="table-scroll" role="region" tabindex="0" aria-label=${this.seriesName(item)}><table><caption>${this.seriesName(item)} · ${this.w('bounded recorded samples', 'begränsat urval av registrerade mätvärden')}</caption><thead><tr><th scope="col">${this.w('Time (s)', 'Tid (s)')}</th><th scope="col">${this.w('Estimated distance (m)', 'Uppskattat avstånd (m)')}</th>${channels.map(channel => html`<th scope="col">${this.title(channel)}</th>`)}<th scope="col">${this.w('Recorded gap', 'Registrerad lucka')}</th></tr></thead><tbody>${item.samples.map((sample, index) => html`<tr><th scope="row">${this.value(sample.time_s)}</th><td>${this.value(sample.distance)}</td>${channels.map(channel => html`<td>${this.value(sample[channel])}</td>`)}<td>${sample.gap_before || index && sample.time_s - item.samples[index - 1].time_s > 2 ? this.w('Gap before sample', 'Lucka före mätvärdet') : '—'}</td></tr>`)}</tbody></table></div>`;
  }
  render() {
    if (!this.model || !this.module) return html``;
    const model = this.model, channels = model.fields.map(id => id.replace(/^telemetry_/, '')).filter(id => CHANNELS[id]);
    const presentation = model.options.presentation, tab = model.series.find(item => item.id === this.table) ?? model.series[0];
    return html`<details ?open=${!model.compared || this.pickerOnly}><summary>${this.w('Selected laps', 'Valda varv')} · ${model.selected.length}</summary>${this.picker()}</details>${this.pickerOnly ? '' : html`
      <div class="controls"><button ?disabled=${!model.canCompare || model.readonly || model.comparing} @click=${() => this.send('compare')}>${this.w('Compare selected laps', 'Jämför valda varv')}</button>${model.comparing ? html`<span role="status">${this.w('Fetching selected telemetry…', 'Hämtar vald telemetri…')}</span>` : ''}</div>
      ${model.compareError || model.compareDisconnected ? html`<p role="alert">${this.w('The comparison could not be loaded for this session. Check the replay and try Compare again.', 'Jämförelsen kunde inte hämtas för den här sessionen. Kontrollera replay och tryck på Jämför igen.')}</p>` : ''}
      ${model.compared ? html`${model.options.show_explanation !== false ? html`<details><summary>${this.w('About the telemetry', 'Om telemetrin')}</summary><p class="muted">${this.w('Up to 500 samples per lap. Gaps stay open. Brake is a signal, not measured brake pressure; DRS is the recorded channel code.', 'Upp till 500 mätvärden per varv. Luckor lämnas öppna. Broms är en signal, inte uppmätt bromstryck; DRS visar registrerad kanalkod.')}</p>
      ${channels.includes('delta_s') || model.options.axis === 'distance' ? html`<p class="muted">${this.w('Distance is estimated from continuous speed samples. The first sample may be up to 2 s after the lap boundary; gaps or late starts disable distance and delta. Negative delta means reaching that estimated distance earlier than reference', 'Avstånd uppskattas från sammanhängande hastighetsmätningar. Första mätvärdet kan ligga upp till 2 s efter varvgränsen; luckor eller sena starter stänger av avstånd och delta. Negativt delta betyder att uppskattat avstånd nås tidigare än referensen')}: ${model.series[0] ? this.seriesName(model.series[0]) : '—'}.</p>` : ''}
      </details>` : ''}${!channels.length ? html`<p class="empty">${this.w('Choose curves in the editor.', 'Välj kurvor i editorn.')}</p>` : html`${presentation !== 'table' ? channels.map(channel => html`<h3>${this.title(channel)}</h3>${this.plot(channel)}`) : ''}
      ${presentation === 'chart' ? html`<button aria-expanded=${String(Boolean(this.table))} @click=${() => { this.table = this.table ? '' : model.series[0]?.id ?? ''; }}>${this.table ? this.w('Hide data table', 'Dölj datatabell') : this.w('Show data table', 'Visa datatabell')}</button>` : ''}
      ${(presentation !== 'chart' || this.table) && tab ? html`<div class="controls"><label><span>${this.w('Table for lap', 'Tabell för varv')}</span><select aria-label=${this.w('Table for lap', 'Tabell för varv')} .value=${tab.id} @change=${event => { this.table = event.target.value; }}>${model.series.map(item => html`<option value=${item.id}>${this.seriesName(item)}</option>`)}</select></label></div>${this.dataTable(tab, channels)}` : ''}`}` : ''}`}`;
  }
}
if (!customElements.get('f1-telemetry-view')) customElements.define('f1-telemetry-view', F1TelemetryView);
