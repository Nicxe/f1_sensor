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
    if (!customElements.get(tag)) return html`<p role="alert">${this.w('Reload the page to load the card editor.', 'Ladda om sidan för att hämta korteditorn.')}</p>`;
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
      ${isLegacyConfig(this.config) ? html`<section class="migration" aria-label=${this.w('Convert this card', 'Konvertera detta kort')}>
        <h3>${this.w('Try the modular F1 Sensor card', 'Prova det modulära F1 Sensor-kortet')}</h3>
        <p>${this.w('Review a converted configuration with your original saved for recovery. You can cancel before applying it.', 'Granska en konverterad konfiguration med originalet sparat för återställning. Du kan avbryta innan den tillämpas.')}</p>
        <button @click=${() => this.review()}>${this.w('Review conversion', 'Granska konvertering')}</button>
      </section>` : ''}
      ${this.error ? html`<p class="error" role="alert">${this.error}</p>` : ''}${this.childEditor()}`;
    const rows = this.proposal.rows;
    return html`<section class="migration" aria-label=${this.w('Review conversion', 'Granska konvertering')}>
      <h3>${this.w('Review before replacing this card', 'Granska innan kortet ersätts')}</h3>
      <p>${this.w('Apply changes only the card being edited. Save in Home Assistant to keep it. Its original configuration remains recoverable from the new editor, including unsupported settings.', 'Tillämpa ändrar bara kortet som redigeras. Spara i Home Assistant för att behålla det. Originalkonfigurationen kan återställas i den nya editorn, inklusive inställningar som saknar stöd.')}</p>
      <p>${this.w('To keep both cards visible, duplicate the original in the dashboard before converting the copy.', 'För att behålla båda korten synliga, duplicera originalet i dashboarden innan du konverterar kopian.')}</p>
      <label>${this.w('F1 Sensor installation', 'F1 Sensor-installation')}<select .value=${this.proposal.config.f1_entry_id} @change=${event => { this.entryId = event.target.value; this.review(); }}>
        <option value="" .selected=${!this.proposal.config.f1_entry_id}>${this.w('Choose an installation', 'Välj en installation')}</option>
        ${this.entries.map(entry => html`<option value=${entry.entry_id} .selected=${this.proposal.config.f1_entry_id === entry.entry_id}>${entry.title}</option>`)}
        ${this.proposal.config.f1_entry_id && !this.entries.some(e => e.entry_id === this.proposal.config.f1_entry_id) ? html`<option value=${this.proposal.config.f1_entry_id} .selected=${true}>${this.proposal.config.f1_entry_id}</option>` : ''}
      </select></label>
      ${['review', 'changed', 'mapped'].map(status => {
        const items = rows.filter(row => row.status === status); if (!items.length) return '';
        const title = status === 'review' ? this.w('Choose again or keep the original', 'Välj igen eller behåll originalet') : status === 'changed' ? this.w('Changed behavior', 'Ändrat beteende') : this.w('Transferred settings', 'Överförda inställningar');
        return html`<details ?open=${status === 'review'}><summary>${title} (${items.length})</summary><ul>${items.map(row => html`<li><strong>${row.path.startsWith('$') ? this.w('Card behavior', 'Kortets beteende') : row.path}</strong>${Object.hasOwn(this.config, row.path) ? html` <code>${JSON.stringify(this.config[row.path])}</code>` : ''}: ${this.w(row.message.en, row.message.sv)}</li>`)}</ul></details>`;
      })}
      <label class="check"><input type="checkbox" .checked=${this.accepted} @change=${event => { this.accepted = event.target.checked; }}>${this.w('I have reviewed the differences and settings that need to be chosen again.', 'Jag har granskat skillnaderna och inställningarna som behöver väljas igen.')}</label>
      <div class="buttons"><button @click=${() => { this.proposal = null; this.accepted = false; }}>${this.w('Cancel conversion', 'Avbryt konvertering')}</button><button ?disabled=${!this.accepted} @click=${() => { if (this.accepted) this.publish(this.proposal.config); }}>${this.w('Apply conversion', 'Tillämpa konvertering')}</button></div>
    </section><div class="preview"><h3>${this.w('Preview with sample data', 'Förhandsvisning med exempeldata')}</h3>${this.preview()}</div>`;
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
