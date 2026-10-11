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
    .annotation-line-back { stroke:var(--f1-panel); stroke-width:2.6; }
    .annotation-line { stroke:var(--f1-text); stroke-width:1.15; }
    .annotation-line.sector { stroke:var(--f1-muted); stroke-width:.85; stroke-dasharray:.8 .55; }
    .annotation-tag-text { fill:var(--f1-muted); font-weight:700; paint-order:stroke; stroke:var(--f1-panel); stroke-width:.7; }
    .annotation-leader { stroke:var(--f1-muted); stroke-width:.25; }
    .annotation-number { fill:var(--f1-text); font-weight:700; paint-order:stroke; stroke:var(--f1-panel); stroke-width:.8; font-variant-numeric:tabular-nums; }
    .annotation-feature-tick { stroke:var(--f1-muted); stroke-width:.65; stroke-linecap:round; }
    .annotation-feature-tick.low-grip { stroke-dasharray:.35 .35; }
    .annotation-feature-text { fill:var(--f1-muted); font-weight:650; paint-order:stroke; stroke:var(--f1-panel); stroke-width:.8; }
    .annotation-summary { color:var(--f1-muted); font-size:.83em; }
    .annotation-experimental { display:inline-flex; align-items:center; border:1px solid var(--f1-border); border-radius:999px; padding:1px 6px; color:var(--f1-muted); font-size:.76em; font-weight:650; line-height:1.4; white-space:nowrap; }
    .annotation-heading { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
    .annotation-note { color:var(--f1-muted); font-size:.82em; }
    .annotation-summary details { margin-top:4px; }
    .annotation-summary summary { min-height:44px; display:flex; align-items:center; cursor:pointer; }
    .annotation-summary summary:focus-visible { outline:3px solid var(--f1-focus); outline-offset:3px; }
    .annotation-summary ul { display:flex; flex-wrap:wrap; gap:4px 14px; margin:0; padding:0 0 0 20px; }
    .annotation-unavailable { margin:0; color:var(--f1-muted); font-size:.82em; }
    .driver-list { display:grid; gap:6px; list-style:none; margin:14px 0 0; padding:0; }
    .driver-list button { width:100%; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:6px 12px; text-align:left; }
    .driver-list small { display:block; font-size:.8em; }
    @media(forced-colors:active) { .track,.marker circle,.annotation-line,.annotation-feature-tick,.annotation-leader { stroke:CanvasText!important; } .marker text,.annotation-number,.annotation-feature-text,.annotation-tag-text { fill:CanvasText!important; stroke:Canvas!important; } .marker .team { display:none; } }
  `];
  constructor() {
    super(); this.width = 400; this.selected = ''; this.listOpen = false;
    this.motions = new Map(); this.motionFrame = 0; this.tickCache = new WeakMap();
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
  sectorStart(line) { return line.label === 'S1' ? 'S2' : line.label === 'S2' ? 'S3' : line.label; }
  featureCaption(point, allPoints) {
    if (point.layer === 'speed_traps') return 'SPD';
    const straightMode = /^SM A([1-5]) ([NL])$/.exec(point.label);
    if (straightMode) {
      const [, group, grip] = straightMode;
      const paired = allPoints.some(candidate => candidate.label === `SM A${group} ${grip === 'N' ? 'L' : 'N'}`);
      if (grip === 'L') return paired ? '' : `SM${group} L`;
      return `SM${group} ${paired ? 'N/L' : 'N'}`;
    }
    if (point.label === 'OT A') return 'OT';
    return point.label.replace('DRS ', '');
  }
  featureDescription(point) {
    if (point.layer === 'speed_traps') return this.annotationName('map_speed_traps');
    const straightMode = /^SM A([1-5]) ([NL])$/.exec(point.label);
    if (straightMode) return `${point.label} · ${this.w('modular.straight_mode_activation')}, ${this.w(straightMode[2] === 'N' ? 'modular.normal_grip' : 'modular.low_grip')}`;
    if (point.label === 'OT A') return `${point.label} · ${this.w('modular.overtake_activation')}`;
    const drs = /^DRS ([DA])([1-4])$/.exec(point.label);
    return drs ? `${point.label} · ${this.w(drs[1] === 'D' ? 'modular.detection' : 'modular.activation')}` : point.label;
  }
  featureTick(point) {
    let tangent = [1, 0], nearest = Infinity;
    const points = this.model.points;
    let ticks = this.tickCache.get(points);
    if (!ticks) { ticks = new Map(); this.tickCache.set(points, ticks); }
    const key = `${point.point[0]},${point.point[1]}`;
    if (ticks.has(key)) return ticks.get(key);
    for (let index = 1; index < points.length; index++) {
      const start = points[index - 1], end = points[index];
      if (!start || !end) continue;
      const dx = end[0] - start[0], dy = end[1] - start[1], lengthSquared = dx * dx + dy * dy;
      if (lengthSquared < 1e-8) continue;
      const fraction = Math.max(0, Math.min(1, ((point.point[0] - start[0]) * dx + (point.point[1] - start[1]) * dy) / lengthSquared));
      const distance = (point.point[0] - start[0] - fraction * dx) ** 2 + (point.point[1] - start[1] - fraction * dy) ** 2;
      if (distance < nearest) { nearest = distance; tangent = [dx, dy]; }
    }
    const length = Math.hypot(...tangent), normal = [-tangent[1] / length, tangent[0] / length];
    const tick = [point.point[0] - normal[0] * 1.1, point.point[1] - normal[1] * 1.1, point.point[0] + normal[0] * 1.1, point.point[1] + normal[1] * 1.1];
    ticks.set(key, tick);
    return tick;
  }
  markingLabels(annotations, featurePoints, font) {
    const labels = new Map(), occupied = [];
    const place = (id, text, size, candidates) => {
      const width = text.length * size * .78 + .6, height = size * 1.65;
      const choices = candidates.map(([x, y, anchor = 'middle']) => {
        const left = anchor === 'end' ? x - width : anchor === 'start' ? x : x - width / 2;
        return { x, y, anchor, box: { left, right: left + width, top: y - height / 2, bottom: y + height / 2 } };
      }).filter(({ box }) => box.left >= 2 && box.right <= 98 && box.top >= 2 && box.bottom <= 98);
      const overlap = choice => occupied.reduce((area, box) => area + Math.max(0, Math.min(choice.box.right, box.right) - Math.max(choice.box.left, box.left) + .35) * Math.max(0, Math.min(choice.box.bottom, box.bottom) - Math.max(choice.box.top, box.top) + .35), 0);
      const chosen = choices.find(choice => overlap(choice) === 0) ?? choices.reduce((best, choice) => !best || overlap(choice) < overlap(best) ? choice : best, null) ?? choices[0];
      if (chosen) { labels.set(id, chosen); occupied.push(chosen.box); }
    };
    for (const corner of annotations.corners) {
      const x = corner.point[0] + corner.offset[0] * .7, y = corner.point[1] + corner.offset[1] * .7;
      place(`corner:${corner.id}`, corner.label, Math.max(1.9, font * .58), [[x, y], [corner.point[0] - 2.5, corner.point[1] - 2.5], [corner.point[0] + 2.5, corner.point[1] - 2.5], [corner.point[0] - 2.5, corner.point[1] + 2.5], [corner.point[0] + 2.5, corner.point[1] + 2.5]]);
    }
    for (const line of annotations.lines.filter(item => item.layer === 'sectors')) {
      const x = (line.start[0] + line.end[0]) / 2, y = (line.start[1] + line.end[1]) / 2;
      const caption = this.sectorStart(line);
      place(`sector:${line.id}`, caption, Math.max(1.9, font * .55), [[x + 2, y - 2], [x - 2, y - 2], [x + 2, y + 2], [x - 2, y + 2]]);
    }
    for (const point of featurePoints) {
      const caption = this.featureCaption(point, featurePoints);
      if (!caption) continue;
      const x = point.point[0], y = point.point[1], size = Math.max(1.8, font * .55);
      const preferredX = Math.min(97, Math.max(3, x + point.offset[0] * .6));
      const edgeX = Math.min(97, Math.max(3, x + (x > 75 ? 2 : x < 25 ? -2 : 0)));
      const edgeAnchor = x > 75 ? 'end' : x < 25 ? 'start' : 'middle';
      place(`feature:${point.id}`, caption, size, [[preferredX, Math.min(97, Math.max(3, y + point.offset[1] * .6)), preferredX > 86 ? 'end' : preferredX < 14 ? 'start' : 'middle'], [x - 1.8, y - 1.8, 'end'], [x + 1.8, y - 1.8, 'start'], [x - 1.8, y + 1.8, 'end'], [x + 1.8, y + 1.8, 'start'], [x, y - 3.8], [x, y + 3.8], [edgeX, y - 5.5, edgeAnchor], [edgeX, y + 5.5, edgeAnchor]]);
    }
    return labels;
  }
  render() {
    if (!this.model || !this.settings) return html``;
    const rows = this.model.rows ?? [], font = Math.max(2.2, 1400 / this.width);
    const annotations = this.model.annotations ?? { lines: [], corners: [], points: [], unavailable: [] };
    const featurePoints = annotations.points ?? [];
    const labels = this.markingLabels(annotations, featurePoints, font);
    const markingCount = annotations.lines.length + annotations.corners.length + featurePoints.length;
    const annotationsSelected = this.module.fields.some(field => ['map_start_finish', 'map_corners', 'map_sectors', 'map_speed_traps', 'map_detection_zones'].includes(field));
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
          return svg`<g class="annotation-line-group" aria-hidden="true"><line class="annotation-line-back" x1=${line.start[0]} y1=${line.start[1]} x2=${line.end[0]} y2=${line.end[1]}></line><line class="annotation-line ${line.layer === 'sectors' ? 'sector' : ''}" x1=${line.start[0]} y1=${line.start[1]} x2=${line.end[0]} y2=${line.end[1]}></line></g>`;
        })}
        ${options.show_car_markers !== false ? repeat(rows.filter(row => row.point && row.point.every(value => value >= 0 && value <= 100)), row => row.id, row => {
          const point = this.motionPoint(row);
          return svg`<g style=${`--team-accent:${this.accent(row)}`} class="marker ${row.stale ? 'stale' : ''} ${row.selected || row.id === this.selected ? 'selected' : ''}" transform=${`translate(${point[0]} ${point[1]})`}><circle r="1.6"></circle><circle class="team" r="1"></circle>${showLabels ? svg`<text x=${point[0] + 2.2 + String(this.module.options.labels === 'number' ? row.id : row.driver).length * font * .7 > 99 ? -2.2 : 2.2} text-anchor=${point[0] + 2.2 + String(this.module.options.labels === 'number' ? row.id : row.driver).length * font * .7 > 99 ? 'end' : 'start'} y=${point[1] < font + 2 ? font + 1.5 : -1.5} font-size=${font}>${this.module.options.labels === 'number' ? row.id : row.driver}</text>` : ''}</g>`;
        }) : ''}
        ${repeat(annotations.lines.filter(line => line.layer === 'sectors'), line => line.id, line => {
          const label = labels.get(`sector:${line.id}`);
          return label ? svg`<text class="annotation-tag-text" aria-hidden="true" x=${label.x} y=${label.y} text-anchor=${label.anchor} dominant-baseline="middle" font-size=${Math.max(1.9, font * .55)}>${this.sectorStart(line)}</text>` : '';
        })}
        ${repeat(annotations.corners, corner => corner.id, corner => {
          const label = labels.get(`corner:${corner.id}`);
          return label ? svg`<g class="annotation-corner-group" aria-hidden="true"><line class="annotation-leader" x1=${corner.point[0]} y1=${corner.point[1]} x2=${label.x} y2=${label.y}></line><text class="annotation-number" x=${label.x} y=${label.y} text-anchor=${label.anchor} dominant-baseline="middle" font-size=${Math.max(1.9, font * .58)}>${corner.label}</text></g>` : '';
        })}
        ${repeat(featurePoints, point => point.id, point => {
          const caption = this.featureCaption(point, featurePoints);
          const label = labels.get(`feature:${point.id}`), tick = this.featureTick(point);
          return svg`<g class="annotation-feature-group" aria-hidden="true"><title>${this.featureDescription(point)}</title><line class="annotation-feature-tick ${/^SM A[1-5] L$/.test(point.label) ? 'low-grip' : ''}" x1=${tick[0]} y1=${tick[1]} x2=${tick[2]} y2=${tick[3]}></line>${caption && label ? svg`<line class="annotation-leader" x1=${point.point[0]} y1=${point.point[1]} x2=${label.x} y2=${label.y}></line><text class="annotation-feature-text" x=${label.x} y=${label.y} text-anchor=${label.anchor} dominant-baseline="middle" font-size=${Math.max(1.8, font * .55)}>${caption}</text>` : ''}</g>`;
        })}
      </svg></div>` : html`<p class="empty">${this.w('modular.track_geometry_is_not_available_for_this_session_yet')}</p>` : ''}
      ${annotationsSelected ? html`<div class="annotation-heading"><span class="annotation-experimental">${this.w('modular.experimental')}</span><span class="annotation-note">${this.w('modular.track_markings_experimental_note')}</span></div>` : ''}
      ${markingCount ? html`<div class="annotation-summary"><details><summary>${this.w('modular.track_markings')} · ${markingCount}</summary><ul>${annotations.lines.map(line => html`<li>${line.layer === 'sectors' ? `${this.annotationName('map_sectors')} ${line.label}/${this.sectorStart(line)}` : this.annotationName('map_start_finish')}</li>`)}${annotations.corners.map(corner => html`<li>${this.w('modular.corner')} ${corner.label}</li>`)}${featurePoints.map(point => html`<li>${this.featureDescription(point)}</li>`)}</ul></details></div>` : ''}
      ${annotations.unavailable.length ? html`<p class="annotation-unavailable">${annotations.unavailable.map(field => this.annotationName(field)).join(', ')}: ${this.w('modular.no_verified_markings_for_this_session')}</p>` : ''}
      ${showList || showMap ? html`<details class="map-list" .open=${this.listOpen} @toggle=${event => { this.listOpen = event.target.open; }}><summary>${this.w('modular.driver_positions_and_status')}${this.module.options.show_driver_count === false ? '' : ` · ${rows.length}`}</summary>
        ${rows.length ? html`<ul class="driver-list">${repeat(rows, row => row.id, row => html`<li><button aria-pressed=${String(this.selected === row.id)} @click=${() => { this.selected = this.selected === row.id ? '' : row.id; }}><span>${row.id} · ${this.settings.appearance.full_names ? row.name : row.driver}<small>${row.team ?? ''}</small></span><span><span>${this.state(row)}</span><small>${dateTime(row.timestamp, this.settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</small></span></button></li>`)}</ul>` : html`<p class="empty">${this.w('modular.no_driver_positions_are_available_live_positioning_needs_f1tv_access_and_a_supported_session')}</p>`}
      </details>` : ''}
      ${options.show_footer ? html`<div class="map-footer"><span>${source}</span><span>${this.model.context?.updated ? dateTime(this.model.context.updated, this.settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : this.w('modular.update_time_unavailable')}</span></div>` : ''}
    </div>`;
  }
}
if (!customElements.get('f1-track-map-view')) customElements.define('f1-track-map-view', F1TrackMapView);
