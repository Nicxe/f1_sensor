const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, css, repeat }, { moduleTitle, translatePlural, words }, configAPI] = await Promise.all([load('../f1-lit-3.3.2.js'), load('./catalog.js'), load('./config.js')]);

// This editor-only overview keeps pointer previews local. A completed gesture
// emits one change, so Home Assistant and Undo never receive partial moves.
export class F1ModuleArranger extends LitElement {
  static properties = { config: { attribute: false }, language: {}, selected: {}, draft: { state: true }, draftStacks: { state: true }, announcement: { state: true } };
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
    .board[data-layout=stacks] { align-items:start; }
    .stack-group { min-width:0; padding:8px; border:1px dashed var(--f1-border); border-radius:10px; }
    .stack-group[data-active=true] { outline:2px dashed var(--primary-color,#03a9f4); outline-offset:-2px; }
    .stack-head { display:flex; align-items:center; gap:6px; margin-bottom:4px; }
    .stack-heading { flex:1; min-width:0; font-size:.85em; overflow-wrap:anywhere; }
    .stack-heading strong,.stack-heading small { display:block; }
    .stack-heading small { margin-top:3px; color:var(--f1-muted); }
    .stack-resize { cursor:ew-resize; }
    .stack-modules { display:flex; flex-direction:column; min-width:0; }
    .stack-modules .tile { min-height:104px; padding-bottom:36px; }
    .stack-modules .tile[data-selected=true] { padding-bottom:35px; }
    .dropzone { display:grid; place-items:center; min-height:32px; padding:4px; margin:3px 0; border:1px dashed var(--f1-border); border-radius:6px; color:var(--f1-muted); font-size:11px; text-align:center; }
    .dropzone[data-active=true] { border:2px solid var(--primary-color,#03a9f4); color:var(--f1-text); background:color-mix(in srgb,var(--primary-color,#03a9f4) 12%,var(--f1-surface)); }
    @media(forced-colors:active) { .tile[data-selected=true],.tile[data-active=true],.ghost { border-color:Highlight; } }
  `;
  constructor() {
    super(); this.language = 'en'; this.announcement = ''; this.draft = null; this.draftStacks = null;
    this.cancel = () => this.finish(false);
    this.escape = event => { if (event.key === 'Escape' && this.gesture) { event.preventDefault(); event.stopPropagation(); this.finish(false); } };
  }
  w(source, replacements = {}) { return words(this.language, source, replacements); }
  get independent() { return this.config.layout === 'stacks'; }
  get columns() { return ['columns', 'stacks'].includes(this.config.layout) ? this.config.columns : 1; }
  get modules() { return this.draft ?? this.config.modules; }
  get stacks() { return this.draftStacks ?? configAPI.layoutStacks(this.config); }
  stackTitle(stack) { return this.w('modular.stack_number', { number: this.stacks.findIndex(item => item.id === stack.id) + 1 }); }
  publishStacks(next) { this.emit({ modules: next.modules, stacks: next.stacks }); }
  moveToStack(id, stackId) {
    const current = this.stacks.find(stack => stack.modules.includes(id));
    if (current?.id === stackId) return;
    this.pendingFocus = { id, mode: 'move' };
    this.publishStacks(configAPI.placeModuleInStack(this.config, id, stackId));
  }
  changeStackWidth(id, value) {
    if (this.stacks.find(stack => stack.id === id)?.column_span === value) return;
    this.publishStacks(configAPI.changeStackWidth(this.config, id, value));
  }
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
    if (this.independent) return this.moveWithinStackKey(event, id);
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
  moveWithinStackKey(event, id) {
    const stack = this.stacks.find(item => item.modules.includes(id));
    if (!stack || this.gesture) return;
    const index = stack.modules.indexOf(id);
    const target = ({ ArrowLeft: index - 1, ArrowUp: index - 1, ArrowRight: index + 1, ArrowDown: index + 1, Home: 0, End: stack.modules.length - 1 })[event.key];
    if (target === undefined) return;
    event.preventDefault(); this.choose(id);
    const next = Math.max(0, Math.min(stack.modules.length - 1, target));
    if (next === index) return;
    this.pendingFocus = { id, mode: 'move' };
    this.announcement = this.w('modular.position_value_of_length', { value: next + 1, length: stack.modules.length });
    this.publishStacks(configAPI.placeModuleInStack(this.config, id, stack.id, next));
  }
  moveStackKey(event, id) {
    const index = this.stacks.findIndex(item => item.id === id);
    const target = ({ ArrowLeft: index - 1, ArrowUp: index - 1, ArrowRight: index + 1, ArrowDown: index + 1, Home: 0, End: this.stacks.length - 1 })[event.key];
    if (target === undefined || this.gesture) return;
    event.preventDefault();
    const next = Math.max(0, Math.min(this.stacks.length - 1, target));
    if (next === index) return;
    this.pendingFocus = { id, mode: 'stack-move' };
    this.announcement = this.w('modular.stack_position', { position: next + 1, length: this.stacks.length });
    this.publishStacks(configAPI.moveStack(this.config, id, next - index));
  }
  resizeStackKey(event, stack) {
    const span = stack.column_span === 'full' ? this.columns : Math.min(stack.column_span, this.columns);
    const next = ({ ArrowLeft: span - 1, ArrowRight: span + 1, Home: 1, End: this.columns })[event.key];
    if (next === undefined || this.gesture) return;
    event.preventDefault();
    this.pendingFocus = { id: stack.id, mode: 'stack-resize' };
    this.changeStackWidth(stack.id, Math.max(1, Math.min(this.columns, next)));
  }
  resizeKey(event, module) {
    const span = module.column_span === 'full' ? this.columns : Math.min(module.column_span, this.columns);
    const next = ({ ArrowLeft: span - 1, ArrowRight: span + 1, Home: 1, End: this.columns })[event.key];
    if (next === undefined || this.gesture) return;
    event.preventDefault(); this.choose(module.id); this.changeWidth(module.id, Math.max(1, Math.min(this.columns, next)));
  }
  focusHandle(id, mode) {
    const stack = mode.startsWith('stack-');
    [...this.renderRoot.querySelectorAll(`[data-handle=${mode}]`)].find(node => stack ? node.closest('[data-stack-id]')?.dataset.stackId === id : node.closest('[data-id]')?.dataset.id === id)?.focus({ preventScroll: true });
  }
  start(event, id, mode) {
    if (this.gesture || event.button !== 0 || event.isPrimary === false) return;
    event.preventDefault(); event.stopPropagation(); event.currentTarget.focus({ preventScroll: true });
    const board = this.renderRoot.querySelector('.board');
    const stackGesture = mode.startsWith('stack-');
    const module = stackGesture ? this.stacks.find(stack => stack.id === id) : this.config.modules.find(module => module.id === id);
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
    if (!stackGesture) this.choose(id);
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
    if (g.mode === 'stack-resize') {
      const scrolled = this.renderRoot.querySelector('.scroll').scrollLeft - g.scrollLeft;
      const span = Math.max(1, Math.min(this.columns, g.span + Math.round((g.x - g.startX + scrolled) / g.pitch)));
      const saved = configAPI.layoutStacks(this.config).find(stack => stack.id === g.id);
      const width = span === g.span ? saved.column_span : span;
      this.draftStacks = configAPI.layoutStacks(this.config).map(stack => stack.id === g.id ? { ...stack, column_span: width } : stack);
      this.announcement = this.widthText(this.stacks.find(stack => stack.id === g.id));
    } else if (g.mode === 'stack-move') {
      this.reorderStacksAt(g);
      this.announcement = this.w('modular.stack_position', { position: this.stacks.findIndex(stack => stack.id === g.id) + 1, length: this.stacks.length });
    } else if (this.independent) {
      this.stackDestinationAt(g);
      this.announcement = g.destination ? this.w('modular.stacks_drop_position', { position: g.destination.index + 1, stack: this.stackTitle(this.stacks.find(stack => stack.id === g.destination.id)) }) : '';
    } else if (g.mode === 'resize') {
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
  stackDestinationAt(g) {
    // Keep the groups still during a module drag, with a marked insertion area.
    // This avoids a target moving away while a captured pointer is held over it.
    g.destination = null;
    const group = [...g.board.querySelectorAll('.stack-group')].find(node => this.inside(node.getBoundingClientRect(), g.x, g.y));
    if (!group) return;
    const stack = this.stacks.find(item => item.id === group.dataset.stackId);
    const zone = [...group.querySelectorAll('.dropzone')].find(node => this.inside(node.getBoundingClientRect(), g.x, g.y));
    let index;
    if (zone) index = Number(zone.dataset.position);
    else {
      const tiles = [...group.querySelectorAll('.tile')];
      index = tiles.findIndex(node => g.y < node.getBoundingClientRect().top + node.getBoundingClientRect().height / 2);
      if (index < 0) index = stack.modules.length;
    }
    const previous = stack.modules.indexOf(g.id);
    g.destination = { id: stack.id, position: index, index: index - Number(previous >= 0 && previous < index) };
  }
  reorderStacksAt(g) {
    const nodes = [...g.board.querySelectorAll('.stack-group')];
    const current = nodes.find(node => node.dataset.stackId === g.id);
    if (!current || this.inside(current.getBoundingClientRect(), g.x, g.y)) return;
    const candidates = nodes.filter(node => node !== current).map(node => {
      const rect = node.getBoundingClientRect();
      return { id: node.dataset.stackId, rect, distance: Math.hypot(Math.max(rect.left - g.x, 0, g.x - rect.right), Math.max(rect.top - g.y, 0, g.y - rect.bottom)) };
    }).sort((a, b) => a.distance - b.distance);
    const target = candidates[0]; if (!target || !this.inside(g.board.getBoundingClientRect(), g.x, g.y)) return;
    const after = g.y > target.rect.bottom || (g.y >= target.rect.top && g.x > (target.rect.left + target.rect.right) / 2);
    const stacks = this.stacks.filter(stack => stack.id !== g.id);
    stacks.splice(stacks.findIndex(stack => stack.id === target.id) + Number(after), 0, this.stacks.find(stack => stack.id === g.id));
    if (stacks.some((stack, index) => stack.id !== this.stacks[index].id)) this.draftStacks = stacks;
  }
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
    const inside = this.inside(rect, g.x, g.y);
    if (this.independent && g.mode === 'move' && g.active && inside && g.destination) {
      const next = configAPI.placeModuleInStack(this.config, g.id, g.destination.id, g.destination.index);
      this.draft = next.modules; this.draftStacks = next.stacks;
    }
    this.finish(g.active && (g.mode.endsWith('resize') || inside) && (!this.independent || g.mode !== 'move' || Boolean(g.destination)));
  }
  finish(commit) {
    const g = this.gesture; if (!g) return;
    const modules = this.draft;
    const stacks = this.draftStacks;
    this.gesture = null; this.draft = null; this.draftStacks = null;
    cancelAnimationFrame(this.frame); this.frame = null;
    window.removeEventListener('keydown', this.escape, true); window.removeEventListener('blur', this.cancel);
    if (g.board.hasPointerCapture(g.pointer)) g.board.releasePointerCapture(g.pointer);
    const changed = this.independent ? Boolean(stacks && JSON.stringify(stacks) !== JSON.stringify(configAPI.layoutStacks(this.config))) : modules?.some((module, i) => module.id !== this.config.modules[i]?.id || module.column_span !== this.config.modules[i]?.column_span);
    if (commit && changed) {
      this.pendingFocus = { id: g.id, mode: g.mode };
      if (this.independent) {
        const byId = new Map(this.config.modules.map(module => [module.id, module]));
        this.emit({ modules: modules ?? stacks.flatMap(stack => stack.modules.map(id => byId.get(id))), stacks });
      } else this.emit({ modules });
    }
    this.announcement = !g.active ? '' : commit ? this.w('modular.arrangement_updated_you_can_undo_this_change') : this.w('modular.change_cancelled');
    this.requestUpdate();
    if (this.isConnected && !(commit && changed)) this.updateComplete.then(() => this.focusHandle(g.id, g.mode));
  }
  renderTile(module, index, stacked = false) {
    return html`<div class="tile" data-id=${module.id} data-selected=${String(module.id === this.selected)} data-active=${String(this.gesture?.active && this.gesture.id === module.id && (!stacked || this.gesture.mode === 'move'))} style=${stacked ? '' : `grid-column:${this.config.layout === 'columns' && module.column_span === 'full' ? '1 / -1' : `span ${this.config.layout === 'columns' ? Math.min(module.column_span, this.columns) : 1}`}`}>
      <div class="tile-head"><button class="handle" data-handle="move" aria-label=${`${this.w('modular.move')} ${moduleTitle(module, this.language)}`} aria-describedby="instructions" @pointerdown=${event => this.start(event, module.id, 'move')} @keydown=${event => this.moveKey(event, module.id)} @click=${() => this.choose(module.id)}>⠿</button>
        <button class="choose" aria-pressed=${String(module.id === this.selected)} @click=${() => this.choose(module.id)}><strong><span class="position">${index + 1}.</span> ${moduleTitle(module, this.language)}</strong>${!module.enabled ? html`<small>${this.w('modular.hidden_module')}</small>` : module.visibility?.length ? html`<small>${this.w('modular.conditional_visibility')}</small>` : ''}</button></div>
      <span class="width">${this.config.layout === 'columns' ? this.widthText(module) : this.w('modular.position_value', { value: index + 1 })}</span>
      ${this.config.layout === 'columns' ? html`<button class="handle resize" data-handle="resize" aria-label=${`${this.w('modular.resize')} ${moduleTitle(module, this.language)}`} aria-describedby="instructions" @pointerdown=${event => this.start(event, module.id, 'resize')} @keydown=${event => this.resizeKey(event, module)}>↔</button>` : ''}
    </div>`;
  }
  renderDropzone(stack, position) {
    const active = this.gesture?.active && this.gesture.mode === 'move' && this.gesture.destination?.id === stack.id && this.gesture.destination.position === position;
    return html`<div class="dropzone" data-stack-id=${stack.id} data-position=${position} data-active=${String(Boolean(active))} aria-hidden="true">${this.w('modular.stack_drop_here')}</div>`;
  }
  renderStacks() {
    const byId = new Map(this.modules.map(module => [module.id, module]));
    return repeat(this.stacks, stack => stack.id, stack => html`<section class="stack-group" data-stack-id=${stack.id} data-active=${String(this.gesture?.active && this.gesture.id === stack.id && this.gesture.mode.startsWith('stack-'))} aria-label=${this.stackTitle(stack)} style=${`grid-column:${stack.column_span === 'full' ? '1 / -1' : `span ${Math.min(stack.column_span, this.columns)}`}`}>
      <div class="stack-head"><button class="handle" data-handle="stack-move" aria-label=${this.w('modular.move_stack', { stack: this.stackTitle(stack) })} aria-describedby="instructions" @pointerdown=${event => this.start(event, stack.id, 'stack-move')} @keydown=${event => this.moveStackKey(event, stack.id)}>⠿</button><div class="stack-heading"><strong>${this.stackTitle(stack)}</strong><small class="stack-width">${this.widthText(stack)}</small></div><button class="handle stack-resize" data-handle="stack-resize" aria-label=${this.w('modular.resize_stack', { stack: this.stackTitle(stack) })} aria-describedby="instructions" @pointerdown=${event => this.start(event, stack.id, 'stack-resize')} @keydown=${event => this.resizeStackKey(event, stack)}>↔</button></div>
      <div class="stack-modules">${this.renderDropzone(stack, 0)}${repeat(stack.modules, id => id, (id, index) => html`${this.renderTile(byId.get(id), index, true)}${this.renderDropzone(stack, index + 1)}`)}</div>
    </section>`);
  }
  render() {
    if (!this.config) return html``;
    const selected = this.config.modules.find(module => module.id === this.selected);
    const selectedStack = this.independent ? this.stacks.find(stack => stack.modules.includes(this.selected)) : null;
    return html`
      <div class="controls">
        <label><span>${this.w('modular.module_layout')}</span><select aria-label=${this.w('modular.module_layout')} .value=${this.config.layout} @change=${event => this.emit({ layout: event.target.value })}>
          <option value="stack" ?selected=${this.config.layout === 'stack'}>${this.w('modular.stacked_modules')}</option><option value="tabs" ?selected=${this.config.layout === 'tabs'}>${this.w('modular.tabs')}</option><option value="columns" ?selected=${this.config.layout === 'columns'}>${this.w('modular.columns')}</option><option value="stacks" ?selected=${this.independent}>${this.w('modular.independent_stacks')}</option>
        </select></label>
        ${['columns', 'stacks'].includes(this.config.layout) ? html`<label><span>${this.w('modular.columns_in_layout')}</span><select aria-label=${this.w('modular.columns_in_layout')} .value=${String(this.columns)} @change=${event => this.emit({ columns: Number(event.target.value) })}>${[2, 3, 4].map(n => html`<option value=${n} ?selected=${n === this.columns}>${n}</option>`)}</select></label>` : ''}
      </div>
      <p id="instructions">${this.w(this.independent ? 'modular.stacks_arrangement_help' : 'modular.drag_a_move_handle_to_reorder_in_columns_drag_the_right_edge_to_resize')}</p>
      <p>${this.independent ? this.w('modular.stacks_overview_help') : this.config.layout === 'columns' ? this.w('modular.layout_overview_in_columns_columns_scroll_sideways_on_small_screens_the_finished_card_adapts', { columns: this.columns }) : this.w('modular.this_overview_shows_module_order_tabs_show_one_module_at_a_time_on_the')}</p>
      ${this.modules.some(module => !module.enabled || module.visibility?.length) ? html`<p>${this.w('modular.hidden_and_conditional_modules_remain_in_this_overview_so_you_can_arrange_them_visibility')}</p>` : ''}
      ${!this.modules.length ? html`<p>${this.w('modular.add_a_module_below_to_start_arranging')}</p>` : ''}
      <div class="scroll" tabindex="0" role="region" aria-label=${this.w('modular.module_arrangement')}>
        <div class="board" data-layout=${this.config.layout} style=${`--columns:${this.columns}`} @pointermove=${this.pointerMove} @pointerup=${this.pointerUp} @pointercancel=${this.cancel} @lostpointercapture=${this.cancel}>
          ${this.independent ? this.renderStacks() : repeat(this.modules, module => module.id, (module, index) => this.renderTile(module, index))}
        </div>
      </div>
      ${this.config.layout === 'columns' && selected ? html`<div class="controls"><label><span>${this.w('modular.width_of_selected_module')} · ${moduleTitle(selected, this.language)}</span><select aria-label=${this.w('modular.width_of_selected_module')} .value=${String(selected.column_span)} @change=${event => this.changeWidth(selected.id, event.target.value === 'full' ? 'full' : Number(event.target.value))}>${[1, 2, 3, 4].map(n => html`<option value=${n} ?selected=${selected.column_span === n}>${translatePlural(this.language, 'modular.column_count', n)}</option>`)}<option value="full" ?selected=${selected.column_span === 'full'}>${this.w('modular.full_card_width')}</option></select></label></div>` : ''}
      ${this.independent && selectedStack ? html`<div class="controls"><label><span>${this.w('modular.move_to_stack')} · ${moduleTitle(selected, this.language)}</span><select aria-label=${this.w('modular.move_to_stack')} .value=${selectedStack.id} @change=${event => this.moveToStack(selected.id, event.target.value === '__new__' ? '' : event.target.value)}>${this.stacks.map(stack => html`<option value=${stack.id} ?selected=${stack.id === selectedStack.id}>${this.stackTitle(stack)}</option>`)}<option value="__new__">${this.w('modular.new_stack')}</option></select></label><label><span>${this.w('modular.stack_width')} · ${this.stackTitle(selectedStack)}</span><select aria-label=${this.w('modular.stack_width')} .value=${String(selectedStack.column_span)} @change=${event => this.changeStackWidth(selectedStack.id, event.target.value === 'full' ? 'full' : Number(event.target.value))}>${[1, 2, 3, 4].map(n => html`<option value=${n} ?selected=${selectedStack.column_span === n}>${translatePlural(this.language, 'modular.column_count', n)}</option>`)}<option value="full" ?selected=${selectedStack.column_span === 'full'}>${this.w('modular.full_card_width')}</option></select></label></div>` : ''}
      <p class="status" role="status" aria-live="polite">${this.announcement || this.w('modular.select_a_module_to_edit_its_settings_below')}</p>
      ${this.gesture?.active && ['move', 'stack-move'].includes(this.gesture.mode) ? html`<div class="ghost" aria-hidden="true" style=${`left:${Math.min(innerWidth - 180, Math.max(8, this.gesture.x + 16))}px;top:${Math.max(8, Math.min(innerHeight - 60, this.gesture.y + 16))}px`}>${this.gesture.mode === 'stack-move' ? this.stackTitle(this.stacks.find(stack => stack.id === this.gesture.id)) : moduleTitle(this.modules.find(module => module.id === this.gesture.id), this.language)}</div>` : ''}
    `;
  }
}
if (!customElements.get('f1-module-arranger')) customElements.define('f1-module-arranger', F1ModuleArranger);
