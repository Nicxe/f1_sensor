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
export class F1SeriesChart extends LitElement {
  static properties = { model: { attribute: false }, module: { attribute: false }, settings: { attribute: false }, tableOpen: { state: true }, chartWidth: { state: true }, textSize: { state: true } };
  static styles = [sharedStyles, css`
    .plot { width:100%; height:auto; display:block; overflow:visible; margin:4px 0 12px; }
    .axis { font-size:.8em; fill:var(--f1-muted); }
    .grid-line { stroke:var(--f1-divider); stroke-width:1; }
    .series-line { fill:none; stroke-width:2.5; stroke-linecap:round; stroke-linejoin:round; }
    .chart-legend { list-style:none; padding:0; margin:12px 0; display:flex; flex-wrap:wrap; gap:10px 18px; }
    .chart-legend li { display:flex; gap:6px; align-items:center; min-width:0; overflow-wrap:anywhere; font-size:.85em; }
    .chart-layout { display:flex; flex-direction:column; min-width:0; }
    .chart-layout[data-legend=left] { flex-direction:row-reverse; gap:18px; }
    .chart-layout[data-legend=right] { flex-direction:row; gap:18px; }
    .chart-layout[data-legend=left] .chart-legend,.chart-layout[data-legend=right] .chart-legend { flex:0 1 240px; align-content:flex-start; flex-direction:column; flex-wrap:nowrap; }
    .chart-canvas { flex:1 1 auto; min-width:0; }
    .sample { width:34px; height:18px; flex:0 0 34px; }
    .chart-tools { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
    .chart-tools p { font-size:.85em; }
    @media(max-width:600px) { .chart-layout[data-legend=left],.chart-layout[data-legend=right] { flex-direction:column; gap:0; } .chart-layout[data-legend=left] .chart-legend,.chart-layout[data-legend=right] .chart-legend { flex-basis:auto; flex-direction:row; flex-wrap:wrap; } }
    @media(forced-colors:active) { .series-line,.marker { stroke:CanvasText!important; } .marker { fill:Canvas!important; } .axis { fill:CanvasText; } .grid-line { stroke:GrayText; } }
  `];
  constructor() { super(); this.tableOpen = false; this.chartWidth = 620; this.textSize = 16; }
  connectedCallback() {
    super.connectedCallback();
    this.observer = new ResizeObserver(entries => {
      const width = Math.round(entries[0]?.contentRect.width ?? 0);
      if (width > 0) this.chartWidth = Math.max(300, width);
      this.textSize = parseFloat(getComputedStyle(this).fontSize) || 16;
    });
    this.observer.observe(this);
  }
  disconnectedCallback() { super.disconnectedCallback(); this.observer?.disconnect(); }
  w(en, sv) { return words(this.settings?.language, en, sv); }
  value(value) { return value === null || value === undefined ? '—' : this.model?.metric === 'lap_time' ? formatTime(value) : this.model?.metric === 'lap_change' ? `${formatDelta(value)} s` : new Intl.NumberFormat(this.settings?.language ?? 'en', { maximumFractionDigits: 2 }).format(value); }
  get metric() { return this.model?.metric === 'lap_position' ? this.w('Position at lap completion', 'Placering vid avslutat varv') : this.model?.metric === 'lap_time' ? this.w('Lap time', 'Varvtid') : this.model?.metric === 'lap_change' ? this.w('Change from previous lap', 'Skillnad mot föregående varv') : this.model?.metric === 'wins_per_round' ? this.w('Wins per round', 'Vinster per deltävling') : this.model?.metric === 'points_per_round' ? this.w('Points per round', 'Poäng per deltävling') : this.w('Total points', 'Totala poäng'); }
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
    const palette = colors[this.settings.mode] ?? colors.dark;
    return html`<svg class="plot" viewBox=${`0 0 ${width} ${height}`} role="img" aria-label=${`${this.metric}. ${this.w('Values and missing data are available in the data table.', 'Värden och saknade uppgifter finns i datatabellen.')}`}>
      <title>${this.metric}</title>
      ${ticks.map(tick => svg`<line class="grid-line" x1=${gutter} x2=${right} y1=${y(tick)} y2=${y(tick)}/><text class="axis" x=${gutter - 8} y=${y(tick) + 4} text-anchor="end">${this.value(tick)}</text>`)}
      ${labels ? rounds.map((round, index) => index === 0 || index === rounds.length - 1 || index % Math.max(1, Math.ceil(rounds.length / Math.max(2, Math.floor((right - gutter) / (this.textSize * 3))))) === 0 ? svg`<text class="axis round-label" x=${x(index)} y=${height - this.textSize * .6} text-anchor="middle">${this.model.axisKind === 'lap' ? 'L' : 'R'}${round.id}</text>` : '') : ''}
      ${repeat(series, item => item.id, (item, index) => svg`<g data-series=${item.id} aria-hidden="true">
        ${seriesSegments(item.values).map(segment => svg`<path class="series-line" d=${segment.map((point, i) => `${i ? 'L' : 'M'}${x(point.index)},${y(point.value)}`).join(' ')} style=${`stroke:${palette[index % palette.length]};stroke-dasharray:${patterns[Math.floor(index / 4) % patterns.length]}`}/>`)}
        ${this.module.options.show_points === false ? '' : item.values.map((point, i) => point.value === null || i % Math.max(1, Math.ceil(item.values.length / 64)) !== 0 && i !== item.values.length - 1 && item.values[i - 1]?.value != null && item.values[i + 1]?.value != null ? '' : this.marker(index, x(i), y(point.value), palette[index % palette.length]))}
      </g>`)}
    </svg>`;
  }
  table(series, rounds) {
    return html`<div class="table-scroll" tabindex="0" role="region" aria-label=${this.model.axisKind === 'lap' ? this.w('Lap data, scroll horizontally for more drivers', 'Varvdata, rulla i sidled för fler förare') : this.w('Progression data, scroll horizontally for more competitors', 'Utvecklingsdata, rulla i sidled för fler deltagare')}><table><caption class="sr">${this.metric}</caption>
      <thead><tr><th scope="col">${this.model.axisKind === 'lap' ? this.w('Lap', 'Varv') : this.w('Round', 'Deltävling')}</th>${series.map(item => html`<th scope="col">${item.name}</th>`)}</tr></thead>
      <tbody>${repeat(rounds, round => round.id, (round, index) => html`<tr><th scope="row">${round.id}${round.race_name ? ` · ${round.race_name}` : ''}</th>${series.map(item => html`<td>${this.value(item.values[index]?.value)}</td>`)}</tr>`)}</tbody>
    </table></div>`;
  }
  render() {
    if (!this.model || !this.module || !this.settings) return html``;
    const { series = [], rounds = [] } = this.model, presentation = this.module.options.presentation;
    if (!series.length || !rounds.length || !series.some(item => item.values.some(point => point.value !== null))) return html`<p class="empty">${this.w('No chart data matches this selection.', 'Ingen diagramdata matchar urvalet.')}</p>`;
    const showTable = presentation !== 'chart' || this.tableOpen, palette = colors[this.settings.mode] ?? colors.dark;
    const showLegend = presentation !== 'table' && this.module.options.show_legend !== false;
    const legendPosition = ['left', 'right'].includes(this.module.options.legend_position) ? this.module.options.legend_position : 'bottom';
    const legend = showLegend ? html`<ul class="chart-legend">${series.map((item, index) => html`<li><svg class="sample" aria-hidden="true" viewBox="0 0 34 18"><path class="series-line" d="M1,9L33,9" style=${`stroke:${palette[index % palette.length]};stroke-dasharray:${patterns[Math.floor(index / 4) % patterns.length]}`}/>${this.marker(index, 17, 9, palette[index % palette.length])}</svg><span>${symbols[index % 4]} ${item.name}</span>${this.module.type === 'progression' && this.module.options.show_legend_points !== false ? html`<span class="muted">${this.value(item.total)} ${this.w('pts', 'p')}</span>` : ''}</li>`)}</ul>` : '';
    return html`<div class="chart-tools"><strong>${this.metric}</strong><p class="muted">${this.w('Gaps mean data is missing.', 'Glapp betyder att data saknas.')}</p></div>
      ${presentation !== 'table' ? html`<div class="chart-layout" data-legend=${showLegend ? legendPosition : 'none'}><div class="chart-canvas">${this.plot(series, rounds)}</div>${legend}</div>` : ''}
      ${presentation === 'chart' ? html`<button aria-expanded=${String(showTable)} aria-controls="progression-data" @click=${() => { this.tableOpen = !this.tableOpen; }}>${showTable ? this.w('Hide data table', 'Dölj datatabell') : this.w('Show data table', 'Visa datatabell')}</button>` : ''}
      <div id="progression-data" ?hidden=${!showTable}>${showTable ? this.table(series, rounds) : ''}</div>
    `;
  }
}
if (!customElements.get('f1-series-chart')) customElements.define('f1-series-chart', F1SeriesChart);
