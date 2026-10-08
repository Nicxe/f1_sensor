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
    return ({ offline: this.w('modular.disconnected_reconnect_to_change_viewing_settings'),
      missing: this.w('modular.live_delay_control_is_unavailable_check_the_integration_s_system_device'),
      replay: this.w('modular.replay_uses_its_own_playback_clock_live_delay_does_not_delay_replay_stop_replay'),
      unknown_replay: this.w('modular.replay_status_is_unknown_live_delay_controls_will_return_when_its_state_is_available'),
      calibrating: this.w('modular.calibration_is_active_finish_or_cancel_it_below_before_setting_a_manual_delay'),
      unknown_calibration: this.w('modular.calibration_status_is_unavailable_check_the_integration_s_system_device'),
    })[reason] ?? '';
  }
  calibrationStatus(calibration) {
    if (calibration.mode === 'waiting') return calibration.reference.kind === 'lap_sync' ? this.w('modular.waiting_for_the_next_completed_lap') : this.w('modular.waiting_for_the_session_to_go_live');
    if (calibration.mode === 'running') return this.w('modular.measuring_tv_delay');
    if (calibration.mode === 'unknown') return this.w('modular.calibration_status_unavailable');
    return ({ completed: this.w('modular.calibration_saved'), cancelled: this.w('modular.calibration_cancelled_delay_unchanged'), timeout: this.w('modular.calibration_timed_out_delay_unchanged'), session_ended: this.w('modular.session_ended_calibration_stopped_without_saving'), replay: this.w('modular.calibration_stopped_because_replay_was_selected'), unsupported_session: this.w('modular.lap_sync_needs_a_race_or_sprint_session') })[calibration.outcome] ?? this.w('modular.ready_to_calibrate');
  }
  calibrationView() {
    const cal = this.model?.calibration;
    if (!cal) return '';
    const disabled = this.readonly || this.request?.pending;
    const optionLabel = option => option === 'Session live' ? this.w('modular.session_live') : this.w('modular.lap_sync_race_sprint');
    const reason = ({ offline: this.w('modular.reconnect_to_control_calibration'), missing: this.w('modular.calibration_controls_are_unavailable_check_the_integration_s_system_device'), replay: this.w('modular.stop_and_clear_the_selected_replay_before_calibrating_a_live_broadcast'), protected: this.w('modular.global_spoiler_protection_stops_live_delivery_review_that_setting_before_starting_calibration'), reference: this.w('modular.choose_an_available_reference_and_wait_for_it_to_be_confirmed'), lap_session: this.w('modular.lap_sync_can_start_during_an_active_race_or_sprint_session_start_can_be') })[cal.reason];
    return html`<details class="calibration"><summary data-command="cal-summary">${this.w('modular.calibrate_with_tv')} · ${this.calibrationStatus(cal)}</summary>
      <div class="calibration-body" data-command="calibration-region" tabindex="-1" role="group" aria-label=${this.w('modular.guided_tv_calibration')}>
        <p>${this.w('modular.choose_a_reference_start_calibration_then_match_that_moment_on_your_tv_matching_saves')}</p>
        <label>${this.w('modular.calibration_reference')}<select data-command="cal-reference" .value=${cal.reference.option} ?disabled=${disabled || !cal.allowed.reference} @change=${event => { const value = event.target.value; event.target.value = cal.reference.option; this.send('calibration_reference', value, cal.context); }}>
          ${cal.reference.option ? '' : html`<option value="" disabled>${this.w('modular.choose_reference')}</option>`}${cal.reference.options.map(option => html`<option value=${option}>${optionLabel(option)}</option>`)}
        </select></label>
        ${cal.reference.kind === 'session_live' ? html`<p class="muted">${this.w('modular.match_lights_out_in_a_race_or_pit_exit_opening_in_practice_or_qualifying')}</p>` : ''}
        ${reason ? html`<p>${reason}</p>` : ''}
        <p aria-live=${this.settings?.accessibility?.announce ? 'polite' : 'off'} aria-atomic="true">${this.calibrationStatus(cal)}</p>
        ${cal.detailsHidden && cal.mode === 'running' ? html`<p>${this.w('modular.reference_details_are_hidden_by_spoiler_protection_in_this_card_matching_is_unavailable_here')}</p>` : ''}
        ${cal.recordedLap !== null ? html`<p><strong>${cal.recordedLap === 0 ? this.w('modular.start_of_lap_1') : this.w('modular.lap_recordedlap_completed', { recordedLap: cal.recordedLap })}</strong> · ${this.w('modular.match_when_the_tv_lap_counter_changes_to_value', { value: cal.recordedLap + 1 })}</p>` : ''}
        ${cal.elapsed !== null ? html`<p class="calibration-reading"><span>${this.w('modular.measured_delay')}</span><strong>${cal.elapsed.toLocaleString(this.settings?.language, { maximumFractionDigits: 1 })} s</strong></p>` : ''}
        <div class="buttons">${['waiting', 'running'].includes(cal.mode) ? html`<button data-command="cal-match" ?disabled=${disabled || !cal.allowed.match} @click=${() => this.send('calibration_match', null, cal.context)}>${this.w('modular.match_tv_and_save_delay')}</button>` : html`<button data-command="cal-start" ?disabled=${disabled || !cal.allowed.start} @click=${() => this.send('calibration_start', null, cal.context)}>${this.w('modular.start_calibration')}</button>`}
          <button data-command="cal-cancel" ?disabled=${disabled || !cal.allowed.cancel} @click=${() => this.send('calibration_cancel', null, cal.context)}>${this.w('modular.cancel_calibration')}</button></div>
        ${cal.lastResult ? html`<p class="muted">${this.w('modular.last_calibration')}: ${cal.lastResult.seconds} s · ${dateTime(cal.lastResult.completedAt, this.settings, { dateStyle: 'medium', timeStyle: 'short' })}</p>` : ''}
      </div></details>`;
  }
  render() {
    if (!this.model) return html``;
    const { delay, spoilers } = this.model, pending = this.request?.pending, disabled = this.readonly || pending;
    const stale = this.draft !== null && this.draftContext !== delay.context;
    const value = this.draft ?? (delay.seconds === null ? '' : String(delay.seconds));
    const protection = spoilers.protection === 'protected' ? this.w('modular.global_protection_on') : spoilers.protection === 'clear' ? this.w('modular.global_protection_off') : this.w('modular.global_protection_unknown');
    return html`<details @toggle=${event => { if (!event.target.open) this.confirmation = ''; }}><summary>${this.w('modular.viewing_settings')} <small>· ${delay.seconds === null ? this.w('modular.live_delay_unknown') : `${this.w('modular.saved_live_delay')} ${delay.seconds} s`} · ${protection}${['waiting', 'running'].includes(this.model.calibration?.mode) ? ` · ${this.calibrationStatus(this.model.calibration)}` : ''}</small></summary>
      ${this.readonly ? html`<p class="muted">${this.w('modular.read_only_in_a_preview_or_frozen_view_no_integration_settings_can_be_changed')}</p>` : ''}
      <section data-command="delay-region" tabindex="-1" aria-label="Live Delay"><h3>Live Delay · ${this.model.scope}</h3><p>${this.w('modular.changes_live_delivery_for_this_entire_installation_including_other_cards_and_automations_it_does')}</p>
        <p class="muted">${this.w('modular.saved_value')}: ${delay.seconds ?? '—'} s</p>
        ${delay.reason ? html`<p>${this.reason(delay.reason)}</p>` : ''}
        <form @submit=${event => { event.preventDefault(); if (!stale && !delay.reason) this.send('delay', value, this.draftContext || delay.context); }}>
          <label>${this.w('modular.delay_in_seconds')}<input data-command="delay" type="number" required min=${delay.min ?? 0} max=${delay.max ?? 300} step=${delay.step ?? 1} .value=${value} ?disabled=${disabled || Boolean(delay.reason)} @input=${event => { if (this.draft === null) this.draftContext = delay.context; this.draft = event.target.value; }}></label>
          <button type="submit" ?disabled=${disabled || Boolean(delay.reason) || stale || value === '' || Number(value) === delay.seconds}>${this.w('modular.apply_live_delay')}</button>
          ${this.draft !== null ? html`<button type="button" ?disabled=${pending} @click=${() => { this.reset(); this.focusTarget = 'delay'; }}>${this.w('modular.use_current_value')}</button>` : ''}
        </form>
        ${stale ? html`<p role="status">${this.w('modular.settings_changed_elsewhere_use_the_current_value_before_editing_again')}</p>` : ''}
        ${this.calibrationView()}
      </section>
      <section data-command="protection" tabindex="-1" aria-label=${this.w('modular.global_spoiler_protection')}><h3>${this.w('modular.global_spoiler_protection')}</h3>
        <p>${this.w('modular.affects_every_f1_sensor_installation_dashboard_and_automation_enable_before_the_session_to_hold')}</p>
        <p>${protection}</p>
        ${this.localHidden ? html`<p>${this.w('modular.this_card_also_hides_spoilers_locally_turning_global_protection_off_will_not_reveal_them')}</p>` : ''}
        ${spoilers.protection === 'unknown' ? html`<p>${this.w('modular.protection_cannot_be_verified_check_the_global_no_spoiler_mode_switch_on_the_system')}</p>` : spoilers.protection === 'clear'
          ? html`<button data-command="protect" ?disabled=${disabled || !spoilers.available} @click=${() => this.send('protect', null, spoilers.context)}>${this.w('modular.enable_global_protection')}</button>`
          : this.confirmation ? html`<div class="confirmation"><p>${this.w('modular.turning_protection_off_requests_current_results_and_may_resume_live_delivery_for_all_f1')}</p><div class="buttons"><button data-command="reveal" ?disabled=${disabled || !spoilers.available} @click=${() => this.send('reveal', null, this.confirmation)}>${this.w('modular.turn_off_protection_for_all_f1_installations')}</button><button data-command="cancel" ?disabled=${pending} @click=${() => { this.confirmation = ''; this.focusTarget = 'review'; }}>${this.w('modular.cancel')}</button></div></div>`
            : html`<button data-command="review" ?disabled=${disabled || !spoilers.available} @click=${() => { this.confirmation = spoilers.context; this.focusTarget = 'reveal'; }}>${this.w('modular.review_turning_protection_off')}</button>`}
      </section>
      <div aria-live=${this.settings?.accessibility?.announce ? 'polite' : 'off'} aria-atomic="true">${pending ? html`<p>${this.w('modular.applying_viewing_setting')}</p>` : this.request?.error ? html`<p>${this.w('modular.the_change_could_not_be_completed_the_displayed_state_comes_from_home_assistant_check')}</p>` : this.request?.busy ? html`<p>${this.w('modular.another_card_is_changing_this_setting_wait_for_its_state_to_update')}</p>` : ''}</div>
    </details>`;
  }
}
if (!customElements.get('f1-viewing-controls')) customElements.define('f1-viewing-controls', F1ViewingControls);
