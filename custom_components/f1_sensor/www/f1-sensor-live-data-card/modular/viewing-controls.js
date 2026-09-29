const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, css }, { sharedStyles, words, dateTime }] = await Promise.all([load('../f1-lit-3.3.2.js'), load('./view.js')]);

export class F1ViewingControls extends LitElement {
  static properties = { model: { attribute: false }, settings: { attribute: false }, connection: { attribute: false }, readonly: { type: Boolean }, localHidden: { type: Boolean }, request: { attribute: false }, draft: { state: true }, draftContext: { state: true }, confirmation: { state: true } };
  static styles = [sharedStyles, css`
    :host { margin-bottom:var(--f1-section-space,20px); }
    details { border:1px solid var(--f1-divider); border-radius:8px; padding:0 12px; }
    summary { min-height:44px; padding:10px 0; cursor:pointer; overflow-wrap:anywhere; }
    summary small { color:var(--f1-muted); }
    section { border-top:1px solid var(--f1-divider); padding:12px 0; }
    h3 { font-size:1em; margin:0; }
    p { margin:8px 0; }
    form,.buttons { display:flex; align-items:end; flex-wrap:wrap; gap:8px; }
    label { display:flex; flex-direction:column; gap:4px; }
    input { width:8em; max-width:100%; min-height:44px; border:1px solid var(--f1-border); border-radius:8px; padding:8px; color:var(--f1-text); background:var(--f1-surface); font:inherit; }
    .calibration { margin-top:16px; }
    .calibration select { width:100%; min-height:44px; border:1px solid var(--f1-border); border-radius:8px; padding:8px; background:var(--f1-surface); color:var(--f1-text); }
    .calibration-body { padding:8px 0 14px; }
    .calibration-reading { display:flex; align-items:baseline; flex-wrap:wrap; justify-content:space-between; gap:8px; background:var(--f1-panel); padding:12px; border-radius:8px; }
    .calibration-reading strong { font-size:1.7rem; font-variant-numeric:tabular-nums; }
    button[data-command=cal-match] { border-width:2px; font-weight:700; }
    .confirmation { padding:12px; border:1px solid currentColor; border-radius:8px; }
  `];
  constructor() { super(); this.draft = null; this.draftContext = ''; this.confirmation = ''; }
  w(en, sv) { return words(this.settings?.language, en, sv); }
  willUpdate(changed) {
    const active = this.shadowRoot?.activeElement, calibration = this.model?.calibration;
    if (!this.focusTarget && !this.request?.pending && active?.dataset?.command === 'calibration-region') this.focusTarget = this.request?.action === 'calibration_reference' ? 'cal-reference' : this.calibrationFocus();
    const calAction = ({ 'cal-reference': 'reference', 'cal-start': 'start', 'cal-match': 'match', 'cal-cancel': 'cancel' })[active?.dataset?.command];
    if (!this.focusTarget && calibration && calAction && !calibration.allowed[calAction]) this.focusTarget = this.calibrationFocus();
    if (!this.focusTarget && !this.request?.pending && active?.dataset?.command === 'delay-region') this.focusTarget = 'delay';
    if (!this.focusTarget && !this.request?.pending && active?.dataset?.command === 'protection') this.focusTarget = this.model?.spoilers.protection === 'protected' ? 'review' : this.model?.spoilers.protection === 'clear' ? 'protect' : 'summary';
    if (!this.focusTarget && ['protect', 'reveal', 'review', 'cancel', 'protection'].includes(active?.dataset?.command) && changed.has('model') && changed.get('model')?.spoilers.protection !== this.model?.spoilers.protection) this.focusTarget = this.model?.spoilers.protection === 'protected' ? 'review' : this.model?.spoilers.protection === 'clear' ? 'protect' : 'summary';
    if (changed.has('connection') || changed.has('model') && changed.get('model')?.entryId !== this.model?.entryId || this.readonly || !this.model?.online) this.reset();
    if (this.confirmation && this.confirmation !== this.model?.spoilers.context) this.confirmation = '';
    if (this.draft !== null && this.draft !== '' && Number(this.draft) === this.model?.delay.seconds && this.request?.action === 'delay' && !this.request.error) this.reset();
  }
  updated() {
    if (!this.focusTarget) return;
    const target = this.focusTarget; this.focusTarget = '';
    if (this.shadowRoot.querySelector('details')?.open) this.shadowRoot.querySelector(target === 'summary' ? 'summary' : `[data-command="${target}"]`)?.focus({ preventScroll: true });
  }
  calibrationFocus() { const allowed = this.model?.calibration?.allowed ?? {}; return allowed.match ? 'cal-match' : allowed.cancel ? 'cal-cancel' : allowed.start ? 'cal-start' : 'cal-summary'; }
  reset() { this.draft = null; this.draftContext = ''; this.confirmation = ''; }
  send(action, value, context) {
    if (this.readonly || this.request?.pending || !this.isConnected) return;
    if (action === 'reveal' && this.confirmation !== context) return;
    this.shadowRoot.querySelector(`[data-command="${action.startsWith('calibration_') ? 'calibration-region' : action === 'delay' ? 'delay-region' : 'protection'}"]`)?.focus({ preventScroll: true });
    this.dispatchEvent(new CustomEvent('f1-viewing-action', { bubbles: true, composed: true, detail: { action, value, context, connection: this.connection } }));
  }
  reason(reason) {
    return ({ offline: this.w('Disconnected. Reconnect to change viewing settings.', 'Frånkopplad. Anslut igen för att ändra visningsinställningar.'),
      missing: this.w('Live Delay control is unavailable. Check the integration’s System device.', 'Live Delay-kontrollen saknas. Kontrollera integrationens System-enhet.'),
      replay: this.w('Replay uses its own playback clock. Live Delay does not delay replay; stop replay before changing the saved live delay.', 'Replay använder sin egen uppspelningsklocka. Live Delay fördröjer inte replay; stoppa replay innan du ändrar den sparade livefördröjningen.'),
      unknown_replay: this.w('Replay status is unknown. Live Delay controls will return when its state is available.', 'Replaystatus är okänd. Live Delay-kontroller återkommer när status är tillgänglig.'),
      calibrating: this.w('Calibration is active. Finish or cancel it below before setting a manual delay.', 'Kalibrering pågår. Slutför eller avbryt den nedan innan du ställer in fördröjningen manuellt.'),
      unknown_calibration: this.w('Calibration status is unavailable. Check the integration’s System device.', 'Kalibreringsstatus saknas. Kontrollera integrationens System-enhet.'),
    })[reason] ?? '';
  }
  calibrationStatus(calibration) {
    if (calibration.mode === 'waiting') return calibration.reference.kind === 'lap_sync' ? this.w('Waiting for the next completed lap', 'Väntar på nästa avslutade varv') : this.w('Waiting for the session to go live', 'Väntar på att sessionen ska starta');
    if (calibration.mode === 'running') return this.w('Measuring TV delay', 'Mäter TV-fördröjning');
    if (calibration.mode === 'unknown') return this.w('Calibration status unavailable', 'Kalibreringsstatus saknas');
    return ({ completed: this.w('Calibration saved', 'Kalibreringen sparad'), cancelled: this.w('Calibration cancelled; delay unchanged', 'Kalibreringen avbruten; fördröjningen oförändrad'), timeout: this.w('Calibration timed out; delay unchanged', 'Tiden för kalibrering gick ut; fördröjningen oförändrad'), session_ended: this.w('Session ended; calibration stopped without saving', 'Sessionen avslutades; kalibreringen stoppades utan att sparas'), replay: this.w('Calibration stopped because replay was selected', 'Kalibreringen stoppades eftersom replay valdes'), unsupported_session: this.w('Lap sync needs a race or sprint session', 'Varvsynk kräver race eller sprint') })[calibration.outcome] ?? this.w('Ready to calibrate', 'Redo att kalibrera');
  }
  calibrationView() {
    const cal = this.model?.calibration;
    if (!cal) return '';
    const disabled = this.readonly || this.request?.pending;
    const optionLabel = option => option === 'Session live' ? this.w('Session live', 'Sessionsstart') : this.w('Lap sync (race/sprint)', 'Varvsynk (race/sprint)');
    const reason = ({ offline: this.w('Reconnect to control calibration.', 'Anslut igen för att styra kalibreringen.'), missing: this.w('Calibration controls are unavailable. Check the integration’s System device.', 'Kalibreringskontrollerna saknas. Kontrollera integrationens System-enhet.'), replay: this.w('Stop and clear the selected replay before calibrating a live broadcast.', 'Stoppa och rensa vald replay innan du kalibrerar en livesändning.'), protected: this.w('Global spoiler protection stops live delivery. Review that setting before starting calibration.', 'Globalt spoilerskydd stoppar liveleveransen. Granska den inställningen innan du startar kalibrering.'), reference: this.w('Choose an available reference and wait for it to be confirmed.', 'Välj en tillgänglig referens och vänta på att den bekräftas.'), lap_session: this.w('Lap sync can start during an active race or sprint. Session start can be armed beforehand.', 'Varvsynk kan startas under ett aktivt race eller sprint. Sessionsstart kan förberedas i förväg.') })[cal.reason];
    return html`<details class="calibration"><summary data-command="cal-summary">${this.w('Calibrate with TV', 'Kalibrera mot TV')} · ${this.calibrationStatus(cal)}</summary>
      <div class="calibration-body" data-command="calibration-region" tabindex="-1" role="group" aria-label=${this.w('Guided TV calibration', 'Guidad TV-kalibrering')}>
        <p>${this.w('Choose a reference, start calibration, then match that moment on your TV. Matching saves the measured delay for this installation and its automations.', 'Välj en referens, starta kalibreringen och matcha sedan det ögonblicket på TV:n. Matchningen sparar den uppmätta fördröjningen för denna installation och dess automationer.')}</p>
        <label>${this.w('Calibration reference', 'Kalibreringsreferens')}<select data-command="cal-reference" .value=${cal.reference.option} ?disabled=${disabled || !cal.allowed.reference} @change=${event => { const value = event.target.value; event.target.value = cal.reference.option; this.send('calibration_reference', value, cal.context); }}>
          ${cal.reference.option ? '' : html`<option value="" disabled>${this.w('Choose reference…', 'Välj referens…')}</option>`}${cal.reference.options.map(option => html`<option value=${option}>${optionLabel(option)}</option>`)}
        </select></label>
        ${cal.reference.kind === 'session_live' ? html`<p class="muted">${this.w('Match lights out in a race or pit exit opening in practice or qualifying. If the session is already live, measurement starts when you arm it; use lap sync if you missed the start.', 'Matcha när startlamporna slocknar i race eller när depåutfarten öppnas i träning eller kval. Om sessionen redan är igång börjar mätningen när du aktiverar den; använd varvsynk om du missade starten.')}</p>` : ''}
        ${reason ? html`<p>${reason}</p>` : ''}
        <p aria-live=${this.settings?.accessibility?.announce ? 'polite' : 'off'} aria-atomic="true">${this.calibrationStatus(cal)}</p>
        ${cal.detailsHidden && cal.mode === 'running' ? html`<p>${this.w('Reference details are hidden by spoiler protection in this card. Matching is unavailable here; you can still cancel calibration.', 'Referensdetaljer döljs av spoilerskyddet i detta kort. Matchning är inte tillgänglig här; du kan fortfarande avbryta kalibreringen.')}</p>` : ''}
        ${cal.recordedLap !== null ? html`<p><strong>${cal.recordedLap === 0 ? this.w('Start of lap 1', 'Start av varv 1') : this.w(`Lap ${cal.recordedLap} completed`, `Varv ${cal.recordedLap} avslutat`)}</strong> · ${this.w(`Match when the TV lap counter changes to ${cal.recordedLap + 1}.`, `Matcha när TV:ns varvräknare växlar till ${cal.recordedLap + 1}.`)}</p>` : ''}
        ${cal.elapsed !== null ? html`<p class="calibration-reading"><span>${this.w('Measured delay', 'Uppmätt fördröjning')}</span><strong>${cal.elapsed.toLocaleString(this.settings?.language, { maximumFractionDigits: 1 })} s</strong></p>` : ''}
        <div class="buttons">${['waiting', 'running'].includes(cal.mode) ? html`<button data-command="cal-match" ?disabled=${disabled || !cal.allowed.match} @click=${() => this.send('calibration_match', null, cal.context)}>${this.w('Match TV and save delay', 'Matcha TV och spara fördröjning')}</button>` : html`<button data-command="cal-start" ?disabled=${disabled || !cal.allowed.start} @click=${() => this.send('calibration_start', null, cal.context)}>${this.w('Start calibration', 'Starta kalibrering')}</button>`}
          <button data-command="cal-cancel" ?disabled=${disabled || !cal.allowed.cancel} @click=${() => this.send('calibration_cancel', null, cal.context)}>${this.w('Cancel calibration', 'Avbryt kalibrering')}</button></div>
        ${cal.lastResult ? html`<p class="muted">${this.w('Last calibration', 'Senaste kalibrering')}: ${cal.lastResult.seconds} s · ${dateTime(cal.lastResult.completedAt, this.settings, { dateStyle: 'medium', timeStyle: 'short' })}</p>` : ''}
      </div></details>`;
  }
  render() {
    if (!this.model) return html``;
    const { delay, spoilers } = this.model, pending = this.request?.pending, disabled = this.readonly || pending;
    const stale = this.draft !== null && this.draftContext !== delay.context;
    const value = this.draft ?? (delay.seconds === null ? '' : String(delay.seconds));
    const protection = spoilers.protection === 'protected' ? this.w('Global protection on', 'Globalt skydd på') : spoilers.protection === 'clear' ? this.w('Global protection off', 'Globalt skydd av') : this.w('Global protection unknown', 'Globalt skydd okänt');
    return html`<details @toggle=${event => { if (!event.target.open) this.confirmation = ''; }}><summary>${this.w('Viewing settings', 'Visningsinställningar')} <small>· ${delay.seconds === null ? this.w('Live Delay unknown', 'Live Delay okänd') : `${this.w('Saved Live Delay', 'Sparad Live Delay')} ${delay.seconds} s`} · ${protection}${['waiting', 'running'].includes(this.model.calibration?.mode) ? ` · ${this.calibrationStatus(this.model.calibration)}` : ''}</small></summary>
      ${this.readonly ? html`<p class="muted">${this.w('Read only in a preview or frozen view. No integration settings can be changed here.', 'Skrivskyddat i förhandsvisning eller fryst vy. Inga integrationsinställningar kan ändras här.')}</p>` : ''}
      <section data-command="delay-region" tabindex="-1" aria-label="Live Delay"><h3>Live Delay · ${this.model.scope}</h3><p>${this.w('Changes live delivery for this entire installation, including other cards and automations. It does not delay season results or standings.', 'Ändrar liveleveransen för hela denna installation, inklusive andra kort och automationer. Säsongsresultat och mästerskapsställning fördröjs inte.')}</p>
        <p class="muted">${this.w('Saved value', 'Sparat värde')}: ${delay.seconds ?? '—'} s</p>
        ${delay.reason ? html`<p>${this.reason(delay.reason)}</p>` : ''}
        <form @submit=${event => { event.preventDefault(); if (!stale && !delay.reason) this.send('delay', value, this.draftContext || delay.context); }}>
          <label>${this.w('Delay in seconds', 'Fördröjning i sekunder')}<input data-command="delay" type="number" required min=${delay.min ?? 0} max=${delay.max ?? 300} step=${delay.step ?? 1} .value=${value} ?disabled=${disabled || Boolean(delay.reason)} @input=${event => { if (this.draft === null) this.draftContext = delay.context; this.draft = event.target.value; }}></label>
          <button type="submit" ?disabled=${disabled || Boolean(delay.reason) || stale || value === '' || Number(value) === delay.seconds}>${this.w('Apply live delay', 'Använd livefördröjning')}</button>
          ${this.draft !== null ? html`<button type="button" ?disabled=${pending} @click=${() => { this.reset(); this.focusTarget = 'delay'; }}>${this.w('Use current value', 'Använd aktuellt värde')}</button>` : ''}
        </form>
        ${stale ? html`<p role="status">${this.w('Settings changed elsewhere. Use the current value before editing again.', 'Inställningarna ändrades på annat håll. Använd aktuellt värde innan du redigerar igen.')}</p>` : ''}
        ${this.calibrationView()}
      </section>
      <section data-command="protection" tabindex="-1" aria-label=${this.w('Global spoiler protection', 'Globalt spoilerskydd')}><h3>${this.w('Global spoiler protection', 'Globalt spoilerskydd')}</h3>
        <p>${this.w('Affects every F1 Sensor installation, dashboard and automation. Enable before the session to hold new spoiler-sensitive updates. This does not record the session.', 'Påverkar alla F1 Sensor-installationer, dashboards och automationer. Aktivera före sessionen för att hålla tillbaka nya spoilerkänsliga uppdateringar. Sessionen spelas inte in.')}</p>
        <p>${protection}</p>
        ${this.localHidden ? html`<p>${this.w('This card also hides spoilers locally. Turning global protection off will not reveal them in this card.', 'Detta kort döljer också spoilers lokalt. När globalt skydd stängs av förblir de dolda i detta kort.')}</p>` : ''}
        ${spoilers.protection === 'unknown' ? html`<p>${this.w('Protection cannot be verified. Check the global No Spoiler Mode switch on the System device.', 'Skyddet kan inte verifieras. Kontrollera den globala No Spoiler Mode-knappen på System-enheten.')}</p>` : spoilers.protection === 'clear'
          ? html`<button data-command="protect" ?disabled=${disabled || !spoilers.available} @click=${() => this.send('protect', null, spoilers.context)}>${this.w('Enable global protection', 'Aktivera globalt skydd')}</button>`
          : this.confirmation ? html`<div class="confirmation"><p>${this.w('Turning protection off requests current results and may resume live delivery for all F1 installations. Continue when you are ready to reveal them everywhere.', 'När skyddet stängs av hämtas aktuella resultat och liveleverans kan återupptas för alla F1-installationer. Fortsätt när du är redo att visa dem överallt.')}</p><div class="buttons"><button data-command="reveal" ?disabled=${disabled || !spoilers.available} @click=${() => this.send('reveal', null, this.confirmation)}>${this.w('Turn off protection for all F1 installations', 'Stäng av skyddet för alla F1-installationer')}</button><button data-command="cancel" ?disabled=${pending} @click=${() => { this.confirmation = ''; this.focusTarget = 'review'; }}>${this.w('Cancel', 'Avbryt')}</button></div></div>`
            : html`<button data-command="review" ?disabled=${disabled || !spoilers.available} @click=${() => { this.confirmation = spoilers.context; this.focusTarget = 'reveal'; }}>${this.w('Review turning protection off', 'Granska avstängning av skydd')}</button>`}
      </section>
      <div aria-live=${this.settings?.accessibility?.announce ? 'polite' : 'off'} aria-atomic="true">${pending ? html`<p>${this.w('Applying viewing setting…', 'Tillämpar visningsinställning…')}</p>` : this.request?.error ? html`<p>${this.w('The change could not be completed. The displayed state comes from Home Assistant. Check it before trying again.', 'Ändringen kunde inte slutföras. Visad status kommer från Home Assistant. Kontrollera den innan du försöker igen.')}</p>` : this.request?.busy ? html`<p>${this.w('Another card is changing this setting. Wait for its state to update.', 'Ett annat kort ändrar denna inställning. Vänta på uppdaterad status.')}</p>` : ''}</div>
    </details>`;
  }
}
if (!customElements.get('f1-viewing-controls')) customElements.define('f1-viewing-controls', F1ViewingControls);
