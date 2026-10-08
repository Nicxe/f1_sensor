const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, css, repeat }, { moduleTitle, translatePlural, words }] = await Promise.all([load('../f1-lit-3.3.2.js'), load('./catalog.js')]);

// This editor-only overview keeps pointer previews local. A completed gesture
// emits one change, so Home Assistant and Undo never receive partial moves.
export class F1ModuleArranger extends LitElement {
  static properties = { config: { attribute: false }, language: {}, selected: {}, draft: { state: true }, announcement: { state: true } };
  static styles = css`
    :host { display:block; min-width:0; color:var(--f1-text); }
    * { box-sizing:border-box; }
    p { margin:8px 0; font-size:.85em; line-height:1.5; }
    .controls { display:flex; flex-wrap:wrap; gap:12px; margin:12px 0; }
    label { flex:1; min-width:130px; font-size:.85em; }
    label span { display:block; margin-bottom:5px; }
    select,button { font:inherit; color:inherit; background:var(--f1-surface); border:1px solid var(--f1-border); border-radius:7px; min-height:44px; }
    select { width:100%; padding:8px; }
    button { cursor:pointer; }
    button:focus-visible,select:focus-visible,.scroll:focus-visible { outline:3px solid var(--primary-color,#03a9f4); outline-offset:2px; }
    .scroll { overflow:auto; max-height:520px; padding:4px; border:1px solid var(--f1-border); border-radius:10px; }
    .board { display:grid; grid-template-columns:repeat(var(--columns),minmax(0,1fr)); grid-auto-flow:row; gap:10px; min-width:calc(var(--columns) * 150px); padding:6px; direction:ltr; }
    .tile { position:relative; min-width:0; min-height:132px; padding:5px 5px 48px; border:1px solid var(--f1-border); border-radius:9px; background:var(--f1-surface); }
    .tile[data-selected=true] { border:2px solid var(--primary-color,#03a9f4); padding:4px 4px 47px; }
    .tile[data-active=true] { border:2px dashed var(--primary-color,#03a9f4); padding:4px 4px 47px; background:color-mix(in srgb,var(--primary-color,#03a9f4) 12%,var(--f1-surface)); }
    .tile-head { display:flex; align-items:flex-start; gap:4px; }
    .handle { flex:none; width:44px; touch-action:none; user-select:none; -webkit-user-select:none; cursor:grab; font-size:24px; }
    .choose { flex:1; min-width:0; padding:5px; text-align:left; border:0; background:transparent; overflow-wrap:anywhere; }
    .choose strong,.choose small { display:block; }
    .choose small { margin-top:5px; font-size:12px; line-height:1.4; color:var(--f1-muted); }
    .width { position:absolute; left:10px; bottom:12px; right:52px; font-size:12px; line-height:1.3; }
    .resize { position:absolute; right:2px; bottom:2px; cursor:ew-resize; }
    .position { font-variant-numeric:tabular-nums; }
    .ghost { position:fixed; z-index:1000; max-width:240px; padding:8px 12px; border:2px solid var(--primary-color,#03a9f4); border-radius:8px; background:var(--f1-surface); color:var(--f1-text); pointer-events:none; box-shadow:0 4px 18px #0005; font-size:13px; }
    .status { min-height:24px; }
    @media(forced-colors:active) { .tile[data-selected=true],.tile[data-active=true],.ghost { border-color:Highlight; } }
  `;
  constructor() {
    super(); this.language = 'en'; this.announcement = ''; this.draft = null;
    this.cancel = () => this.finish(false);
    this.escape = event => { if (event.key === 'Escape' && this.gesture) { event.preventDefault(); event.stopPropagation(); this.finish(false); } };
  }
  w(en, sv) { return words(this.language, en, sv); }
  get columns() { return this.config.layout === 'columns' ? this.config.columns : 1; }
  get modules() { return this.draft ?? this.config.modules; }
  willUpdate(changed) { if (changed.has('config') && this.gesture && this.config !== this.gesture.config) this.finish(false); }
  updated(changed) {
    if (changed.has('config') && this.pendingFocus) {
      const { id, mode } = this.pendingFocus; this.pendingFocus = null; this.focusHandle(id, mode);
    }
  }
  disconnectedCallback() { this.finish(false); super.disconnectedCallback(); }
  emit(detail) { this.dispatchEvent(new CustomEvent('arrangement-changed', { detail, bubbles: true, composed: true })); }
  choose(id) { this.dispatchEvent(new CustomEvent('module-selected', { detail: { id }, bubbles: true, composed: true })); }
  widthText(module) {
    if (module.column_span !== 'full' && module.column_span > this.columns) return this.w('modular.columns_of_columns_columns_saved_columnspan', { columns: this.columns, columnSpan: module.column_span });
    return module.column_span === 'full' ? this.w('modular.full_card_width') : this.w('modular.columnspan_of_columns_columns', { columnSpan: module.column_span, columns: this.columns });
  }
  changeWidth(id, value) {
    if (this.config.modules.find(module => module.id === id)?.column_span === value) return;
    this.emit({ modules: this.config.modules.map(module => module.id === id ? { ...module, column_span: value } : module) });
  }
  moveKey(event, id) {
    const index = this.config.modules.findIndex(module => module.id === id);
    const target = ({ ArrowLeft: index - 1, ArrowUp: index - 1, ArrowRight: index + 1, ArrowDown: index + 1, Home: 0, End: this.config.modules.length - 1 })[event.key];
    if (target === undefined || this.gesture) return;
    event.preventDefault(); this.choose(id);
    const next = Math.max(0, Math.min(this.config.modules.length - 1, target));
    if (next === index) return;
    const modules = [...this.config.modules]; modules.splice(next, 0, modules.splice(index, 1)[0]);
    this.announcement = this.w('modular.position_value_of_length', { value: next + 1, length: modules.length });
    this.pendingFocus = { id, mode: 'move' };
    this.emit({ modules });
  }
  resizeKey(event, module) {
    const span = module.column_span === 'full' ? this.columns : Math.min(module.column_span, this.columns);
    const next = ({ ArrowLeft: span - 1, ArrowRight: span + 1, Home: 1, End: this.columns })[event.key];
    if (next === undefined || this.gesture) return;
    event.preventDefault(); this.choose(module.id); this.changeWidth(module.id, Math.max(1, Math.min(this.columns, next)));
  }
  focusHandle(id, mode) { [...this.renderRoot.querySelectorAll(`[data-handle=${mode}]`)].find(node => node.closest('[data-id]').dataset.id === id)?.focus({ preventScroll: true }); }
  start(event, id, mode) {
    if (this.gesture || event.button !== 0 || event.isPrimary === false) return;
    event.preventDefault(); event.stopPropagation(); event.currentTarget.focus({ preventScroll: true });
    const board = this.renderRoot.querySelector('.board');
    const module = this.config.modules.find(module => module.id === id);
    const scrolls = [];
    for (let node = board; node; node = node.parentElement ?? node.getRootNode()?.host) {
      const style = getComputedStyle(node);
      if (/(auto|scroll)/.test(style.overflow + style.overflowX + style.overflowY)) scrolls.push(node);
    }
    if (!scrolls.includes(document.scrollingElement)) scrolls.push(document.scrollingElement);
    this.gesture = { id, mode, board, config: this.config, pointer: event.pointerId, startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY, span: module.column_span === 'full' ? this.columns : Math.min(module.column_span, this.columns), pitch: (board.clientWidth - 12 + 10) / this.columns, scrolls, scrollLeft: this.renderRoot.querySelector('.scroll').scrollLeft, active: false };
    board.setPointerCapture(event.pointerId);
    window.addEventListener('keydown', this.escape, true);
    window.addEventListener('blur', this.cancel);
    this.choose(id);
  }
  pointerMove(event) {
    const g = this.gesture; if (!g || event.pointerId !== g.pointer) return;
    g.x = event.clientX; g.y = event.clientY;
    if (!g.active && Math.hypot(g.x - g.startX, g.y - g.startY) < 7) return;
    event.preventDefault(); g.active = true;
    if (!this.frame) this.frame = requestAnimationFrame(() => this.tick());
  }
  tick() {
    this.frame = null;
    const g = this.gesture; if (!g?.active) return;
    this.autoScroll(g);
    if (g.mode === 'resize') {
      const scrolled = this.renderRoot.querySelector('.scroll').scrollLeft - g.scrollLeft;
      const span = Math.max(1, Math.min(this.columns, g.span + Math.round((g.x - g.startX + scrolled) / g.pitch)));
      // Returning to the starting width also restores 'full' or a wider saved span.
      const width = span === g.span ? this.config.modules.find(module => module.id === g.id).column_span : span;
      if (this.modules.find(module => module.id === g.id).column_span !== width) this.draft = this.config.modules.map(module => module.id === g.id ? { ...module, column_span: width } : module);
      this.announcement = this.widthText(this.modules.find(module => module.id === g.id));
    } else {
      this.reorderAt(g);
      this.announcement = this.w('modular.drop_at_position_value_of_length', { value: this.modules.findIndex(module => module.id === g.id) + 1, length: this.modules.length });
    }
    this.requestUpdate();
    this.frame = requestAnimationFrame(() => this.tick());
  }
  inside(rect, x, y) { return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom; }
  reorderAt(g) {
    const nodes = [...g.board.querySelectorAll('.tile')];
    const current = nodes.find(node => node.dataset.id === g.id);
    if (this.inside(current.getBoundingClientRect(), g.x, g.y)) return;
    const candidates = nodes.filter(node => node !== current).map(node => {
      const rect = node.getBoundingClientRect();
      const distance = Math.hypot(Math.max(rect.left - g.x, 0, g.x - rect.right), Math.max(rect.top - g.y, 0, g.y - rect.bottom));
      return { id: node.dataset.id, rect, distance };
    }).sort((a, b) => a.distance - b.distance);
    const target = candidates[0]; if (!target || !this.inside(g.board.getBoundingClientRect(), g.x, g.y)) return;
    const after = this.columns === 1 ? g.y > (target.rect.top + target.rect.bottom) / 2 : g.y > target.rect.bottom || (g.y >= target.rect.top && g.x > (target.rect.left + target.rect.right) / 2);
    const modules = this.modules.filter(module => module.id !== g.id);
    modules.splice(modules.findIndex(module => module.id === target.id) + Number(after), 0, this.modules.find(module => module.id === g.id));
    if (modules.some((module, i) => module.id !== this.modules[i].id)) this.draft = modules;
  }
  autoScroll(g) {
    let movedX = false, movedY = false;
    for (const node of g.scrolls) {
      const rect = node === document.scrollingElement ? { left: 0, top: 0, right: innerWidth, bottom: innerHeight } : node.getBoundingClientRect();
      if (!this.inside({ left: rect.left - 20, right: rect.right + 20, top: rect.top - 20, bottom: rect.bottom + 20 }, g.x, g.y)) continue;
      const delta = (point, start, end) => point < start + 32 ? -8 : point > end - 32 ? 8 : 0;
      const x = node.scrollLeft, y = node.scrollTop;
      node.scrollBy({ left: movedX ? 0 : delta(g.x, rect.left, rect.right), top: movedY ? 0 : delta(g.y, rect.top, rect.bottom), behavior: 'instant' });
      movedX ||= node.scrollLeft !== x; movedY ||= node.scrollTop !== y;
    }
  }
  pointerUp(event) {
    const g = this.gesture; if (!g || event.pointerId !== g.pointer) return;
    // Process the final position even if pointerup arrives before the next frame.
    g.x = event.clientX; g.y = event.clientY;
    if (g.active) { cancelAnimationFrame(this.frame); this.tick(); }
    const rect = this.renderRoot.querySelector('.scroll').getBoundingClientRect();
    this.finish(g.active && (g.mode === 'resize' || this.inside(rect, g.x, g.y)));
  }
  finish(commit) {
    const g = this.gesture; if (!g) return;
    const modules = this.draft;
    this.gesture = null; this.draft = null;
    cancelAnimationFrame(this.frame); this.frame = null;
    window.removeEventListener('keydown', this.escape, true); window.removeEventListener('blur', this.cancel);
    if (g.board.hasPointerCapture(g.pointer)) g.board.releasePointerCapture(g.pointer);
    const changed = modules?.some((module, i) => module.id !== this.config.modules[i]?.id || module.column_span !== this.config.modules[i]?.column_span);
    if (commit && changed) { this.pendingFocus = { id: g.id, mode: g.mode }; this.emit({ modules }); }
    this.announcement = !g.active ? '' : commit ? this.w('modular.arrangement_updated_you_can_undo_this_change') : this.w('modular.change_cancelled');
    this.requestUpdate();
    if (this.isConnected && !(commit && changed)) this.updateComplete.then(() => this.focusHandle(g.id, g.mode));
  }
  render() {
    if (!this.config) return html``;
    const selected = this.config.modules.find(module => module.id === this.selected);
    return html`
      <div class="controls">
        <label><span>${this.w('modular.module_layout')}</span><select aria-label=${this.w('modular.module_layout')} .value=${this.config.layout} @change=${event => this.emit({ layout: event.target.value })}>
          <option value="stack" ?selected=${this.config.layout === 'stack'}>${this.w('modular.stacked_modules')}</option><option value="tabs" ?selected=${this.config.layout === 'tabs'}>${this.w('modular.tabs')}</option><option value="columns" ?selected=${this.config.layout === 'columns'}>${this.w('modular.columns')}</option>
        </select></label>
        ${this.config.layout === 'columns' ? html`<label><span>${this.w('modular.columns_in_layout')}</span><select aria-label=${this.w('modular.columns_in_layout')} .value=${String(this.columns)} @change=${event => this.emit({ columns: Number(event.target.value) })}>${[2, 3, 4].map(n => html`<option value=${n} ?selected=${n === this.columns}>${n}</option>`)}</select></label>` : ''}
      </div>
      <p id="instructions">${this.w('modular.drag_a_move_handle_to_reorder_in_columns_drag_the_right_edge_to_resize')}</p>
      <p>${this.config.layout === 'columns' ? this.w('modular.layout_overview_in_columns_columns_scroll_sideways_on_small_screens_the_finished_card_adapts', { columns: this.columns }) : this.w('modular.this_overview_shows_module_order_tabs_show_one_module_at_a_time_on_the')}</p>
      ${this.modules.some(module => !module.enabled || module.visibility?.length) ? html`<p>${this.w('modular.hidden_and_conditional_modules_remain_in_this_overview_so_you_can_arrange_them_visibility')}</p>` : ''}
      ${!this.modules.length ? html`<p>${this.w('modular.add_a_module_below_to_start_arranging')}</p>` : ''}
      <div class="scroll" tabindex="0" role="region" aria-label=${this.w('modular.module_arrangement')}>
        <div class="board" style=${`--columns:${this.columns}`} @pointermove=${this.pointerMove} @pointerup=${this.pointerUp} @pointercancel=${this.cancel} @lostpointercapture=${this.cancel}>
          ${repeat(this.modules, module => module.id, (module, index) => html`<div class="tile" data-id=${module.id} data-selected=${String(module.id === this.selected)} data-active=${String(this.gesture?.active && this.gesture.id === module.id)} style=${`grid-column:${this.config.layout === 'columns' && module.column_span === 'full' ? '1 / -1' : `span ${this.config.layout === 'columns' ? Math.min(module.column_span, this.columns) : 1}`}`}>
            <div class="tile-head"><button class="handle" data-handle="move" aria-label=${`${this.w('modular.move')} ${moduleTitle(module, this.language)}`} aria-describedby="instructions" @pointerdown=${event => this.start(event, module.id, 'move')} @keydown=${event => this.moveKey(event, module.id)} @click=${() => this.choose(module.id)}>⠿</button>
              <button class="choose" aria-pressed=${String(module.id === this.selected)} @click=${() => this.choose(module.id)}><strong><span class="position">${index + 1}.</span> ${moduleTitle(module, this.language)}</strong>${!module.enabled ? html`<small>${this.w('modular.hidden_module')}</small>` : module.visibility?.length ? html`<small>${this.w('modular.conditional_visibility')}</small>` : ''}</button></div>
            <span class="width">${this.config.layout === 'columns' ? this.widthText(module) : this.w('modular.position_value', { value: index + 1 })}</span>
            ${this.config.layout === 'columns' ? html`<button class="handle resize" data-handle="resize" aria-label=${`${this.w('modular.resize')} ${moduleTitle(module, this.language)}`} aria-describedby="instructions" @pointerdown=${event => this.start(event, module.id, 'resize')} @keydown=${event => this.resizeKey(event, module)}>↔</button>` : ''}
          </div>`)}
        </div>
      </div>
      ${this.config.layout === 'columns' && selected ? html`<div class="controls"><label><span>${this.w('modular.width_of_selected_module')} · ${moduleTitle(selected, this.language)}</span><select aria-label=${this.w('modular.width_of_selected_module')} .value=${String(selected.column_span)} @change=${event => this.changeWidth(selected.id, event.target.value === 'full' ? 'full' : Number(event.target.value))}>${[1, 2, 3, 4].map(n => html`<option value=${n} ?selected=${selected.column_span === n}>${translatePlural(this.language, 'modular.column_count', n)}</option>`)}<option value="full" ?selected=${selected.column_span === 'full'}>${this.w('modular.full_card_width')}</option></select></label></div>` : ''}
      <p class="status" role="status" aria-live="polite">${this.announcement || this.w('modular.select_a_module_to_edit_its_settings_below')}</p>
      ${this.gesture?.active && this.gesture.mode === 'move' ? html`<div class="ghost" aria-hidden="true" style=${`left:${Math.min(innerWidth - 180, Math.max(8, this.gesture.x + 16))}px;top:${Math.max(8, Math.min(innerHeight - 60, this.gesture.y + 16))}px`}>${moduleTitle(this.modules.find(module => module.id === this.gesture.id), this.language)}</div>` : ''}
    `;
  }
}
if (!customElements.get('f1-module-arranger')) customElements.define('f1-module-arranger', F1ModuleArranger);
