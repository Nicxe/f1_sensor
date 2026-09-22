const array = value => Array.isArray(value) ? value : [value];

function entityValue(hass, entityId) {
  return typeof entityId === 'string' && hass?.states?.[entityId] ? hass.states[entityId].state : undefined;
}

function comparedValues(value, hass) {
  return array(value).flatMap(item => {
    const dynamic = entityValue(hass, item);
    return dynamic === undefined ? [item] : [item, dynamic];
  }).map(String);
}

function stateMet(condition, hass) {
  const stateObject = hass?.states?.[condition.entity];
  const raw = condition.attribute ? stateObject?.attributes?.[condition.attribute] : stateObject?.state;
  const state = raw == null ? 'unknown' : String(raw);
  if (condition.state !== undefined) return comparedValues(condition.state, hass).includes(state);
  return !comparedValues(condition.state_not, hass).includes(state);
}

function numericMet(condition, hass) {
  const stateObject = hass?.states?.[condition.entity];
  const raw = condition.attribute ? stateObject?.attributes?.[condition.attribute] : stateObject?.state;
  const value = Number(raw);
  if (Number.isNaN(value)) return false;
  const threshold = input => Number(typeof input === 'string' ? entityValue(hass, input) ?? input : input);
  const above = threshold(condition.above), below = threshold(condition.below);
  return (condition.above === undefined || !Number.isNaN(above) && above < value)
    && (condition.below === undefined || !Number.isNaN(below) && below > value);
}

function timezone(hass) {
  const preference = hass?.locale?.time_zone;
  return preference === 'local' ? Intl.DateTimeFormat().resolvedOptions().timeZone
    : preference && preference !== 'server' ? preference : hass?.config?.time_zone ?? 'UTC';
}

function localParts(hass, now) {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone(hass), weekday: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    }).formatToParts(now);
    return Object.fromEntries(parts.map(part => [part.type, part.value]));
  } catch {
    return null;
  }
}

function timeValue(value) {
  const [hour, minute, second = 0] = value.split(':').map(Number);
  return hour * 3600 + minute * 60 + second;
}

function timeMet(condition, hass, now) {
  const parts = localParts(hass, now);
  if (!parts) return false;
  const weekday = String(parts.weekday).slice(0, 3).toLowerCase();
  if (condition.weekdays?.length && !condition.weekdays.includes(weekday)) return false;
  if (!condition.after && !condition.before) return true;
  const current = Number(parts.hour) * 3600 + Number(parts.minute) * 60 + Number(parts.second);
  const after = condition.after ? timeValue(condition.after) : null;
  const before = condition.before ? timeValue(condition.before) : null;
  if (after !== null && before !== null) return before < after ? current >= after || current <= before : current >= after && current <= before;
  if (after !== null) return current >= after;
  return current <= before;
}

function locationMet(condition, hass) {
  const userId = hass?.user?.id;
  if (!userId) return false;
  const person = Object.entries(hass.states ?? {}).find(([entityId, state]) => entityId.startsWith('person.') && state?.attributes?.user_id === userId)?.[1];
  return Boolean(person && condition.locations.includes(person.state));
}

function conditionMet(condition, hass, environment) {
  switch (condition.condition) {
    case 'state': return stateMet(condition, hass);
    case 'numeric_state': return numericMet(condition, hass);
    case 'screen': {
      try { return Boolean(environment.matchMedia(condition.media_query).matches); } catch { return false; }
    }
    case 'user': return Boolean(hass?.user?.id && condition.users.includes(hass.user.id));
    case 'location': return locationMet(condition, hass);
    case 'time': return timeMet(condition, hass, environment.now);
    case 'and': return visibilityMet(condition.conditions, hass, environment);
    case 'or': return condition.conditions.some(item => conditionMet(item, hass, environment));
    case 'not': return !visibilityMet(condition.conditions, hass, environment);
    default: return false;
  }
}

export function visibilityMet(conditions, hass, options = {}) {
  const environment = {
    now: options.now ?? new Date(),
    matchMedia: options.matchMedia ?? (query => globalThis.matchMedia(query)),
  };
  return conditions.every(condition => conditionMet(condition, hass, environment));
}

function collect(conditions, predicate, result) {
  for (const condition of conditions) {
    if (predicate(condition)) result.push(condition);
    if (Array.isArray(condition.conditions)) collect(condition.conditions, predicate, result);
  }
  return result;
}

export const visibilityMediaQueries = conditions => [...new Set(collect(conditions, condition => condition.condition === 'screen', []).map(condition => condition.media_query))];
export const hasTimeVisibility = conditions => collect(conditions, condition => condition.condition === 'time', []).length > 0;
