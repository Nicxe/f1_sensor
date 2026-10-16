const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('experimental Team Radio module presents driver, team, separated dialogue and safe preview controls', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'team_radio' }] } }));
  const radio = page.locator('f1-team-radio-view');

  await expect(page.getByText('Experimental', { exact: true })).toBeVisible();
  await expect(radio).toBeVisible();
  await expect(radio.getByText('LEC', { exact: true })).toBeVisible();
  await expect(radio.getByText('Ferrari', { exact: true })).toBeVisible();
  await expect(radio.locator('.speaker')).toHaveCount(0);
  const turns = radio.locator('[part="team-radio-turn"]');
  await expect(turns).toHaveCount(3);
  const [leftTurn, rightTurn] = await Promise.all([turns.nth(0).boundingBox(), turns.nth(1).boundingBox()]);
  expect(leftTurn.x).toBeLessThan(rightTurn.x);
  expect(await turns.nth(0).evaluate(node => getComputedStyle(node).borderStyle)).toBe('none');
  await expect(page.getByRole('button', { name: 'Play Team Radio' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Transcribe Team Radio' })).toHaveCount(0);
  await expect(page.getByText('New Team Radio', { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => [...document.querySelectorAll('f1-team-radio-view')].every(view => [...view.shadowRoot.querySelectorAll('audio')].every(audio => audio.paused)))).toBe(true);

  const audit = await new AxeBuilder({ page }).include('f1-sensor-card').withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(audit.violations).toEqual([]);
});

test('Team Radio runs the manual transcription action from a discreet control beside Play', async ({ page }) => {
  await page.evaluate(async () => {
    window.mountModular({ config: { modules: [{ type: 'team_radio', options: { ai_task_entity_id: 'ai_task.google_ai_task' } }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const state = demo.hass.states[entry.entities.team_radio];
    state.attributes = {
      ...state.attributes,
      transcription_status: null,
      transcription_text: null,
      transcription_segments: [],
      history: state.attributes.history.map((clip, index) => index ? clip : {
        ...clip, transcription_status: null, transcription_text: null, transcription_segments: [],
      }),
    };
    demo.hass.states['ai_task.google_ai_task'] = { state: 'idle', attributes: {} };
    card.previewData = null;
    card.entries = demo.preview.entries;
    card.revision++;
    await card.updateComplete;
    window.teamRadioCalls = [];
    demo.hass.connection = { connected: true };
    demo.hass.callService = async (...args) => { window.teamRadioCalls.push(args); };
  });

  const play = page.getByRole('button', { name: 'Play Team Radio' });
  const transcribe = page.getByRole('button', { name: 'Transcribe Team Radio' });
  await expect(transcribe).toBeEnabled();
  expect(await transcribe.evaluate(node => node.parentElement?.querySelector('button:not(.transcribe)')?.getAttribute('aria-label'))).toBe('Play Team Radio');
  await expect(play).toBeEnabled();
  await transcribe.click();
  await expect.poll(() => page.evaluate(() => window.teamRadioCalls.length)).toBe(1);
  expect(await page.evaluate(() => window.teamRadioCalls[0])).toEqual([
    'f1_sensor',
    'transcribe_team_radio',
    { entity_id: 'sensor.f1_demo_team_radio', ai_task_entity_id: 'ai_task.google_ai_task', force: false },
    undefined,
    true,
  ]);
});

test('Team Radio editor saves an AI Task entity from domain-filtered choices', async ({ page }) => {
  await page.evaluate(async () => {
    window.mountModular({ editor: true, config: { modules: [{ type: 'team_radio' }] } });
    const editor = window.fixtureCard;
    editor.hass.states['ai_task.google_ai_task'] = { state: 'idle', attributes: {} };
    editor.hass.states['sensor.not_an_ai_task'] = { state: 'idle', attributes: {} };
    editor.requestUpdate();
    await editor.updateComplete;
  });

  await page.getByText('Module options', { exact: true }).click();
  const input = page.getByLabel('AI Task entity for transcription');
  await expect(input).toBeVisible();
  expect(await input.evaluate(node => {
    const choices = node.getRootNode().getElementById(node.getAttribute('list'));
    return [...choices.options].map(option => option.value);
  })).toEqual(['ai_task.google_ai_task']);
  await input.fill('ai_task.google_ai_task');
  await input.evaluate(node => node.dispatchEvent(new Event('change', { bubbles: true, composed: true })));
  await expect.poll(() => page.evaluate(() => window.savedConfig?.modules?.[0]?.options?.ai_task_entity_id)).toBe('ai_task.google_ai_task');
});

test('Team Radio resolves a missing clip identity from the driver list', async ({ page }) => {
  await page.evaluate(async () => {
    window.mountModular({ config: { modules: [{ type: 'team_radio' }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const radioId = entry.entities.team_radio, rosterId = entry.entities.driver_list;
    const clip = {
      utc: '2026-02-20T14:40:24Z', racing_number: '27', path: 'TeamRadio/27_message.mp3',
      clip_url: '/api/f1_sensor/team-radio/demo/27-message?authSig=sample',
      transcription_status: 'completed', transcription_text: 'Check the switches.',
      transcription_segments: [{ speaker: 'A', text: 'Check the switches.' }],
    };
    demo.hass.states[radioId] = {
      ...demo.hass.states[radioId], state: clip.utc, attributes: { ...clip, history: [clip] },
    };
    demo.hass.states[rosterId] = {
      ...demo.hass.states[rosterId],
      attributes: { drivers: [{ racing_number: '27', tla: 'HUL', full_name: 'Nico Hülkenberg', team: 'Audi', team_color: '#f50537' }] },
    };
    card.revision++;
    await card.updateComplete;
  });

  const radio = page.locator('f1-team-radio-view');
  await expect(radio.getByText('HUL', { exact: true })).toBeVisible();
  await expect(radio.getByText('Audi', { exact: true })).toBeVisible();
  await expect(radio.getByText('Unknown driver', { exact: true })).toHaveCount(0);
  await expect(page.locator('[part="team-radio-card"]')).toHaveCSS('border-top-color', 'rgb(245, 5, 55)');
});

test('Team Radio recent view follows shared driver focus', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { context: { driver: '4' }, modules: [{ type: 'team_radio', options: { presentation: 'recent_messages', messages_to_show: 10 } }] } }));
  const radio = page.locator('f1-team-radio-view');

  await expect(page.locator('[part="team-radio-card"]')).toHaveCount(1);
  await expect(radio.getByText('NOR', { exact: true })).toBeVisible();
  await expect(radio.getByText('McLaren', { exact: true })).toBeVisible();
  await expect(radio.getByText('LEC', { exact: true })).toHaveCount(0);
});

test('Team Radio marks only a newly published clip as new', async ({ page }) => {
  await page.evaluate(async () => {
    window.radioPlayCalls = 0;
    HTMLMediaElement.prototype.play = function play() { window.radioPlayCalls++; return Promise.resolve(); };
    window.mountModular({ config: { modules: [{ type: 'team_radio' }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    card.previewData = null;
    card.entries = demo.preview.entries;
    card.revision++;
    await card.updateComplete;
  });
  await expect(page.locator('[part="team-radio-new"]')).toHaveCount(0);

  await page.evaluate(async () => {
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const state = demo.hass.states[entry.entities.team_radio];
    const clip = { utc: '2026-09-13T13:31:00Z', racing_number: '4', driver_tla: 'NOR', driver_name: 'Lando Norris', team_name: 'McLaren', team_color: '#ff8000', path: 'TeamRadio/NOR_4_new.mp3', clip_url: '/api/f1_sensor/team-radio/demo/nor-new?authSig=sample', transcription_status: null, transcription_text: null, transcription_segments: [] };
    state.state = clip.utc;
    state.attributes = { ...clip, history: [clip, ...state.attributes.history] };
    card.revision++;
    await card.updateComplete;
  });

  await expect(page.locator('[part="team-radio-new"]')).toBeVisible();
  await expect(page.locator('f1-team-radio-view').getByText('NOR', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.radioPlayCalls)).toBe(0);
  await page.getByRole('button', { name: 'Play Team Radio' }).click();
  expect(await page.evaluate(() => window.radioPlayCalls)).toBe(1);
  await expect(page.locator('[part="team-radio-new"]')).toHaveCount(0);

  await page.evaluate(async () => {
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    const state = demo.hass.states[entry.entities.team_radio];
    state.attributes.transcription_status = 'completed';
    state.attributes.transcription_text = 'Same clip, transcript added later.';
    state.attributes.transcription_segments = [{ speaker: 'A', text: 'Same clip, transcript added later.' }];
    card.revision++;
    await card.updateComplete;
  });
  await expect(page.locator('[part="team-radio-new"]')).toHaveCount(0);
});
