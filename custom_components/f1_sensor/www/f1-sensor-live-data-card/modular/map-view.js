const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, svg, css, repeat }, { sharedStyles, words, dateTime }] = await Promise.all([load('../f1-lit-3.3.2.js'), load('./view.js')]);
class F1TrackMapView extends LitElement {
  static properties = { model: { attribute: false }, module: { attribute: false }, settings: { attribute: false }, width: { state: true }, selected: { state: true }, listOpen: { state: true } };
  static styles = [sharedStyles, css`
    .map-frame { border:1px solid var(--f1-border); border-radius:10px; background:var(--f1-panel); }
    .map-shell { display:grid; gap:12px; }
    .map-shell.compact { gap:8px; }
    .map-shell.full { gap:16px; }
    .map-meta,.map-footer { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px 14px; color:var(--f1-muted); }
    .map-meta strong { color:var(--f1-text); }
    .map-badges { display:flex; flex-wrap:wrap; gap:6px; }
    .map-status { display:inline-flex; align-items:center; min-height:28px; border:1px solid var(--f1-border); border-radius:999px; padding:2px 9px; color:var(--f1-text); }
    .map-footer { border-top:1px solid var(--f1-divider); padding-top:10px; font-size:.82em; }
    svg { display:block; width:100%; height:auto; }
    .track { fill:none; stroke:var(--f1-text); stroke-width:1; stroke-linejoin:round; stroke-linecap:round; }
    .track-status-accent { fill:none; stroke:var(--track-status-color); stroke-width:3; opacity:.32; stroke-linejoin:round; stroke-linecap:round; }
    .track.status-full { stroke:var(--track-status-color); stroke-width:1.4; }
    .marker circle { fill:var(--f1-surface); stroke:var(--f1-text); stroke-width:.5; }
    .marker .team { fill:var(--team-accent); stroke:none; }
    .map-list summary { min-height:44px; padding:10px 0; cursor:pointer; }
    .map-list summary:focus-visible { outline:3px solid var(--f1-focus); outline-offset:3px; }
    .marker text { fill:var(--f1-text); paint-order:stroke; stroke:var(--f1-panel); stroke-width:.55; stroke-linejoin:round; font-weight:700; }
    .marker.selected circle { stroke-width:1.3; }
    .marker.stale circle { stroke-dasharray:1 .8; }
    .annotation-line { stroke:var(--f1-text); stroke-width:1.5; stroke-dasharray:1.4 .8; }
    .annotation-line-back { stroke:var(--f1-panel); stroke-width:3; }
    .annotation-tag { fill:var(--f1-panel); stroke:var(--f1-text); stroke-width:.5; }
    .annotation-tag-text { fill:var(--f1-text); font-weight:800; letter-spacing:.03em; }
    .annotation-point { fill:var(--f1-panel); stroke:var(--f1-text); stroke-width:.75; }
    .annotation-leader { stroke:var(--f1-muted); stroke-width:.4; }
    .annotation-number { fill:var(--f1-text); font-weight:800; paint-order:stroke; stroke:var(--f1-panel); stroke-width:.65; font-variant-numeric:tabular-nums; }
    .annotation-feature-point { fill:var(--f1-panel); stroke:var(--f1-text); stroke-width:.8; }
    .annotation-feature-text { fill:var(--f1-text); font-weight:700; paint-order:stroke; stroke:var(--f1-panel); stroke-width:.7; }
    .annotation-summary { color:var(--f1-muted); font-size:.83em; }
    .annotation-summary details { margin-top:4px; }
    .annotation-summary summary { min-height:44px; display:flex; align-items:center; cursor:pointer; }
    .annotation-summary summary:focus-visible { outline:3px solid var(--f1-focus); outline-offset:3px; }
    .annotation-summary ul { display:flex; flex-wrap:wrap; gap:4px 14px; margin:0; padding:0 0 0 20px; }
    .annotation-unavailable { margin:0; color:var(--f1-muted); font-size:.82em; }
    .driver-list { display:grid; gap:6px; list-style:none; margin:14px 0 0; padding:0; }
    .driver-list button { width:100%; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:6px 12px; text-align:left; }
    .driver-list small { display:block; font-size:.8em; }
    @media(forced-colors:active) { .track,.marker circle,.annotation-line,.annotation-point,.annotation-feature-point,.annotation-leader,.annotation-tag { stroke:CanvasText!important; } .marker text,.annotation-number,.annotation-feature-text,.annotation-tag-text { fill:CanvasText!important; stroke:Canvas!important; } .marker .team { display:none; } }
  `];
  constructor() {
    super(); this.width = 400; this.selected = ''; this.listOpen = false;
    this.motions = new Map(); this.motionFrame = 0;
  }
  connectedCallback() {
    super.connectedCallback(); this.observer = new ResizeObserver(entries => { this.width = Math.max(200, entries[0].contentRect.width); }); this.observer.observe(this);
  }
  disconnectedCallback() {
    super.disconnectedCallback(); this.observer?.disconnect();
    if (this.motionFrame) cancelAnimationFrame(this.motionFrame);
    this.motionFrame = 0;
  }
  willUpdate(changed) {
    const sessionChanged = this.model?.sessionKey !== this.sessionKey;
    if (sessionChanged) { this.sessionKey = this.model?.sessionKey; this.selected = ''; }
    if (changed.has('model') || changed.has('settings')) this.syncMotion(sessionChanged, changed.has('model'));
    if (changed.has('module')) {
      const showList = this.module?.fields.includes('map_drivers');
      if (showList !== this.showList) { this.listOpen = Boolean(showList); this.showList = showList; }
    }
    if (this.selected && !this.model?.rows.some(row => row.id === this.selected)) this.selected = '';
  }
  updated() {
    const map = this.shadowRoot?.querySelector('.map-frame svg');
    if (!map) return;
    const lines = map.querySelectorAll('.annotation-line-group');
    const corners = map.querySelectorAll('.annotation-corner-group');
    const features = map.querySelectorAll('.annotation-feature-group');
    if (!lines.length && !corners.length && !features.length) return;
    const carBounds = [...map.querySelectorAll('.marker > circle:first-of-type, .marker text')]
      .map(element => element.getBoundingClientRect());
    const visibleLabels = [];
    const overlaps = (bounds, other) => bounds.left < other.right && bounds.right > other.left && bounds.top < other.bottom && bounds.bottom > other.top;
    const overlapsCar = element => {
      const bounds = element.getBoundingClientRect();
      return carBounds.some(car => overlaps(bounds, car));
    };
    const overlapsLabel = element => visibleLabels.some(label => overlaps(element.getBoundingClientRect(), label));
    for (const group of lines) {
      const tag = group.querySelector('.annotation-tag');
      const text = group.querySelector('.annotation-tag-text');
      const hidden = (carBounds.length && (overlapsCar(tag) || overlapsCar(text))) || overlapsLabel(tag);
      tag.style.visibility = hidden ? 'hidden' : '';
      text.style.visibility = hidden ? 'hidden' : '';
      if (!hidden) visibleLabels.push(tag.getBoundingClientRect());
    }
    for (const group of corners) {
      const label = group.querySelector('.annotation-number');
      const hidden = (carBounds.length && [...group.children].some(overlapsCar)) || overlapsLabel(label);
      group.style.visibility = hidden ? 'hidden' : '';
      if (!hidden) visibleLabels.push(label.getBoundingClientRect());
    }
    for (const group of features) {
      const label = group.querySelector('.annotation-feature-text');
      const hidden = (carBounds.length && [...group.children].some(overlapsCar)) || overlapsLabel(label);
      group.style.visibility = hidden ? 'hidden' : '';
      if (!hidden) visibleLabels.push(label.getBoundingClientRect());
    }
  }
  reducedMotion() {
    return this.settings?.accessibility?.motion === 'reduced' || globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  }
  motionPoint(row, now = performance.now()) {
    const motion = this.motions.get(row.id);
    if (!motion) return row.point;
    if (!motion.duration || now >= motion.start + motion.duration) return motion.to;
    const progress = Math.max(0, Math.min(1, (now - motion.start) / motion.duration));
    return motion.from.map((value, index) => value + (motion.to[index] - value) * progress);
  }
  syncMotion(sessionChanged, modelChanged) {
    const rows = this.model?.rows ?? [], now = performance.now();
    if (!rows.length) {
      this.motions.clear();
      if (this.motionFrame) cancelAnimationFrame(this.motionFrame);
      this.motionFrame = 0; return;
    }
    const reduced = this.reducedMotion(), stale = this.model?.freshness?.stale;
    const next = new Map(); let active = false;
    for (const row of rows) {
      if (!row.point) continue;
      const existing = this.motions.get(row.id), previous = this.motionPoint(row, now);
      const unchanged = existing && existing.to.every((value, index) => value === row.point[index]);
      if (unchanged && !reduced && !sessionChanged && !stale && !row.stale) {
        next.set(row.id, existing);
        active ||= now < existing.start + existing.duration;
        continue;
      }
      const targetChanged = !existing || !unchanged;
      const rawInterval = modelChanged && targetChanged && existing ? now - existing.observedAt : null;
      const validInterval = rawInterval >= 120 && rawInterval <= 5000;
      const sampleInterval = sessionChanged ? 900 : validInterval
        ? (existing.sampleInterval * .7) + (rawInterval * .3)
        : existing?.sampleInterval ?? 900;
      const duration = Math.max(350, Math.min(2500, sampleInterval * 1.1));
      const distance = previous ? Math.hypot(row.point[0] - previous[0], row.point[1] - previous[1]) : Infinity;
      const animate = !reduced && !sessionChanged && !stale && !row.stale && previous && distance > .001 && distance <= 45;
      const observedAt = modelChanged && targetChanged ? now : existing?.observedAt ?? now;
      const motion = animate
        ? { from: previous, to: [...row.point], start: now, duration, observedAt, sampleInterval }
        : { from: [...row.point], to: [...row.point], start: now, duration: 0, observedAt, sampleInterval };
      next.set(row.id, motion); active ||= animate;
    }
    this.motions = next;
    if (!active && this.motionFrame) { cancelAnimationFrame(this.motionFrame); this.motionFrame = 0; }
    if (active) this.scheduleMotionFrame();
  }
  scheduleMotionFrame() {
    if (this.motionFrame || !this.isConnected) return;
    this.motionFrame = requestAnimationFrame(now => {
      this.motionFrame = 0; this.requestUpdate();
      if ([...this.motions.values()].some(motion => motion.duration && now < motion.start + motion.duration)) this.scheduleMotionFrame();
    });
  }
  accent(row) {
    const value = String(row.team_color ?? '').replace(/^#/, '');
    return this.settings.appearance.team_colors && /^[0-9a-f]{6}$/i.test(value) ? `#${value}` : 'transparent';
  }
  w(en, sv) { return words(this.settings?.language, en, sv); }
  state(row) {
    if (!row.point || row.point.some(value => value < 0 || value > 100)) return this.w('modular.position_outside_the_available_map');
    if (row.stale) return this.w('modular.saved_position_stale');
    const value = String(row.status ?? '').toLowerCase();
    return ({ ontrack: this.w('modular.on_track'), offtrack: this.w('modular.off_track') })[value] ?? row.status ?? this.w('modular.status_unavailable');
  }
  statusInfo() {
    const value = String(this.model?.trackStatus ?? '').trim();
    if (!value) return null;
    const normalized = value.toLowerCase().replaceAll('_', ' ');
    const tone = normalized.includes('red') ? '#e10600' : normalized.includes('yellow') || normalized.includes('safety') ? '#ffd400' : normalized.includes('blue') ? '#2f80ed' : normalized.includes('clear') || normalized.includes('green') ? '#18a558' : '#8a94a6';
    return { value, tone };
  }
  path() {
    let open = false;
    return this.model.points.map(point => {
      if (!point) { open = false; return ''; }
      const command = open ? 'L' : 'M'; open = true; return `${command}${point[0]},${point[1]}`;
    }).join(' ');
  }
  annotationName(field) {
    const names = { map_start_finish: 'modular.start_finish_line', map_corners: 'modular.corner_numbers', map_sectors: 'modular.sector_boundaries', map_speed_traps: 'modular.speed_traps', map_detection_zones: 'modular.detection_zones' };
    return this.w(names[field] ?? field);
  }
  render() {
    if (!this.model || !this.settings) return html``;
    const rows = this.model.rows ?? [], font = Math.max(2.2, 1400 / this.width);
    const annotations = this.model.annotations ?? { lines: [], corners: [], points: [], unavailable: [] };
    const featurePoints = annotations.points ?? [];
    const markingCount = annotations.lines.length + annotations.corners.length + featurePoints.length;
    const showMap = this.module.fields.includes('track_map') || this.module.fields.some(field => field.startsWith('map_') && field !== 'map_drivers');
    const showList = this.module.fields.includes('map_drivers');
    const options = this.module.options, showLabels = options.labels !== 'off';
    const status = this.statusInfo(), session = [this.model.context?.meeting, this.model.context?.session].filter(Boolean).join(' · ');
    const lap = this.model.lap === null || this.model.lap === undefined ? null : `${this.w('modular.lap')} ${this.model.lap}${this.model.totalLaps ? ` / ${this.model.totalLaps}` : ''}`;
    const layout = options.layout_mode === 'auto' ? '' : options.layout_mode;
    const source = this.model.sourceMode === 'replay' ? this.w('modular.recorded_replay_positions') : this.w('modular.live_positions');
    const lineMode = options.track_status_line_mode ?? 'accent';
    if (!showMap && !showList) return html`<p class="empty">${this.w('modular.choose_map_content_in_the_editor')}</p>`;
    return html`<div class="map-shell ${layout}" style=${`--track-status-color:${status?.tone ?? '#8a94a6'}`}>
      ${this.model.freshness?.stale ? html`<p class="chip">${this.w('modular.saved_positions_updates_delayed')}</p>` : ''}
      ${options.show_session_info ? html`<div class="map-meta"><strong>${session || this.w('modular.session_information_unavailable')}</strong><div class="map-badges">
        ${options.show_track_status && status ? html`<span class="map-status">${this.w('modular.track')}: ${status.value}</span>` : ''}
        ${options.show_lap_progress && lap ? html`<span class="map-status">${lap}</span>` : ''}
        ${options.show_driver_count ? html`<span class="map-status">${rows.length} ${this.w(rows.length === 1 ? 'driver' : 'drivers', rows.length === 1 ? 'förare' : 'förare')}</span>` : ''}
      </div></div>` : ''}
      ${showMap ? this.model.points ? html`<div class="map-frame"><svg viewBox="0 0 100 100" role="img" aria-labelledby="map-title map-description">
        <title id="map-title">${this.w('modular.driver_positions_on_the_track')}</title>
        <desc id="map-description">${showLabels ? this.w('modular.labels_identify_each_driver_a_dashed_outline_indicates_a_stale_position_use_the_driver') : this.w('modular.driver_labels_are_hidden_a_dashed_outline_indicates_a_stale_position_use_the_driver')} ${markingCount ? this.w('modular.track_markings_are_listed_below_the_map') : ''} ${status ? `${this.w('modular.track_status')}: ${status.value}.` : ''}</desc>
        ${lineMode === 'accent' && status ? svg`<path class="track-status-accent" d=${this.path()}></path>` : ''}
        <path class="track ${lineMode === 'full' && status ? 'status-full' : ''}" d=${this.path()}></path>
        ${repeat(annotations.lines, line => line.id, line => {
          const x = Math.min(92, Math.max(8, (line.start[0] + line.end[0]) / 2 - 7));
          const y = Math.min(96, Math.max(4, (line.start[1] + line.end[1]) / 2 - 5));
          return svg`<g class="annotation-line-group" aria-hidden="true"><line class="annotation-line-back" x1=${line.start[0]} y1=${line.start[1]} x2=${line.end[0]} y2=${line.end[1]}></line><line class="annotation-line" x1=${line.start[0]} y1=${line.start[1]} x2=${line.end[0]} y2=${line.end[1]}></line><rect class="annotation-tag" x=${x - 6} y=${y - 3} width="12" height="6" rx="1"></rect><text class="annotation-tag-text" x=${x} y=${y} text-anchor="middle" dominant-baseline="middle" font-size=${Math.max(3.2, font * .8)}>${line.layer === 'sectors' ? line.label : 'S/F'}</text></g>`;
        })}
        ${repeat(annotations.corners, corner => corner.id, corner => {
          const x = Math.min(96, Math.max(4, corner.point[0] + corner.offset[0]));
          const y = Math.min(96, Math.max(4, corner.point[1] + corner.offset[1]));
          return svg`<g class="annotation-corner-group" aria-hidden="true"><circle class="annotation-point" cx=${corner.point[0]} cy=${corner.point[1]} r="1"></circle><line class="annotation-leader" x1=${corner.point[0]} y1=${corner.point[1]} x2=${x} y2=${y}></line><text class="annotation-number" x=${x} y=${y} text-anchor="middle" dominant-baseline="middle" font-size=${Math.max(2.8, font * .85)}>${corner.label}</text></g>`;
        })}
        ${repeat(featurePoints, point => point.id, point => {
          const x = Math.min(96, Math.max(4, point.point[0] + point.offset[0]));
          const y = Math.min(96, Math.max(4, point.point[1] + point.offset[1]));
          return svg`<g class="annotation-feature-group" aria-hidden="true"><circle class="annotation-feature-point" cx=${point.point[0]} cy=${point.point[1]} r="1"></circle><line class="annotation-leader" x1=${point.point[0]} y1=${point.point[1]} x2=${x} y2=${y}></line><text class="annotation-feature-text" x=${x} y=${y} text-anchor="middle" dominant-baseline="middle" font-size=${Math.max(2.6, font * .7)}>${point.layer === 'speed_traps' ? 'T' : point.label.replace('DRS ', '')}</text></g>`;
        })}
        ${options.show_car_markers !== false ? repeat(rows.filter(row => row.point && row.point.every(value => value >= 0 && value <= 100)), row => row.id, row => {
          const point = this.motionPoint(row);
          return svg`<g style=${`--team-accent:${this.accent(row)}`} class="marker ${row.stale ? 'stale' : ''} ${row.selected || row.id === this.selected ? 'selected' : ''}" transform=${`translate(${point[0]} ${point[1]})`}><circle r="1.6"></circle><circle class="team" r="1"></circle>${showLabels ? svg`<text x=${point[0] + 2.2 + String(this.module.options.labels === 'number' ? row.id : row.driver).length * font * .7 > 99 ? -2.2 : 2.2} text-anchor=${point[0] + 2.2 + String(this.module.options.labels === 'number' ? row.id : row.driver).length * font * .7 > 99 ? 'end' : 'start'} y=${point[1] < font + 2 ? font + 1.5 : -1.5} font-size=${font}>${this.module.options.labels === 'number' ? row.id : row.driver}</text>` : ''}</g>`;
        }) : ''}
      </svg></div>` : html`<p class="empty">${this.w('modular.track_geometry_is_not_available_for_this_session_yet')}</p>` : ''}
      ${markingCount ? html`<div class="annotation-summary"><details><summary>${this.w('modular.track_markings')} · ${markingCount}</summary><ul>${annotations.lines.map(line => html`<li>${line.layer === 'sectors' ? `${this.annotationName('map_sectors')} ${line.label}` : this.annotationName('map_start_finish')}</li>`)}${annotations.corners.map(corner => html`<li>${this.w('modular.corner')} ${corner.label}</li>`)}${featurePoints.map(point => html`<li>${point.layer === 'speed_traps' ? this.annotationName('map_speed_traps') : point.label}</li>`)}</ul></details></div>` : ''}
      ${annotations.unavailable.length ? html`<p class="annotation-unavailable">${annotations.unavailable.map(field => this.annotationName(field)).join(', ')}: ${this.w('modular.no_verified_markings_for_this_session')}</p>` : ''}
      ${showList || showMap ? html`<details class="map-list" .open=${this.listOpen} @toggle=${event => { this.listOpen = event.target.open; }}><summary>${this.w('modular.driver_positions_and_status')}${this.module.options.show_driver_count === false ? '' : ` · ${rows.length}`}</summary>
        ${rows.length ? html`<ul class="driver-list">${repeat(rows, row => row.id, row => html`<li><button aria-pressed=${String(this.selected === row.id)} @click=${() => { this.selected = this.selected === row.id ? '' : row.id; }}><span>${row.id} · ${this.settings.appearance.full_names ? row.name : row.driver}<small>${row.team ?? ''}</small></span><span><span>${this.state(row)}</span><small>${dateTime(row.timestamp, this.settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</small></span></button></li>`)}</ul>` : html`<p class="empty">${this.w('modular.no_driver_positions_are_available_live_positioning_needs_f1tv_access_and_a_supported_session')}</p>`}
      </details>` : ''}
      ${options.show_footer ? html`<div class="map-footer"><span>${source}</span><span>${this.model.context?.updated ? dateTime(this.model.context.updated, this.settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : this.w('modular.update_time_unavailable')}</span></div>` : ''}
    </div>`;
  }
}
if (!customElements.get('f1-track-map-view')) customElements.define('f1-track-map-view', F1TrackMapView);
