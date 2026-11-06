const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, svg, css, repeat }, { sharedStyles, words }, { seriesSegments, chartAxis }, { formatTime, formatDelta }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./view.js'), load('./season-data.js'), load('./semantics.js'),
]);
const colors = {
  dark: ['#75baff', '#ffb673', '#92d99f', '#d9a7ff', '#ff9db0', '#b9d867', '#7edcda', '#e2c5a0'],
  light: ['#145f9e', '#994100', '#226a33', '#77409b', '#a82b4a', '#576818', '#126d71', '#755531'],
};
const patterns = ['', '8 4', '3 4', '10 3 2 3', '14 6', '2 6', '10 6 3 6', '14 4 2 4 2 4'];
const symbols = ['●', '■', '▲', '◆'];
const eventKinds = ['pit', 'sc', 'vsc', 'red_flag'];
const eventSymbols = { pit: '●', sc: '■', vsc: '▲', red_flag: '◆' };
const eventLabels = { pit: 'P', sc: 'SC', vsc: 'VSC', red_flag: 'RF' };
export class F1SeriesChart extends LitElement {
  static properties = { model: { attribute: false }, module: { attribute: false }, settings: { attribute: false }, tableOpen: { state: true }, chartWidth: { state: true }, textSize: { state: true }, hiddenSeriesKeys: { state: true }, inspectedLap: { state: true } };
  static styles = [sharedStyles, css`
    .plot { width:100%; height:auto; display:block; overflow:visible; margin:4px 0 12px; }
    .axis { font-size:.8em; fill:var(--f1-muted); }
    .zero-line { stroke:var(--f1-text); stroke-width:1.5; stroke-dasharray:5 3; opacity:.8; }
    .trace-scope { display:flex; flex-wrap:wrap; gap:8px 20px; margin:8px 0; font-weight:650; }
    .trace-help,.point-reason { font-size:.82em; color:var(--f1-muted); }
    .point-reason { display:block; max-width:22ch; white-space:normal; }
    .trace-inspector { display:grid; gap:6px; margin:10px 0; }
    .trace-inspector input { width:100%; min-height:44px; accent-color:var(--primary-color,#75baff); }
    .trace-inspector input:focus-visible { outline:2px solid var(--f1-text); outline-offset:2px; }
    .trace-details { border:1px solid var(--f1-divider); border-radius:8px; padding:12px; margin:8px 0; }
    .trace-details ul { display:flex; flex-wrap:wrap; gap:8px 24px; list-style:none; padding:0; margin:8px 0 0; }
    .trace-details li { min-width:0; overflow-wrap:anywhere; }
    .event-track { width:100%; height:auto; display:block; margin:8px 0; }
    .event-point { fill:var(--f1-text); cursor:pointer; }
    .event-lane { stroke:var(--f1-divider); stroke-dasharray:2 3; }
    .trace-details .event-list,.event-cell ul { display:block; list-style:none; margin:8px 0 0; padding:0; }
    .event-list li,.event-cell li { margin:5px 0; }
    .event-cell { min-width:22ch; max-width:44ch; white-space:normal; overflow-wrap:anywhere; font-size:.85em; }
    .grid-line { stroke:var(--f1-divider); stroke-width:1; }
    .series-line { fill:none; stroke-width:2.5; stroke-linecap:round; stroke-linejoin:round; }
    .series-hit { fill:none; stroke:transparent; stroke-width:16; pointer-events:stroke; cursor:pointer; }
    .series-toggle .series-line,.series-toggle .marker { cursor:pointer; }
    .series-toggle:focus-visible { outline:none; }
    .series-toggle:focus-visible .series-line { stroke-width:4; filter:drop-shadow(0 0 3px var(--series-color)); }
    .chart-legend { list-style:none; padding:0; margin:12px 0; display:flex; flex-wrap:wrap; gap:10px 18px; }
    .chart-legend li { display:flex; min-width:0; }
    .legend-toggle { display:inline-grid; grid-template-columns:34px minmax(0,auto) auto; gap:6px; align-items:center; min-width:0; min-height:28px; padding:3px 7px; border:1px solid color-mix(in srgb,var(--series-color) 22%,var(--f1-divider)); border-radius:8px; background:color-mix(in srgb,var(--series-color) 5%,transparent); color:inherit; font:inherit; font-size:.85em; line-height:1.25; text-align:left; overflow-wrap:anywhere; cursor:pointer; appearance:none; }
    .legend-toggle:hover,.legend-toggle:focus-visible { border-color:color-mix(in srgb,var(--series-color) 55%,var(--f1-divider)); background:color-mix(in srgb,var(--series-color) 10%,transparent); outline:none; }
    .legend-toggle[data-hidden=true] { opacity:.45; background:transparent; }
    .legend-toggle[data-hidden=true] .legend-name { text-decoration:line-through; text-decoration-thickness:1px; }
    .legend-toggle[data-hidden=true] .series-line,.legend-toggle[data-hidden=true] .marker { opacity:.45; }
    .chart-layout { display:flex; flex-direction:column; min-width:0; }
    .chart-layout[data-legend=left] { flex-direction:row-reverse; gap:18px; }
    .chart-layout[data-legend=right] { flex-direction:row; gap:18px; }
    .chart-layout[data-legend=left] .chart-legend,.chart-layout[data-legend=right] .chart-legend { flex:0 1 240px; align-content:flex-start; flex-direction:column; flex-wrap:nowrap; }
    .chart-canvas { flex:1 1 auto; min-width:0; }
    .sample { width:34px; height:18px; flex:0 0 34px; }
    .filter-empty { min-height:180px; display:grid; place-items:center; margin:4px 0 12px; padding:24px; border:1px dashed var(--f1-divider); border-radius:10px; text-align:center; }
    .chart-tools { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
    .chart-tools p { font-size:.85em; }
    @media(max-width:600px) { .chart-layout[data-legend=left],.chart-layout[data-legend=right] { flex-direction:column; gap:0; } .chart-layout[data-legend=left] .chart-legend,.chart-layout[data-legend=right] .chart-legend { flex-basis:auto; flex-direction:row; flex-wrap:wrap; } }
    @media(forced-colors:active) { .series-line,.marker { stroke:CanvasText!important; } .marker { fill:Canvas!important; } .series-hit { stroke:transparent!important; } .legend-toggle { border-color:ButtonText; background:ButtonFace; color:ButtonText; } .legend-toggle:focus-visible { outline:2px solid Highlight; } .axis,.event-point { fill:CanvasText; } .event-lane { stroke:GrayText; } .grid-line { stroke:GrayText; } }
  `];
  constructor() { super(); this.tableOpen = false; this.chartWidth = 620; this.textSize = 16; this.hiddenSeriesKeys = new Set(); this.inspectedLap = null; }
  connectedCallback() {
    super.connectedCallback();
    this.observer = new ResizeObserver(entries => {
      const width = Math.round(entries[0]?.contentRect.width ?? 0);
      if (width > 0) this.chartWidth = Math.max(300, width);
      this.textSize = parseFloat(getComputedStyle(this).fontSize) || 16;
    });
    this.observer.observe(this);
  }
  disconnectedCallback() {
    super.disconnectedCallback(); this.observer?.disconnect(); this.inspectedLap = null;
    // A removed Race Trace must not retain protected values in the reused node.
    if (this.isTrace) { this.model = null; this.tableOpen = false; }
  }
  willUpdate() {
    if (this.lastTraceContext !== this.model?.traceContext) {
      this.inspectedLap = null; this.lastTraceContext = this.model?.traceContext;
    }
    if (this.inspectedLap !== null && !this.model?.rounds?.some(round => round.id === this.inspectedLap)) this.inspectedLap = null;
  }
  get isTrace() { return this.model?.metric === 'cumulative_lap_delta'; }
  pointValue(point) { return this.isTrace ? Number.isSafeInteger(point?.delta_ms) ? point.delta_ms / 1000 : null : point?.value; }
  pointText(point) { return this.value(this.pointValue(point)); }
  pointReason(point) { return point?.reason ? this.w(`modular.race_trace_${point.reason}`) : ''; }
  dash(index) { return patterns[(this.isTrace ? index : Math.floor(index / 4)) % patterns.length]; }
  inspectPointer(event, rounds, gutter, right) {
    if (!this.isTrace || !rounds.length) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const position = (event.clientX - bounds.left) * this.chartWidth / bounds.width;
    const index = Math.max(0, Math.min(rounds.length - 1, Math.round((position - gutter) / (right - gutter) * (rounds.length - 1))));
    this.inspectedLap = rounds[index].id;
  }
  markerData(series) {
    if (!this.isTrace || !this.module.options.event_markers?.length) return null;
    const snapshot = this.model.markers, ready = snapshot?.status === 'ready', byLap = new Map();
    const events = ready ? (snapshot.events ?? []).map(event => ({ ...event, text: this.eventText(event, series) })) : [];
    for (const event of events) {
      if (!byLap.has(event.lap)) byLap.set(event.lap, []);
      byLap.get(event.lap).push(event);
    }
    const message = ready ? events.length ? '' : 'markers_none' : snapshot?.status === 'pending' ? 'markers_pending' : 'markers_unavailable';
    return { byLap, events, message, kinds: eventKinds.filter(kind => this.module.options.event_markers.includes(kind)) };
  }
  eventText(event, series) {
    const driver = series.find(item => item.id === event.driver)?.name ?? event.driver;
    const replacements = { event: this.w(`modular.race_trace_marker_${event.kind}`), driver, lap: event.lap, phase: this.w(`modular.race_trace_marker_phase_${event.phase}`) };
    const text = this.w(event.anchor_type === 'driver_lap' ? 'modular.race_trace_marker_driver_detail' : 'modular.race_trace_marker_reference_detail', replacements);
    return event.description ? `${text} · ${event.description}` : text;
  }
  eventList(events = []) {
    return events.length ? html`<ul class="event-list">${repeat(events, event => event.id, event => html`<li>${eventSymbols[event.kind]} ${event.text}</li>`)}</ul>` : '';
  }
  eventTrack(rounds, markers) {
    if (!markers?.events.length) return '';
    const width = this.chartWidth, gutter = Math.max(48, this.textSize * 6), right = width - 24, rowHeight = this.textSize * 1.6;
    const x = index => rounds.length > 1 ? gutter + index * (right - gutter) / (rounds.length - 1) : (gutter + right) / 2;
    return html`<svg class="event-track" viewBox=${`0 0 ${width} ${rowHeight * markers.kinds.length}`} role="img" aria-label=${this.w('modular.race_trace_event_markers')}>
      <title>${this.w('modular.race_trace_event_markers')}</title>
      ${markers.kinds.map((kind, lane) => svg`<text class="axis" x=${gutter - 10} y=${rowHeight * (lane + .7)} text-anchor="end">${eventSymbols[kind]} ${eventLabels[kind]}</text><line class="event-lane" x1=${gutter} x2=${right} y1=${rowHeight * (lane + .5)} y2=${rowHeight * (lane + .5)}/>
        ${rounds.map((round, index) => {
          const events = markers.byLap.get(round.id)?.filter(event => event.kind === kind);
          return events?.length ? svg`<text class="event-point" data-kind=${kind} data-lap=${round.id} x=${x(index)} y=${rowHeight * (lane + .7)} text-anchor="middle" @click=${() => { this.inspectedLap = round.id; }}><title>${events.map(event => event.text).join('. ')}</title>${eventSymbols[kind]}</text>` : '';
        })}`)}
    </svg>`;
  }
  traceDetails(series, rounds, markers) {
    const index = rounds.findIndex(round => round.id === this.inspectedLap);
    if (index < 0) return '';
    return html`<div class="trace-details" id="trace-values" role="tooltip"><strong>${this.w('modular.race_trace_lap_details', { lap: this.inspectedLap })}</strong><ul>${series.map((item, seriesIndex) => html`<li>${symbols[seriesIndex % 4]} ${item.name}: <strong>${this.pointText(item.values[index])}</strong>${item.values[index]?.reason ? html`<span class="point-reason">${this.pointReason(item.values[index])}</span>` : ''}</li>`)}</ul>${this.eventList(markers?.byLap.get(this.inspectedLap))}</div>`;
  }
  traceInspector(series, rounds, markers) {
    const index = Math.max(0, rounds.findIndex(round => round.id === this.inspectedLap));
    const description = [this.w('modular.race_trace_lap_details', { lap: rounds[index].id }), ...series.map(item => `${item.name}: ${this.pointText(item.values[index])}${item.values[index]?.reason ? `, ${this.pointReason(item.values[index])}` : ''}`), ...(markers?.byLap.get(rounds[index].id) ?? []).map(event => event.text)].join('. ');
    return html`<label class="trace-inspector"><span>${this.w('modular.race_trace_inspect_lap')}</span><input type="range" min="0" max=${rounds.length - 1} step="1" .value=${String(index)} aria-valuetext=${description} aria-describedby="trace-help"
      @focus=${() => { if (this.inspectedLap === null) this.inspectedLap = rounds[index].id; }}
      @input=${event => { this.inspectedLap = rounds[Number(event.target.value)].id; }}
      @keydown=${event => { if (event.key === 'Escape') { this.inspectedLap = null; event.stopPropagation(); } }}></label><p class="trace-help" id="trace-help">${this.w('modular.race_trace_keyboard_help')}</p>${this.traceDetails(series, rounds, markers)}`;
  }
  w(source, replacements = {}) { return words(this.settings?.language, source, replacements); }
  traceValue(value) {
    const language = this.settings?.language ?? 'en';
    if (this.traceNumberLanguage !== language) {
      this.traceNumberLanguage = language;
      this.traceNumberFormat = new Intl.NumberFormat(language, { minimumFractionDigits: 3, maximumFractionDigits: 3, signDisplay: 'exceptZero' });
    }
    return `${this.traceNumberFormat.format(value)} s`;
  }
  value(value) { return value === null || value === undefined ? '—' : this.isTrace ? this.traceValue(value) : this.model?.metric === 'lap_time' ? formatTime(value) : this.model?.metric === 'lap_change' ? `${formatDelta(value)} s` : new Intl.NumberFormat(this.settings?.language ?? 'en', { maximumFractionDigits: 2 }).format(value); }
  get metric() { return this.isTrace ? this.w('modular.race_trace_title') : this.model?.metric === 'lap_position' ? this.w('modular.position_at_lap_completion') : this.model?.metric === 'lap_time' ? this.w('modular.lap_time') : this.model?.metric === 'lap_change' ? this.w('modular.change_from_previous_lap') : this.model?.metric === 'wins_per_round' ? this.w('modular.wins_per_round') : this.model?.metric === 'points_per_round' ? this.w('modular.points_per_round') : this.w('modular.total_points'); }
  seriesKey(item) { return `${this.module?.type ?? 'chart'}:${this.model?.teams ? 'teams' : 'drivers'}:${item?.id ?? ''}`; }
  isSeriesHidden(item) { return this.hiddenSeriesKeys.has(this.seriesKey(item)); }
  toggleSeries(item, event) {
    event?.stopPropagation?.();
    const key = this.seriesKey(item), hidden = new Set(this.hiddenSeriesKeys);
    if (hidden.has(key)) hidden.delete(key); else hidden.add(key);
    this.hiddenSeriesKeys = hidden;
  }
  toggleSeriesFromKey(item, event) {
    if (!['Enter', ' ', 'Spacebar'].includes(event?.key)) return;
    event.preventDefault(); this.toggleSeries(item, event);
  }
  seriesIndex(item) { const index = this.model?.series?.findIndex(candidate => candidate.id === item.id); return index >= 0 ? index : 0; }
  seriesColor(item, index = this.seriesIndex(item)) {
    const palette = colors[this.settings?.mode] ?? colors.dark;
    return this.module?.type === 'progression' && this.settings?.appearance?.team_colors !== false && /^#[0-9a-f]{6}$/i.test(item?.color ?? '') ? item.color : palette[index % palette.length];
  }
  seriesLabel(item, hidden = this.isSeriesHidden(item)) { return `${item.name}: ${hidden ? this.w('modular.hidden_show_series') : this.w('modular.visible_hide_series')}`; }
  marker(index, x, y, color) {
    const style = `fill:${color};stroke:var(--f1-surface);stroke-width:1.2`;
    if (index % 4 === 1) return svg`<rect class="marker" x=${x - 3.5} y=${y - 3.5} width="7" height="7" style=${style}/>`;
    if (index % 4 === 2) return svg`<path class="marker" d=${`M${x},${y - 4.5}L${x + 4.5},${y + 3.5}L${x - 4.5},${y + 3.5}Z`} style=${style}/>`;
    if (index % 4 === 3) return svg`<path class="marker" d=${`M${x},${y - 4.5}L${x + 4.5},${y}L${x},${y + 4.5}L${x - 4.5},${y}Z`} style=${style}/>`;
    return svg`<circle class="marker" cx=${x} cy=${y} r="3.5" style=${style}/>`;
  }
  plot(series, rounds) {
    const values = series.flatMap(item => item.values.map(value => value.value).filter(value => value !== null));
    const positional = this.model.metric === 'lap_position';
    const { low, high, ticks } = positional ? { low: 1, high: Math.max(2, ...values), ticks: Array.from({ length: Math.max(2, ...values) }, (_, index) => index + 1).filter((value, index, all) => value === 1 || value === all.length || value % Math.ceil(all.length / 6) === 0) } : chartAxis(values, this.model.metric === 'wins_per_round', this.model.metric !== 'lap_time'), range = high - low;
    const width = this.chartWidth, gutter = Math.max(48, this.textSize * (this.model.axisKind === 'lap' && !positional ? 6 : 3)), right = width - 24;
    const configuredHeight = Number.isInteger(this.module.options.chart_height) ? this.module.options.chart_height : this.module.type === 'archive' ? 420 : 320;
    const height = Math.max(configuredHeight, this.textSize * 14), labels = this.module.options.show_round_labels !== false, bottom = height - this.textSize * (labels ? 2.3 : 1.2);
    const x = index => rounds.length > 1 ? gutter + index * (right - gutter) / (rounds.length - 1) : (gutter + right) / 2;
    const y = value => positional ? this.textSize * 2 + ((value - low) / range) * (bottom - this.textSize * 2) : bottom - ((value - low) / range) * (bottom - this.textSize * 2);
    const interactive = this.module.type === 'progression';
    return html`<svg class="plot" viewBox=${`0 0 ${width} ${height}`} role=${interactive ? 'group' : 'img'} aria-label=${`${this.metric}. ${this.w('modular.values_and_missing_data_are_available_in_the_data_table')}`}
      @pointermove=${event => this.inspectPointer(event, rounds, gutter, right)} @pointerleave=${() => { if (this.isTrace && this.shadowRoot.activeElement?.type !== 'range') this.inspectedLap = null; }}>
      <title>${this.metric}</title>
      ${ticks.map(tick => svg`<line class="grid-line" x1=${gutter} x2=${right} y1=${y(tick)} y2=${y(tick)}/><text class="axis" x=${gutter - 8} y=${y(tick) + 4} text-anchor="end">${this.value(tick)}</text>`)}
      ${this.isTrace ? svg`<line class="zero-line" x1=${gutter} x2=${right} y1=${y(0)} y2=${y(0)} aria-hidden="true"/>` : ''}
      ${labels ? rounds.map((round, index) => index === 0 || index === rounds.length - 1 || index % Math.max(1, Math.ceil(rounds.length / Math.max(2, Math.floor((right - gutter) / (this.textSize * 3))))) === 0 ? svg`<text class="axis round-label" x=${x(index)} y=${height - this.textSize * .6} text-anchor="middle">${this.model.axisKind === 'lap' ? 'L' : 'R'}${round.id}</text>` : '') : ''}
      ${repeat(series, item => item.id, item => {
        const index = this.seriesIndex(item), color = this.seriesColor(item, index), style = `stroke:${color};stroke-dasharray:${this.dash(index)}`;
        const paths = seriesSegments(item.values).map(segment => {
          const path = segment.map((point, i) => `${i ? 'L' : 'M'}${x(point.index)},${y(point.value)}`).join(' ');
          return svg`<path class="series-line" d=${path} style=${style}/>${interactive ? svg`<path class="series-hit" d=${path}/>` : ''}`;
        });
        const markers = item.values.map((point, i) => {
          const isolated = item.values[i - 1]?.value == null && item.values[i + 1]?.value == null;
          if (point.value === null || this.module.options.show_points === false && !(this.isTrace && isolated)) return '';
          if (!isolated && i % Math.max(1, Math.ceil(item.values.length / 64)) !== 0 && i !== item.values.length - 1 && item.values[i - 1]?.value != null && item.values[i + 1]?.value != null) return '';
          return this.marker(index, x(i), y(point.value), color);
        });
        return interactive ? svg`<g class="series-toggle" data-series=${item.id} style=${`--series-color:${color}`} role="button" tabindex="0" aria-pressed="true" aria-label=${this.seriesLabel(item, false)} @click=${event => this.toggleSeries(item, event)} @keydown=${event => this.toggleSeriesFromKey(item, event)}><title>${this.seriesLabel(item, false)}</title>${paths}${markers}</g>`
          : svg`<g data-series=${item.id} aria-hidden="true">${paths}${markers}</g>`;
      })}
    </svg>`;
  }
  table(series, rounds, markers) {
    return html`<div class="table-scroll" tabindex="0" role="region" aria-label=${this.model.axisKind === 'lap' ? this.w('modular.lap_data_scroll_horizontally_for_more_drivers') : this.w('modular.progression_data_scroll_horizontally_for_more_competitors')}><table><caption class="sr">${this.metric}</caption>
      <thead><tr><th scope="col">${this.model.axisKind === 'lap' ? this.w('modular.lap') : this.w('modular.round')}</th>${series.map(item => html`<th scope="col">${item.name}</th>`)}${markers ? html`<th scope="col">${this.w('modular.race_trace_event_markers')}</th>` : ''}</tr></thead>
      <tbody>${repeat(rounds, round => round.id, (round, index) => html`<tr><th scope="row">${round.id}${round.race_name ? ` · ${round.race_name}` : ''}</th>${series.map(item => html`<td>${this.pointText(item.values[index])}${this.isTrace && item.values[index]?.reason ? html`<span class="point-reason">${this.pointReason(item.values[index])}</span>` : ''}</td>`)}${markers ? html`<td class="event-cell">${markers.byLap.has(round.id) ? this.eventList(markers.byLap.get(round.id)) : '—'}</td>` : ''}</tr>`)}</tbody>
    </table></div>`;
  }
  render() {
    if (!this.model || !this.module || !this.settings) return html``;
    const rounds = this.model.rounds ?? [], presentation = this.module.options.presentation;
    // Milliseconds are the common source for geometry, table and inspected values.
    const series = this.isTrace ? (this.model.series ?? []).map(item => ({ ...item, values: item.values.map(point => ({ ...point, value: this.pointValue(point) })) })) : this.model.series ?? [];
    if (!series.length || !rounds.length || !series.some(item => item.values.some(point => point.value !== null))) return html`<p class="empty">${this.w('modular.no_chart_data_matches_this_selection')}</p>`;
    const showTable = presentation !== 'chart' || this.tableOpen;
    const showLegend = presentation !== 'table' && this.module.options.show_legend !== false;
    const filterable = this.module.type === 'progression' && showLegend;
    const activeSeries = filterable ? series.filter(item => !this.isSeriesHidden(item)) : series;
    const legendPosition = ['left', 'right'].includes(this.module.options.legend_position) ? this.module.options.legend_position : 'bottom';
    const legend = showLegend ? html`<ul class="chart-legend">${series.map((item, index) => {
      const hidden = filterable && this.isSeriesHidden(item), color = this.seriesColor(item, index);
      return html`<li>${filterable ? html`<button type="button" class="legend-toggle" data-hidden=${String(hidden)} aria-pressed=${String(!hidden)} aria-label=${this.seriesLabel(item, hidden)} title=${this.seriesLabel(item, hidden)} style=${`--series-color:${color}`} @click=${event => this.toggleSeries(item, event)}><svg class="sample" aria-hidden="true" viewBox="0 0 34 18"><path class="series-line" d="M1,9L33,9" style=${`stroke:${color};stroke-dasharray:${this.dash(index)}`}/>${this.marker(index, 17, 9, color)}</svg><span class="legend-name">${symbols[index % 4]} ${item.name}</span>${this.module.options.show_legend_points !== false ? html`<span class="muted">${this.value(item.total)} ${this.w('modular.pts')}</span>` : ''}</button>` : html`<svg class="sample" aria-hidden="true" viewBox="0 0 34 18"><path class="series-line" d="M1,9L33,9" style=${`stroke:${color};stroke-dasharray:${this.dash(index)}`}/>${this.marker(index, 17, 9, color)}</svg><span>${symbols[index % 4]} ${item.name}</span>`}</li>`;
    })}</ul>` : '';
    const markers = this.markerData(series);
    const reference = series.find(item => item.id === this.model.referenceDriver);
    return html`${this.isTrace ? html`<div class="trace-scope"><span>${this.w('modular.race_trace_reference', { driver: reference ? `${reference.name} · ${reference.id}` : this.model.referenceDriver })}</span><span>${this.w('modular.race_trace_anchor', { lap: this.model.anchorLap })}</span></div><p class="trace-help">${this.w('modular.race_trace_notice')}</p><p class="trace-help">${this.w('modular.race_trace_signs')}</p>` : ''}<div class="chart-tools"><strong>${this.metric}</strong><p class="muted">${this.w(this.isTrace ? 'modular.race_trace_gaps' : 'modular.gaps_mean_data_is_missing')}</p></div>
      ${presentation !== 'table' ? html`<div class="chart-layout" data-legend=${showLegend ? legendPosition : 'none'}><div class="chart-canvas">${activeSeries.length ? this.plot(activeSeries, rounds) : html`<p class="filter-empty muted" role="status">${this.w('modular.all_series_are_hidden_select_a_driver_or_team_in_the_legend_to_show')}</p>`}</div>${legend}</div>` : ''}
      ${markers ? html`<p class="trace-help">${this.w('modular.race_trace_markers_help')}</p>${markers.message ? html`<p class="trace-help event-status" role="status">${this.w(`modular.race_trace_${markers.message}`)}</p>` : ''}${presentation !== 'table' ? this.eventTrack(rounds, markers) : ''}` : ''}
      ${this.isTrace && presentation !== 'table' ? this.traceInspector(series, rounds, markers) : ''}
      ${presentation === 'chart' ? html`<button aria-expanded=${String(showTable)} aria-controls="progression-data" @click=${() => { this.tableOpen = !this.tableOpen; }}>${showTable ? this.w('modular.hide_data_table') : this.w('modular.show_data_table')}</button>` : ''}
      <div id="progression-data" ?hidden=${!showTable}>${showTable ? this.table(activeSeries, rounds, markers) : ''}</div>
    `;
  }
}
if (!customElements.get('f1-series-chart')) customElements.define('f1-series-chart', F1SeriesChart);
