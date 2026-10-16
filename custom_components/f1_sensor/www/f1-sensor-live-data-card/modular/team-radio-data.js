const version = new URL(import.meta.url).searchParams.get('v');
const { source } = await import(`./data.js${version ? `?v=${encodeURIComponent(version)}` : ''}`);

const MAX_CLIPS = 20;
const MAX_SEGMENTS = 40;
const MAX_TEXT_LENGTH = 4000;

const text = (value, limit = 160) => typeof value === 'string' && value.trim()
  ? value.trim().slice(0, limit)
  : null;
const iso = value => {
  const candidate = text(value, 80);
  return candidate && Number.isFinite(Date.parse(candidate)) ? new Date(candidate).toISOString() : null;
};
const color = value => /^#[0-9a-f]{6}$/i.test(String(value ?? '').trim()) ? String(value).trim() : null;
const clipUrl = value => {
  const candidate = text(value, 1200);
  if (!candidate || !candidate.startsWith('/api/f1_sensor/team-radio/')) return null;
  try {
    const parsed = new URL(candidate, 'https://home-assistant.local');
    return parsed.origin === 'https://home-assistant.local'
      && parsed.pathname.startsWith('/api/f1_sensor/team-radio/') ? `${parsed.pathname}${parsed.search}` : null;
  } catch { return null; }
};

function segments(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, MAX_SEGMENTS).flatMap(segment => {
    if (!segment || typeof segment !== 'object') return [];
    const body = text(segment.text, MAX_TEXT_LENGTH);
    if (!body) return [];
    const rawSpeaker = String(segment.speaker ?? '').trim().toUpperCase();
    return [{ speaker: rawSpeaker === 'A' || rawSpeaker === 'B' ? rawSpeaker : 'unknown', text: body }];
  });
}

function normalizeClip(value) {
  if (!value || typeof value !== 'object') return null;
  const utc = iso(value.utc ?? value.Utc);
  const path = text(value.path ?? value.Path, 1000);
  if (!utc && !path) return null;
  const transcriptSegments = segments(value.transcription_segments);
  return {
    id: `${utc ?? ''}|${path ?? ''}`,
    utc,
    racingNumber: text(value.racing_number ?? value.RacingNumber, 8),
    driverTla: text(value.driver_tla, 8),
    driverName: text(value.driver_name, 120),
    teamName: text(value.team_name, 120),
    teamColor: color(value.team_color),
    path,
    clipUrl: clipUrl(value.clip_url),
    transcriptionStatus: text(value.transcription_status, 40),
    transcriptionText: text(value.transcription_text, MAX_TEXT_LENGTH),
    transcriptionSegments: transcriptSegments,
    transcriptionGeneratedAt: iso(value.transcription_generated_at),
    transcriptionError: text(value.transcription_error, 500),
  };
}

function driverIdentities(hass, entry) {
  const roster = source(hass, entry, 'driver_list');
  const rawDrivers = roster.attributes?.drivers;
  const drivers = Array.isArray(rawDrivers)
    ? rawDrivers
    : rawDrivers && typeof rawDrivers === 'object' ? Object.values(rawDrivers) : [];
  const identities = new Map();
  for (const driver of drivers) {
    if (!driver || typeof driver !== 'object') continue;
    const racingNumber = text(driver.racing_number ?? driver.RacingNumber, 8);
    if (!racingNumber) continue;
    identities.set(racingNumber, {
      driverTla: text(driver.tla ?? driver.Tla, 8),
      driverName: text(driver.name ?? driver.full_name ?? driver.FullName ?? driver.BroadcastName, 120),
      teamName: text(driver.team ?? driver.team_name ?? driver.TeamName, 120),
      teamColor: color(driver.team_color ?? driver.TeamColour ?? driver.TeamColor),
    });
  }
  return { roster, identities };
}

function enrichIdentity(clip, identities) {
  if (!clip) return null;
  const identity = identities.get(clip.racingNumber) ?? {};
  return {
    ...clip,
    driverTla: clip.driverTla ?? identity.driverTla ?? null,
    driverName: clip.driverName ?? identity.driverName ?? null,
    teamName: clip.teamName ?? identity.teamName ?? null,
    teamColor: clip.teamColor ?? identity.teamColor ?? null,
  };
}

const matches = (clip, driver, team) => (!driver || clip.racingNumber === String(driver))
  && (!team || clip.teamName?.localeCompare(String(team), undefined, { sensitivity: 'accent' }) === 0);

export function teamRadioModel(hass, entry, module, focus = {}) {
  const selected = source(hass, entry, 'team_radio');
  const { roster, identities } = driverIdentities(hass, entry);
  const aiTaskEntityId = text(module?.options?.ai_task_entity_id, 255);
  const aiTask = aiTaskEntityId ? hass?.states?.[aiTaskEntityId] : null;
  const attributes = selected.attributes ?? {};
  const latest = enrichIdentity(normalizeClip(attributes), identities);
  const history = Array.isArray(attributes.history) ? attributes.history : [];
  const unique = new Map();
  for (const clip of [latest, ...history.slice(0, MAX_CLIPS).map(value => enrichIdentity(normalizeClip(value), identities))]) {
    if (clip && !unique.has(clip.id)) unique.set(clip.id, clip);
  }
  const driver = module.driver || focus.driver || '';
  const team = module.team || focus.team || '';
  const filtered = [...unique.values()].filter(clip => matches(clip, driver, team));
  const count = module.options.presentation === 'latest_message' ? 1 : module.options.messages_to_show;
  const clips = filtered.slice(0, count).map(clip => ({ ...clip, isLatest: clip.id === latest?.id }));
  return {
    source: selected,
    clips,
    context: {
      key: [entry?.entry_id ?? '', selected.entity_id ?? '', roster.entity_id ?? '', driver, team].join('|'),
      updated: clips[0]?.utc ?? selected.updated_at,
      updatedKind: clips[0]?.utc ? 'source' : 'ha_state',
    },
    focus: { driver: driver || null, team: team || null },
    transcription: {
      entityId: aiTaskEntityId,
      ready: Boolean(aiTaskEntityId?.startsWith('ai_task.') && aiTask && aiTask.state !== 'unavailable'),
    },
  };
}

export function teamRadioCommand(hass, entry, module, clipId) {
  const selected = source(hass, entry, 'team_radio');
  const latest = normalizeClip(selected.attributes);
  const aiTaskEntityId = text(module?.options?.ai_task_entity_id, 255);
  const aiTask = aiTaskEntityId ? hass?.states?.[aiTaskEntityId] : null;
  if (selected.status !== 'available' || latest?.id !== clipId
    || !selected.entity_id?.startsWith('sensor.') || !aiTaskEntityId?.startsWith('ai_task.')
    || !aiTask || aiTask.state === 'unavailable') return null;
  return {
    domain: 'f1_sensor',
    service: 'transcribe_team_radio',
    data: { entity_id: selected.entity_id, ai_task_entity_id: aiTaskEntityId, force: false },
    returnResponse: true,
  };
}
