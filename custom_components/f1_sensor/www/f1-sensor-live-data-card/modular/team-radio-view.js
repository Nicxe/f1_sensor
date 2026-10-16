const version = new URL(import.meta.url).searchParams.get('v');
const load = path => import(`${path}${version ? `?v=${encodeURIComponent(version)}` : ''}`);
const [{ LitElement, html, css, repeat }, { sharedStyles, dateTime, words }] = await Promise.all([
  load('../f1-lit-3.3.2.js'), load('./view.js'),
]);

let activeAudio = null;

const duration = value => {
  if (!Number.isFinite(value) || value < 0) return '0:00';
  return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`;
};

class F1TeamRadioView extends LitElement {
  static properties = {
    module: { attribute: false }, model: { attribute: false }, settings: { attribute: false },
    unread: { state: true }, activeId: { state: true }, audioRevision: { state: true },
  };

  static styles = [sharedStyles, css`
    :host { display:block; }
    .radio-list { display:grid; gap:16px; margin:0; padding:0; list-style:none; }
    .radio-card {
      --radio-accent:var(--f1-border,#6c7480); position:relative; overflow:hidden;
      border:1px solid var(--f1-border,#6c7480); border-top:4px solid var(--radio-accent);
      border-radius:12px; background:linear-gradient(145deg,#151922 0%,#0d1118 100%); color:#f6f8fb;
      box-shadow:inset 0 1px 0 rgba(255,255,255,.05);
    }
    .radio-card::after { content:""; position:absolute; inset:0; pointer-events:none; background:linear-gradient(110deg,transparent 55%,color-mix(in srgb,var(--radio-accent) 12%,transparent)); }
    .radio-head { position:relative; z-index:1; display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:12px; min-height:96px; padding:15px 16px; border-bottom:1px solid rgba(255,255,255,.14); }
    .number { min-width:2ch; color:var(--radio-accent); font-family:'F1 Barlow Condensed',var(--f1-heading-font,inherit); font-size:clamp(2.8rem,11vw,4.8rem); font-weight:800; line-height:.8; letter-spacing:-.04em; font-variant-numeric:tabular-nums; }
    .identity { min-width:0; text-align:right; text-transform:uppercase; }
    .identity strong,.identity span { display:block; overflow-wrap:anywhere; }
    .identity strong { color:var(--radio-accent); font-family:'F1 Barlow Condensed',var(--f1-heading-font,inherit); font-size:clamp(1.35rem,5vw,2rem); line-height:.95; letter-spacing:.02em; }
    .identity .radio { color:#fff; font-family:'F1 Barlow Condensed',var(--f1-heading-font,inherit); font-size:1.55rem; font-weight:800; line-height:1; }
    .identity .team { margin-top:7px; color:#c7ced9; font-size:.75rem; font-weight:650; letter-spacing:.04em; }
    f1-team-logo { --f1-logo-frame:46px; --f1-logo-image:40px; }
    .new { position:absolute; z-index:2; top:8px; left:8px; padding:3px 8px; border:1px solid currentColor; border-radius:999px; background:#fff; color:#11151c; font-size:.72rem; font-weight:800; text-transform:uppercase; letter-spacing:.05em; animation:radio-pulse 1.6s ease-in-out infinite; }
    .radio-body { position:relative; z-index:1; display:grid; gap:14px; padding:16px; }
    .meta { display:flex; align-items:center; justify-content:space-between; gap:8px 16px; flex-wrap:wrap; color:#c7ced9; font-size:.82rem; }
    .transcript { display:grid; gap:12px; }
    .turn { width:min(88%,38rem); margin:0; overflow-wrap:anywhere; line-height:1.45; }
    .turn[data-speaker=B] { justify-self:end; text-align:right; }
    .turn[data-speaker=unknown] { width:100%; color:#d5dae2; }
    .audio { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:10px; }
    .audio[data-has-audio=false] { grid-template-columns:auto; justify-content:start; }
    .audio-actions { display:flex; align-items:center; gap:7px; }
    .audio button { display:inline-grid; place-items:center; border-color:#e5e9ef; background:rgba(255,255,255,.08); color:#fff; font-weight:750; }
    .audio .transcribe { min-height:36px; padding:6px 9px; border-color:rgba(255,255,255,.42); background:transparent; color:#d6dbe4; font-size:.76rem; font-weight:650; }
    .audio .transcribe:disabled { opacity:.48; }
    .audio input { width:100%; min-width:0; min-height:44px; accent-color:var(--radio-accent); }
    .audio-time { min-width:6.5em; color:#c7ced9; text-align:right; font-size:.78rem; font-variant-numeric:tabular-nums; }
    audio { display:none; }
    .status { color:#c7ced9; font-size:.82rem; }
    .error { color:#ffb4ab; }
    @keyframes radio-pulse { 50% { box-shadow:0 0 0 5px rgba(255,255,255,.12); } }
    @media(max-width:420px) {
      .radio-head { grid-template-columns:auto minmax(0,1fr); }
      .radio-head f1-team-logo { grid-column:2; justify-self:end; }
      .audio { grid-template-columns:auto minmax(0,1fr); }
      .audio-time { grid-column:2; }
    }
    @media(prefers-reduced-motion:reduce) { .new { animation:none; } }
    @media(forced-colors:active) {
      .radio-card,.audio button,.new { forced-color-adjust:auto; border-color:CanvasText!important; background:Canvas!important; color:CanvasText!important; }
      .radio-card { --radio-accent:CanvasText!important; }
      .radio-card::after { display:none; }
      .identity strong,.identity .radio,.identity .team,.number,.meta,.turn,.status,.audio-time { color:CanvasText!important; }
    }
  `];

  constructor() {
    super();
    this.unread = false;
    this.activeId = null;
    this.audioRevision = 0;
    this.progress = new Map();
    this.durations = new Map();
    this.errors = new Map();
  }

  get language() { return this.settings?.language ?? 'en'; }
  w(source, replacements = {}) { return words(this.language, source, replacements); }

  willUpdate() {
    const first = this.model?.clips?.[0]?.id ?? null;
    const context = `${this.module?.id ?? ''}|${this.model?.context?.key ?? ''}|${this.model?.readonly === true}`;
    if (context !== this.radioContext) {
      this.radioContext = context;
      this.observedId = first;
      this.unread = false;
      this.stopAudio();
      this.progress.clear(); this.durations.clear(); this.errors.clear();
      return;
    }
    if (first && this.observedId && first !== this.observedId) {
      this.observedId = first;
      this.unread = this.module?.options?.mark_new_messages === true;
    } else if (first && !this.observedId) this.observedId = first;
    const visible = new Set((this.model?.clips ?? []).map(clip => clip.id));
    if (this.activeId && !visible.has(this.activeId)) this.stopAudio();
  }

  disconnectedCallback() {
    this.stopAudio();
    super.disconnectedCallback();
  }

  stopAudio() {
    if (activeAudio?.owner === this) {
      activeAudio.node.pause();
      activeAudio = null;
    }
    this.activeId = null;
  }

  audioFor(id) { return [...this.shadowRoot.querySelectorAll('audio')].find(node => node.dataset.clip === id); }

  async toggleAudio(clip) {
    if (this.model?.readonly || !clip.clipUrl) return;
    const audio = this.audioFor(clip.id);
    if (!audio) return;
    this.unread = false;
    this.errors.delete(clip.id);
    if (!audio.paused) {
      audio.pause();
      this.activeId = null;
      if (activeAudio?.node === audio) activeAudio = null;
      return;
    }
    if (activeAudio?.node !== audio && activeAudio) {
      const previous = activeAudio;
      previous.node.pause();
      previous.owner.activeId = null;
      previous.owner.audioRevision++;
    }
    activeAudio = { owner: this, node: audio };
    this.activeId = clip.id;
    try { await audio.play(); }
    catch {
      if (activeAudio?.node === audio) activeAudio = null;
      this.activeId = null;
      this.errors.set(clip.id, this.w('modular.team_radio_audio_could_not_be_played'));
      this.audioRevision++;
    }
  }

  updateAudio(clip, audio) {
    this.progress.set(clip.id, Number.isFinite(audio.currentTime) ? audio.currentTime : 0);
    if (Number.isFinite(audio.duration)) this.durations.set(clip.id, audio.duration);
    this.audioRevision++;
  }

  seek(clip, value) {
    const audio = this.audioFor(clip.id), position = Number(value);
    if (audio && Number.isFinite(position)) audio.currentTime = position;
  }

  audioError(clip, audio) {
    if (activeAudio?.node === audio) activeAudio = null;
    if (this.activeId === clip.id) this.activeId = null;
    this.errors.set(clip.id, this.w('modular.team_radio_audio_could_not_be_played'));
    this.audioRevision++;
  }

  audioEnded(clip, audio) {
    if (activeAudio?.node === audio) activeAudio = null;
    if (this.activeId === clip.id) this.activeId = null;
    this.audioRevision++;
  }

  status(clip) {
    const status = String(clip.transcriptionStatus ?? '').toLowerCase();
    if (clip.transcriptionSegments.length || clip.transcriptionText) return this.w('modular.team_radio_transcribed');
    if (['pending', 'running', 'processing'].includes(status)) return this.w('modular.team_radio_transcription_in_progress');
    if (['failed', 'error'].includes(status)) return this.w('modular.team_radio_transcription_failed');
    return this.w('modular.team_radio_not_transcribed');
  }

  transcript(clip) {
    if (!this.module.fields.includes('radio_transcript') || this.module.options.show_transcript === false) return '';
    const rows = clip.transcriptionSegments.length ? clip.transcriptionSegments
      : clip.transcriptionText ? [{ speaker: 'unknown', text: clip.transcriptionText }] : [];
    if (!rows.length) return html`<p class="status">${this.w('modular.team_radio_no_transcript_available')}</p>`;
    return html`<div class="transcript" part="team-radio-transcript">${rows.map(row => html`<p class="turn" data-speaker=${row.speaker} part="team-radio-turn" aria-label=${`${row.speaker === 'A' ? this.w('modular.speaker_a') : row.speaker === 'B' ? this.w('modular.speaker_b') : this.w('modular.unknown_speaker')}: ${row.text}`}>${row.text}</p>`)}</div>`;
  }

  audio(clip) {
    const showAudio = this.module.fields.includes('radio_audio') && this.module.options.show_audio_controls !== false;
    const transcriptionStatus = String(clip.transcriptionStatus ?? '').toLowerCase();
    const complete = transcriptionStatus === 'completed' || Boolean(clip.transcriptionSegments.length || clip.transcriptionText);
    const processing = ['pending', 'running', 'processing'].includes(transcriptionStatus);
    const showTranscribe = this.module.options.show_transcribe_button !== false && clip.isLatest && !complete;
    if (!showAudio && !showTranscribe) return '';
    if (showAudio && !clip.clipUrl && !showTranscribe) return html`<p class="status">${this.w('modular.team_radio_audio_unavailable')}</p>`;
    const current = this.progress.get(clip.id) ?? 0, total = this.durations.get(clip.id) ?? 0;
    const playing = this.activeId === clip.id;
    const pending = this.model.request?.pending === true;
    const transcribeDisabled = this.model.readonly || pending || processing || !this.model.transcription?.ready;
    const transcribeTitle = this.model.transcription?.ready ? '' : this.w('modular.team_radio_select_ai_task_entity');
    return html`<div class="audio" data-has-audio=${String(showAudio && Boolean(clip.clipUrl))} part="team-radio-audio team-radio-controls">
      <div class="audio-actions">
        ${showAudio && clip.clipUrl ? html`<button aria-label=${playing ? this.w('modular.pause_team_radio') : this.w('modular.play_team_radio')} aria-pressed=${String(playing)} ?disabled=${this.model.readonly} @click=${() => this.toggleAudio(clip)}>${playing ? this.w('modular.pause') : this.w('modular.play')}</button>` : ''}
        ${showTranscribe ? html`<button class="transcribe" aria-label=${this.w('modular.transcribe_team_radio')} title=${transcribeTitle} ?disabled=${transcribeDisabled} @click=${() => this.dispatchEvent(new CustomEvent('f1-team-radio-action', { bubbles: true, composed: true, detail: { module: this.module.id, action: 'transcribe', clipId: clip.id } }))}>${pending || processing ? this.w('modular.team_radio_transcribing') : this.w('modular.transcribe')}</button>` : ''}
      </div>
      ${showAudio && clip.clipUrl ? html`
        <input type="range" min="0" max=${total || 0} step="0.1" .value=${String(Math.min(current, total || 0))} aria-label=${this.w('modular.team_radio_playback_position')} ?disabled=${this.model.readonly || !total} @input=${event => this.seek(clip, event.target.value)}>
        <span class="audio-time">${duration(current)} / ${duration(total)}</span>
        ${this.model.readonly ? '' : html`<audio preload="metadata" .src=${clip.clipUrl} data-clip=${clip.id} @timeupdate=${event => this.updateAudio(clip, event.currentTarget)} @durationchange=${event => this.updateAudio(clip, event.currentTarget)} @ended=${event => this.audioEnded(clip, event.currentTarget)} @error=${event => this.audioError(clip, event.currentTarget)}></audio>`}` : ''}
    </div>
    ${showAudio && !clip.clipUrl ? html`<p class="status">${this.w('modular.team_radio_audio_unavailable')}</p>` : ''}
    ${this.errors.get(clip.id) ? html`<p class="status error" role="alert">${this.errors.get(clip.id)}</p>` : ''}
    ${this.model.request?.error || this.model.request?.busy ? html`<p class="status error" role="alert">${this.w('modular.team_radio_transcription_could_not_be_started')}</p>` : ''}`;
  }

  card(clip, index) {
    const accent = this.settings?.appearance?.team_colors !== false && clip.teamColor ? clip.teamColor : 'var(--f1-border,#6c7480)';
    const showLogo = this.module.options.show_team_logo !== false && this.settings?.appearance?.logos !== false && clip.teamName;
    const showIdentity = this.module.fields.includes('radio_driver') || this.module.fields.includes('radio_team');
    return html`<li class="radio-card" part="team-radio-card" style=${`--radio-accent:${accent}`}>
      ${index === 0 && this.unread ? html`<span class="new" part="team-radio-new">${this.w('modular.new_team_radio')}</span>` : ''}
      <div class="radio-head" part="team-radio-header">
        <span class="number">${clip.racingNumber ?? '—'}</span>
        <div class="identity">${showIdentity ? html`
          ${this.module.fields.includes('radio_driver') ? html`<strong>${clip.driverTla ?? clip.driverName ?? clip.racingNumber ?? this.w('modular.unknown_driver')}</strong>` : ''}
          <span class="radio">Radio</span>
          ${this.module.fields.includes('radio_team') && clip.teamName ? html`<span class="team">${clip.teamName}</span>` : ''}` : html`<span class="radio">Radio</span>`}
        </div>
        ${showLogo ? html`<f1-team-logo aria-hidden="true" .team=${clip.teamName} .variant=${this.settings.appearance.logo_style} .mode=${this.settings.mode} .size=${this.settings.appearance.logo_size}></f1-team-logo>` : ''}
      </div>
      <div class="radio-body">
        ${this.module.fields.includes('radio_time') && this.module.options.show_message_time !== false ? html`<div class="meta"><time datetime=${clip.utc ?? ''}>${dateTime(clip.utc, this.settings, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time>${this.module.options.show_transcription_status !== false ? html`<span>${this.status(clip)}</span>` : ''}</div>` : this.module.options.show_transcription_status !== false ? html`<p class="status">${this.status(clip)}</p>` : ''}
        ${this.transcript(clip)}${this.audio(clip)}
      </div>
    </li>`;
  }

  render() {
    const clips = this.model?.clips ?? [];
    if (!clips.length) return html`<div class="empty" part="empty-state"><p>${this.w('modular.team_radio_no_matching_messages')}</p></div>`;
    return html`${this.settings?.accessibility?.announce && this.unread ? html`<span class="sr" role="status">${this.w('modular.new_team_radio')}</span>` : ''}<ol class="radio-list" part="team-radio-list">${repeat(clips, clip => clip.id, (clip, index) => this.card(clip, index))}</ol>`;
  }
}

if (!customElements.get('f1-team-radio-view')) customElements.define('f1-team-radio-view', F1TeamRadioView);
