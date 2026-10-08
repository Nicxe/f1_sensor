const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, css }, { copyConfig }, { isLegacyConfig, proposeMigration, LEGACY_MIGRATIONS }, { sharedStyles, words }, { makeDemo }, { watchEntries }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./config.js'), load('./migration.js'), load('./view.js'), load('./demo.js'), load('./connection.js'),
]);

// Only the documented getConfigElement entry point changes. The original card,
// its editor and every dashboard configuration remain untouched until Apply.
export class F1MigrationEditor extends LitElement {
  static properties = { hass: { attribute: false }, config: { state: true }, proposal: { state: true }, entries: { state: true }, accepted: { state: true }, error: { state: true }, entryId: { state: true } };
  static styles = [sharedStyles, css`
    :host { display:block; --f1-text:var(--primary-text-color,#e9edf3); --f1-muted:var(--secondary-text-color,#b9c1ce); --f1-surface:var(--card-background-color,#17202b); --f1-border:var(--divider-color,#637083); }
    .migration { margin:0 0 20px; padding:16px; border:1px solid var(--f1-border); border-radius:12px; }
    h3 { margin:0 0 8px; } p { margin:8px 0; } .buttons { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }
    label { display:block; margin:12px 0; } select { width:100%; min-height:44px; background:var(--f1-surface); color:var(--f1-text); padding:8px; }
    .check { display:flex; align-items:center; gap:10px; min-height:44px; } input { min-width:22px; min-height:22px; }
    summary { cursor:pointer; min-height:44px; align-content:center; font-weight:650; }
    ul { padding-left:22px; } li { margin:12px 0; overflow-wrap:anywhere; } code { overflow-wrap:anywhere; }
    .preview { margin-top:20px; } .error { color:var(--error-color,#ffb4b4); }
  `];
  constructor() { super(); this.entries = []; this.entryId = ''; this.error = ''; this.accepted = false; }
  get language() { return this.hass?.locale?.language ?? this.hass?.language ?? 'en'; }
  w(en, sv) { return words(this.language, en, sv); }
  setConfig(value) {
    const next = copyConfig(value);
    if (JSON.stringify(next) !== JSON.stringify(this.config)) { this.proposal = null; this.accepted = false; this.entryId = ''; }
    this.config = next;
  }
  connectedCallback() { super.connectedCallback(); this.requestUpdate(); }
  disconnectedCallback() { super.disconnectedCallback(); this.stopEntries?.(); this.stopEntries = null; this.connection = null; }
  willUpdate() {
    if (this.isConnected && this.hass?.connection && this.connection !== this.hass.connection) {
      this.stopEntries?.(); this.connection = this.hass.connection;
      this.stopEntries = watchEntries(this.hass, state => {
        if (!state.data) return;
        this.entries = state.data;
        if (this.proposal) this.review();
      });
    }
  }
  review() {
    try { this.proposal = proposeMigration(this.config, { entries: this.entries, entryId: this.entryId }); this.accepted = false; this.error = ''; }
    catch (error) { this.error = error.message; }
  }
  publish(config) {
    this.setConfig(config);
    this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: copyConfig(config) }, bubbles: true, composed: true }));
  }
  childEditor() {
    const type = this.config?.type?.replace(/^custom:/, '');
    const tag = `${type === 'f1-session-archive-card' ? 'f1-last-race-results-card' : type}-editor`;
    if (!customElements.get(tag)) return html`<p role="alert">${this.w('modular.reload_the_page_to_load_the_card_editor')}</p>`;
    if (this.child?.localName !== tag) {
      this.child = document.createElement(tag); this.childValue = '';
      this.child.addEventListener('config-changed', event => { event.stopPropagation(); this.publish(event.detail.config); });
    }
    const value = JSON.stringify(this.config);
    if (value !== this.childValue) { this.child.setConfig(copyConfig(this.config)); this.childValue = value; }
    this.child.hass = this.hass;
    return this.child;
  }
  previewScene() {
    const type = this.config?.type?.replace(/^custom:/, '');
    if (type === 'f1-qualifying-timing-card') return 'qualifying';
    if (type === 'f1-practice-timing-card') return 'practice';
    return 'race';
  }
  preview() {
    if (!this.previewNode) this.previewNode = document.createElement('f1-sensor-card');
    const config = this.proposal.config, demo = makeDemo(this.previewScene(), this.language, config.f1_entry_id);
    this.previewNode.previewData = demo.preview; this.previewNode.hass = demo.hass;
    this.previewNode.setConfig(config);
    return this.previewNode;
  }
  render() {
    if (!this.config) return html``;
    if (!this.proposal) return html`
      ${isLegacyConfig(this.config) ? html`<section class="migration" aria-label=${this.w('modular.convert_this_card')}>
        <h3>${this.w('modular.this_card_is_deprecated')}</h3>
        <p>${this.w('modular.this_card_continues_to_work_but_new_features_and_documentation_target_the_modular_f1')}</p>
        <button @click=${() => this.review()}>${this.w('modular.review_conversion')}</button>
      </section>` : ''}
      ${this.error ? html`<p class="error" role="alert">${this.error}</p>` : ''}${this.childEditor()}`;
    const rows = this.proposal.rows;
    return html`<section class="migration" aria-label=${this.w('modular.review_conversion')}>
      <h3>${this.w('modular.review_before_replacing_this_card')}</h3>
      <p>${this.w('modular.apply_changes_only_the_card_being_edited_save_in_home_assistant_to_keep_it')}</p>
      <p>${this.w('modular.to_keep_both_cards_visible_duplicate_the_original_in_the_dashboard_before_converting_the')}</p>
      <label>${this.w('modular.f1_sensor_installation')}<select .value=${this.proposal.config.f1_entry_id} @change=${event => { this.entryId = event.target.value; this.review(); }}>
        <option value="" .selected=${!this.proposal.config.f1_entry_id}>${this.w('modular.choose_an_installation')}</option>
        ${this.entries.map(entry => html`<option value=${entry.entry_id} .selected=${this.proposal.config.f1_entry_id === entry.entry_id}>${entry.title}</option>`)}
        ${this.proposal.config.f1_entry_id && !this.entries.some(e => e.entry_id === this.proposal.config.f1_entry_id) ? html`<option value=${this.proposal.config.f1_entry_id} .selected=${true}>${this.proposal.config.f1_entry_id}</option>` : ''}
      </select></label>
      ${['review', 'changed', 'mapped'].map(status => {
        const items = rows.filter(row => row.status === status); if (!items.length) return '';
        const title = status === 'review' ? this.w('modular.choose_again_or_keep_the_original') : status === 'changed' ? this.w('modular.changed_behavior') : this.w('modular.transferred_settings');
        return html`<details ?open=${status === 'review'}><summary>${title} (${items.length})</summary><ul>${items.map(row => html`<li><strong>${row.path.startsWith('$') ? this.w('modular.card_behavior') : row.path}</strong>${Object.hasOwn(this.config, row.path) ? html` <code>${JSON.stringify(this.config[row.path])}</code>` : ''}: ${this.w(row.message.en, row.message.sv)}</li>`)}</ul></details>`;
      })}
      <label class="check"><input type="checkbox" .checked=${this.accepted} @change=${event => { this.accepted = event.target.checked; }}>${this.w('modular.i_have_reviewed_the_differences_and_settings_that_need_to_be_chosen_again')}</label>
      <div class="buttons"><button @click=${() => { this.proposal = null; this.accepted = false; }}>${this.w('modular.cancel_conversion')}</button><button ?disabled=${!this.accepted} @click=${() => { if (this.accepted) this.publish(this.proposal.config); }}>${this.w('modular.apply_conversion')}</button></div>
    </section><div class="preview"><h3>${this.w('modular.preview_with_sample_data')}</h3>${this.preview()}</div>`;
  }
}
if (!customElements.get('f1-migration-editor')) customElements.define('f1-migration-editor', F1MigrationEditor);
export function installLegacyMigrationEditors() {
  for (const type of Object.keys(LEGACY_MIGRATIONS)) {
    const Card = customElements.get(type);
    if (!Card || Object.hasOwn(Card, 'f1MigrationEditorInstalled')) continue;
    Card.getConfigElement = () => document.createElement('f1-migration-editor');
    Object.defineProperty(Card, 'f1MigrationEditorInstalled', { value: true });
  }
}
