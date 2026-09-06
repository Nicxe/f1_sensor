const STORAGE_KEY = 'f1-sensor-dashboard-context-v1';
const STORE_KEY = '__f1SensorDashboardContextStore';

export const normalizeF1SessionContext = (value) => {
  const text = String(value || '').trim();
  if (!text) return null;
  const lower = text.toLowerCase();
  const kind = lower.includes('sprint') ? 'sprint' : lower.includes('race') ? 'race' : null;
  const numbers = text.match(/\d+/g) || [];
  return kind && numbers.length ? `${kind}:${numbers.at(-1)}` : text;
};

export const f1SessionContextMatches = (candidate, selected) => (
  normalizeF1SessionContext(candidate) === normalizeF1SessionContext(selected)
);

export const DEFAULT_F1_DASHBOARD_CONTEXT = Object.freeze({
  entry_id: null,
  session_id: null,
  driver_number: null,
  spoiler_mode: false,
  gap_mode: 'ahead',
});

const normalize = (candidate = {}) => {
  const driver = Number.parseInt(candidate.driver_number, 10);
  const gap = String(candidate.gap_mode || 'ahead').toLowerCase();
  return {
    entry_id: String(candidate.entry_id || '').trim() || null,
    session_id: normalizeF1SessionContext(candidate.session_id),
    driver_number: Number.isFinite(driver) && driver > 0 && driver < 100 ? driver : null,
    spoiler_mode: candidate.spoiler_mode === true,
    gap_mode: ['ahead', 'leader', 'off'].includes(gap) ? gap : 'ahead',
  };
};

const readStored = () => {
  try {
    return normalize(JSON.parse(window.localStorage?.getItem(STORAGE_KEY) || '{}'));
  } catch (_err) {
    return { ...DEFAULT_F1_DASHBOARD_CONTEXT };
  }
};

const createStore = () => {
  let value = readStored();
  const listeners = new Set();
  return {
    get value() {
      return { ...value };
    },
    update(patch = {}, source = null) {
      const next = normalize({ ...value, ...patch });
      if (JSON.stringify(next) === JSON.stringify(value)) return { ...value };
      value = next;
      try {
        window.localStorage?.setItem(STORAGE_KEY, JSON.stringify(value));
      } catch (_err) {
        // Private browsing or a full storage quota must not break dashboard cards.
      }
      listeners.forEach((listener) => listener({ ...value }, source));
      window.dispatchEvent(new CustomEvent('f1-dashboard-context-changed', {
        detail: { value: { ...value }, source },
      }));
      return { ...value };
    },
    subscribe(listener) {
      listeners.add(listener);
      listener({ ...value }, 'initial');
      return () => listeners.delete(listener);
    },
  };
};

export const getF1DashboardContextStore = () => {
  if (!window[STORE_KEY]) window[STORE_KEY] = createStore();
  return window[STORE_KEY];
};

export const getF1DashboardContext = () => getF1DashboardContextStore().value;

export const updateF1DashboardContext = (patch, source = null) => (
  getF1DashboardContextStore().update(patch, source)
);

export const installF1DashboardContext = (CardClass) => {
  if (!CardClass?.prototype || CardClass.prototype.__f1DashboardContextInstalled) return;
  const connected = CardClass.prototype.connectedCallback;
  const disconnected = CardClass.prototype.disconnectedCallback;

  CardClass.prototype.connectedCallback = function f1ContextConnected(...args) {
    const result = connected?.apply(this, args);
    if (!this.__f1DashboardContextUnsubscribe) {
      this.__f1DashboardContextUnsubscribe = getF1DashboardContextStore().subscribe(
        (context) => {
          this._f1DashboardContext = context;
          this.requestUpdate?.();
        },
      );
    }
    return result;
  };

  CardClass.prototype.disconnectedCallback = function f1ContextDisconnected(...args) {
    this.__f1DashboardContextUnsubscribe?.();
    this.__f1DashboardContextUnsubscribe = null;
    return disconnected?.apply(this, args);
  };

  Object.defineProperty(CardClass.prototype, '__f1DashboardContextInstalled', {
    value: true,
  });
};
