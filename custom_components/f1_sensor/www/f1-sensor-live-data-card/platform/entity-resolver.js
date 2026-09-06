const entityMapRequests = new WeakMap();

const requestKey = (hass) => hass?.connection || hass;

const loadEntries = async (hass) => {
  if (!hass?.callWS) return [];
  const key = requestKey(hass);
  if (!entityMapRequests.has(key)) {
    entityMapRequests.set(
      key,
      hass.callWS({ type: 'f1_sensor/entities' }).catch((error) => {
        entityMapRequests.delete(key);
        throw error;
      }),
    );
  }
  const entries = await entityMapRequests.get(key);
  return Array.isArray(entries) ? entries : [];
};

const suffixesFor = (suffixValue, config) => {
  const configuredSuffix = typeof suffixValue === 'function'
    ? suffixValue(config)
    : suffixValue;
  return Array.isArray(configuredSuffix) ? configuredSuffix : [configuredSuffix];
};

const configuredEntityIds = (config, bindings, includeDefaults) => Object.entries(bindings)
  .map(([field, suffixValue]) => ({
    value: config?.[field],
    suffixes: suffixesFor(suffixValue, config),
  }))
  .filter(({ value, suffixes }) => (
    typeof value === 'string'
    && value.includes('.')
    && value !== 'auto'
    && (includeDefaults || !conventionalDefault(value, suffixes))
  ))
  .map(({ value }) => value);

const selectEntry = (entries, config, bindings) => {
  if (config?.f1_entry_id) {
    return entries.find((entry) => entry.entry_id === config.f1_entry_id) || null;
  }
  for (const includeDefaults of [false, true]) {
    const configured = new Set(configuredEntityIds(config, bindings, includeDefaults));
    const matching = entries.filter((entry) => (
      Object.values(entry.entities || {}).some((entityId) => configured.has(entityId))
    ));
    if (matching.length === 1) return matching[0];
  }
  return entries.length === 1 ? entries[0] : null;
};

const conventionalDefault = (entityId, suffixes) => {
  if (typeof entityId !== 'string') return false;
  return suffixes.some((suffix) => entityId.endsWith(`.f1_${suffix}`));
};

const targetEntity = (entry, suffixes) => {
  for (const suffix of suffixes) {
    if (entry.entities?.[suffix]) return entry.entities[suffix];
  }
  return null;
};

export const resolveF1CardEntities = async (hass, config = {}, bindings = {}) => {
  const entries = await loadEntries(hass);
  const entry = selectEntry(entries, config, bindings);
  if (!entry) return config;

  let changed = config.f1_entry_id !== entry.entry_id;
  const resolved = { ...config, f1_entry_id: entry.entry_id };
  for (const entryField of ['entry_id', 'history_entry_id']) {
    if (entryField in config && (!config[entryField] || config[entryField] === 'auto')) {
      resolved[entryField] = entry.entry_id;
      changed = true;
    }
  }
  for (const [field, suffixValue] of Object.entries(bindings)) {
    const suffixes = suffixesFor(suffixValue, config);
    const target = targetEntity(entry, suffixes);
    if (!target) continue;
    const current = config[field];
    const mayReplace = !current || current === 'auto' || conventionalDefault(current, suffixes);
    if (mayReplace && current !== target) {
      resolved[field] = target;
      changed = true;
    }
  }
  return changed ? resolved : config;
};

export const installF1EntityAutoBinding = (CardClass, bindings) => {
  if (!CardClass || CardClass.prototype.__f1EntityAutoBindingInstalled) return;
  const proto = CardClass.prototype;
  const originalWillUpdate = proto.willUpdate;
  proto.willUpdate = function willUpdate(changedProperties) {
    if (this.hass && this.config && !this.__f1EntityBindingPending) {
      this.__f1EntityBindingPending = true;
      resolveF1CardEntities(this.hass, this.config, bindings)
        .then((resolved) => {
          if (resolved !== this.config) {
            this.config = resolved;
            this.requestUpdate();
          }
        })
        .catch(() => {})
        .finally(() => {
          this.__f1EntityBindingPending = false;
        });
    }
    return originalWillUpdate?.call(this, changedProperties);
  };
  proto.__f1EntityAutoBindingInstalled = true;
};
