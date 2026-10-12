const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => { throw error; });
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('first three presets render useful demonstration data with no page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 900 });
  for (const preset of ['weekend', 'session', 'driver']) {
    await page.evaluate(preset => window.mountModular({ preset }), preset);
    await expect(page.getByText('DEMO · sample data')).toBeVisible();
    if (preset === 'weekend') await expect(page.getByRole('region', { name: 'Overview', exact: true }).getByText('Demo Grand Prix', { exact: true })).toBeVisible();
    else await expect(page.locator('button.driver').first()).toContainText('LEC');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('FIA documents retain latest view, race context, count and same-tab links', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'documents', options: {
    presentation: 'latest', open_new_tab: false, show_count: true,
    show_race_context: true, show_latest_badge: true,
  } }] } }));
  const documents = page.getByRole('region', { name: 'FIA documents', exact: true });
  await expect(documents.locator('.documents li')).toHaveCount(1);
  await expect(documents.getByText('Demo Grand Prix', { exact: true })).toBeVisible();
  await expect(documents.getByText('2 documents', { exact: true })).toBeVisible();
  await expect(documents.getByText('Latest first', { exact: true })).toBeVisible();
  await expect(documents.getByText('FIA', { exact: true })).toBeVisible();
  await expect(documents.locator('.documents ha-icon[icon="mdi:file-pdf-box"]')).toHaveCount(1);
  await expect(documents.locator('.document-type')).toHaveText('Document');
  await expect(documents.locator('.documents li')).toHaveClass(/tone-neutral/);
  await expect(documents.locator('.documents a')).toHaveAttribute('target', '_self');
  await expect(documents.getByText(/opens in a new tab/)).toHaveCount(0);
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'documents', options: {
    presentation: 'list', list_max_height: 180, document_coloring: false,
    show_document_type: false, show_fia_logo: false, show_pdf_icon: false,
  } }] } }));
  await expect(documents.locator('.documents li')).toHaveCount(2);
  await expect(documents.locator('.documents-scroll')).toHaveAttribute('style', /max-height:180px/);
  await expect(documents.locator('.documents li[class^="tone-"]')).toHaveCount(0);
  await expect(documents.locator('.document-type')).toHaveCount(0);
  await expect(documents.locator('.documents ha-icon')).toHaveCount(0);
  await expect(documents.getByText('FIA', { exact: true })).toHaveCount(0);
});

test('card actions support gestures and keyboard alternatives while preview is inert', async ({ page }) => {
  await page.clock.install();
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [], entity: 'sensor.f1_demo', tap_action: { action: 'call-service', service: 'input_boolean.toggle' }, hold_action: { action: 'navigate', navigation_path: '/lovelace/f1' }, double_tap_action: { action: 'more-info' } } });
    window.actions = [];
    window.fixtureCard.addEventListener('hass-action', event => window.actions.push(event.detail));
  });
  const target = page.locator('[data-f1-card-action]');
  await target.focus(); await page.keyboard.press('Enter');
  await page.getByText('Card actions', { exact: true }).click();
  await page.getByRole('button', { name: 'Hold action', exact: true }).click();
  await page.getByRole('button', { name: 'Double tap action', exact: true }).click();
  await target.dblclick(); await page.clock.fastForward(300);
  expect(await page.evaluate(() => window.actions)).toEqual([]);
  await page.evaluate(() => { window.fixtureCard.entries = window.fixtureDemo.preview.entries; window.fixtureCard.previewData = null; });
  await target.focus(); await page.keyboard.press('Enter');
  expect(await page.evaluate(() => window.actions.at(-1))).toMatchObject({ action: 'tap', config: { tap_action: { action: 'perform-action', perform_action: 'input_boolean.toggle' } } });
  await page.evaluate(() => { window.actions = []; });
  await target.dblclick(); await page.clock.fastForward(300);
  expect(await page.evaluate(() => window.actions.map(item => item.action))).toEqual(['double_tap']);
  await page.evaluate(() => { window.actions = []; });
  await target.hover(); await page.mouse.down(); await page.clock.fastForward(600); await page.mouse.up(); await page.clock.fastForward(300);
  expect(await page.evaluate(() => window.actions.map(item => item.action))).toEqual(['hold']);
  await page.getByRole('button', { name: 'Hold action', exact: true }).focus(); await page.keyboard.press('Enter');
  expect(await page.evaluate(() => window.actions.map(item => item.action))).toEqual(['hold', 'hold']);
  await page.evaluate(() => { window.actions = []; });
  await target.click(); await page.evaluate(() => window.fixtureCard.remove()); await page.clock.fastForward(1000);
  expect(await page.evaluate(() => window.actions)).toEqual([]);
});

test('native action editor round trip preserves custom content and advanced action properties', async ({ page }) => {
  await page.evaluate(async () => {
    window.mountModular({ editor: true, config: { modules: [{ type: 'timing' }], future_setting: 42 } });
    await window.fixtureCard.updateComplete;
    window.fixtureCard.shadowRoot.querySelector('ha-form').dispatchEvent(new CustomEvent('value-changed', { detail: { value: { entity: 'sensor.example', tap_action: { action: 'perform-action', perform_action: 'script.example', data: { message: 'literal' }, confirmation: { text: 'Continue?' } } } } }));
  });
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.modules[0].type).toBe('timing'); expect(saved.future_setting).toBe(42);
  expect(saved.tap_action).toEqual({ action: 'perform-action', perform_action: 'script.example', data: { message: 'literal' }, confirmation: { text: 'Continue?' } });
});

test('Home Assistant boolean preview still discovers real sources but never runs actions', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ preset: 'weekend' });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    window.previewRequests = []; window.previewActions = [];
    card.previewData = null; card.preview = true;
    card.hass = { ...demo.hass, connection: { subscribeEvents: async () => () => {} }, callWS: async message => { window.previewRequests.push(message.type); return demo.preview.entries; } };
    card.addEventListener('hass-action', event => window.previewActions.push(event.detail));
    card.setConfig({ ...card.config, tap_action: { action: 'toggle' }, entity: 'switch.example' });
  });
  await expect(page.getByRole('region', { name: 'Overview', exact: true }).getByText('Demo Grand Prix', { exact: true })).toBeVisible();
  await expect(page.getByText('DEMO · sample data')).toHaveCount(0);
  await page.locator('[data-f1-card-action]').click();
  expect(await page.evaluate(() => window.previewRequests)).toEqual(['f1_sensor/entities']);
  expect(await page.evaluate(() => window.previewActions)).toEqual([]);
});

test('editor adapts to a narrow HA dialog column on a wide desktop', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1000 });
  await page.evaluate(() => { window.mountModular({ editor: true }); document.querySelector('#root').style.width = '390px'; });
  const editor = page.locator('f1-sensor-card-editor');
  await expect(editor.locator('f1-sensor-card')).toHaveCount(0);
  await expect(editor.getByLabel('Card title', { exact: true })).toBeVisible();
  expect(await editor.evaluate(node => node.scrollWidth <= 390)).toBe(true);
});

test('editor clearly separates whole-card settings from the selected module', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { title: 'Race view', modules: [{ type: 'overview' }, { type: 'timing' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  const cardSettings = editor.getByRole('region', { name: 'Card settings', exact: true });
  const modules = editor.getByRole('region', { name: 'Modules', exact: true });

  await expect(cardSettings.getByText('Whole card', { exact: true })).toBeVisible();
  await expect(cardSettings.getByText('These settings apply to every module in this card.', { exact: true })).toBeVisible();
  await expect(cardSettings.getByLabel('Card title', { exact: true })).toHaveValue('Race view');
  await expect(cardSettings.getByLabel('Module title', { exact: true })).toHaveCount(0);
  await expect(modules.getByText('Selected content', { exact: true })).toBeVisible();
  await expect(modules.getByText('Only this module is affected by the settings below.', { exact: true })).toBeVisible();
  await expect(modules.getByText('Editing module 1 of 2', { exact: true })).toBeVisible();

  await modules.getByRole('button', { name: '2. Timing', exact: true }).click();
  await expect(modules.getByText('Editing module 2 of 2', { exact: true })).toBeVisible();
  await expect(modules.getByRole('button', { name: '2. Timing', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('editor changes style and columns, persists emitted configuration, and preserves content after reload', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1000 });
  await page.evaluate(() => window.mountModular({ preset: 'session', editor: true }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.locator('summary').filter({ hasText: /^Appearance$/ }).click();
  await editor.getByLabel('Style', { exact: true }).selectOption('minimal');
  await editor.getByRole('button', { name: '2. Timing', exact: true }).click();
  await editor.getByRole('checkbox', { name: 'To leader', exact: true }).uncheck();
  await expect(editor.getByRole('checkbox', { name: 'Last lap', exact: true })).toBeChecked();
  await expect(editor.getByRole('checkbox', { name: 'To leader', exact: true })).not.toBeChecked();
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.appearance.style).toBe('minimal');
  expect(saved.modules[1].fields).not.toContain('gap');
  await page.reload(); await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.locator('ha-card[data-style=minimal]')).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'To leader', exact: true })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Last lap', exact: true })).toBeVisible();
});

test('timing remains understandable without color and initial card has no serious accessibility violations', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ preset: 'session' }));
  await expect(page.locator('.signal.overall').first()).toContainText('◆');
  await expect(page.locator('.signal.timed').first()).toContainText('■');
  await page.locator('.timing-legend summary').click();
  await expect(page.getByText('◆ Overall fastest', { exact: true })).toBeVisible();
  await expect(page.getByText('■ Recorded time', { exact: true })).toBeVisible();
  const result = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(result.violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
});

test('timing live gap toggle switches one accessible column without changing the saved columns', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'timing', fields: ['position', 'driver', 'interval'], options: { show_gap_toggle: true } }] } }));
  const group = page.getByRole('group', { name: 'Gap mode', exact: true });
  await expect(group).toBeVisible();
  await expect(group.getByRole('button', { name: 'Ahead', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('columnheader', { name: 'Ahead', exact: true })).toBeVisible();
  await group.getByRole('button', { name: 'Leader', exact: true }).click();
  await expect(group.getByRole('button', { name: 'Leader', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('columnheader', { name: 'To leader', exact: true })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Ahead', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].fields)).toEqual(['position', 'driver', 'interval']);
});

test('a hidden tab is removed from visual and accessibility exposure without recreating modules', async ({ page }) => {
  await page.evaluate(() => { const config = window.mountModular(); config.layout = 'tabs'; window.mountModular({ config }); });
  await expect(page.getByRole('columnheader', { name: 'Driver', exact: true })).not.toBeVisible();
  await page.getByRole('button', { name: 'Timing', exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'Driver', exact: true })).toBeVisible();
  await expect(page.getByText('TRACK CLEAR', { exact: true })).not.toBeVisible();
});

test('freeze is a local reading snapshot and active spoiler protection clears a frozen view', async ({ page }) => {
  await page.evaluate(() => window.mountModular());
  const firstLap = page.locator('tr[data-driver="16"] .time').first();
  await expect(firstLap).toHaveText('1:20.873');
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await page.evaluate(() => {
    const card = window.fixtureCard, entry = card.previewData.entries[0];
    const states = structuredClone(card.hass.states);
    states[entry.entities.driver_positions].attributes.drivers[0].laps[12] = 99;
    card.hass = { ...card.hass, states };
  });
  await expect(firstLap).toHaveText('1:20.873');
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await expect(firstLap).toHaveText('1:39.000');
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.previewData.entries[0].global_entities.no_spoiler_mode = 'switch.demo_spoiler';
    card.hass = { ...card.hass, states: { ...card.hass.states, 'switch.demo_spoiler': { state: 'on' } } };
  });
  await expect(page.getByText('Spoiler protection is active.', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('1:39.000', { exact: true })).toHaveCount(0);
});

test('freeze control is shown by default and can be hidden in the visual editor', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true }));
  const editor = page.locator('f1-sensor-card-editor');
  await expect(page.locator('#native-preview').getByRole('button', { name: 'Freeze view', exact: true })).toBeVisible();
  await editor.locator('summary').filter({ hasText: /^Layout and shared focus$/ }).click();
  const control = editor.getByRole('checkbox', { name: 'Show Freeze view button', exact: true });
  await expect(control).toBeChecked();
  await control.uncheck();
  await expect(page.locator('#native-preview').getByRole('button', { name: 'Freeze view', exact: true })).toHaveCount(0);
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.context.show_freeze_control).toBe(false);
  await page.reload();
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.getByRole('button', { name: 'Freeze view', exact: true })).toHaveCount(0);
});

test('driver focus menu uses compact TLA labels and can be hidden in the visual editor', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  const focus = page.locator('#native-preview').getByRole('combobox', { name: 'Driver focus', exact: true });
  await expect(focus).toBeVisible();
  await expect(focus.locator('option')).toHaveText(['All drivers', 'LEC', 'NOR', 'RUS', 'VER', 'ALO']);
  await editor.locator('summary').filter({ hasText: /^Layout and shared focus$/ }).click();
  const control = editor.getByRole('checkbox', { name: 'Show driver focus menu', exact: true });
  await expect(control).toBeChecked();
  await control.uncheck();
  await expect(focus).toHaveCount(0);
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.context.show_focus_control).toBe(false);
  await page.reload();
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.getByRole('combobox', { name: 'Driver focus', exact: true })).toHaveCount(0);
});

test('timing can show a configurable number of recent laps as comparison columns', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'timing', fields: ['position', 'driver'], options: { history: 3 } }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await expect(page.locator('#native-preview').getByRole('columnheader', { name: 'Lap 10', exact: true })).toBeVisible();
  await expect(page.locator('#native-preview').getByRole('columnheader', { name: 'Lap 11', exact: true })).toBeVisible();
  await expect(page.locator('#native-preview').getByRole('columnheader', { name: 'Lap 12', exact: true })).toBeVisible();
  await expect(page.locator('#native-preview').locator('tr[data-driver="16"] .recent-lap .time')).toHaveText(['1:21.543', '1:21.100', '1:20.873']);
  await editor.getByText('Module options', { exact: true }).click();
  const history = editor.getByRole('spinbutton', { name: 'Recent lap columns', exact: true });
  await expect(history).toHaveValue('3');
  await history.fill('2');
  await history.blur();
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.modules[0].options.history).toBe(2);
  await page.reload();
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.getByRole('columnheader', { name: 'Lap 10', exact: true })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Lap 11', exact: true })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Lap 12', exact: true })).toBeVisible();
});

test('About sections are shown by default and can be hidden per module', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'weather', options: { content: 'automatic_conditions' } }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await expect(page.locator('#native-preview').getByText('About the weather data', { exact: true })).toBeVisible();
  await editor.getByText('Module options', { exact: true }).click();
  const control = editor.getByRole('checkbox', { name: 'Show About section', exact: true });
  await expect(control).toBeChecked();
  await control.uncheck();
  await expect(page.locator('#native-preview').getByText('About the weather data', { exact: true })).toHaveCount(0);
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.modules[0].options.show_explanation).toBe(false);
  await page.reload();
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.getByText('About the weather data', { exact: true })).toHaveCount(0);
  await page.evaluate(() => window.mountModular({ scene: 'replay', config: { modules: [{ type: 'telemetry', options: { show_explanation: false } }] } }));
  await expect(page.locator('f1-telemetry-view svg.plot')).toHaveCount(3);
  await expect(page.getByText('About the telemetry', { exact: true })).toHaveCount(0);
});

test('module reordering preserves the module element and keyboard focus on its driver', async ({ page }) => {
  await page.evaluate(() => window.mountModular());
  const driver = page.locator('button[data-focus="driver-16"]');
  await driver.focus();
  await page.evaluate(() => {
    const card = window.fixtureCard;
    window.originalTimingModule = card.moduleNodes.get(card.config.modules[1].id);
    const config = structuredClone(card.config);
    [config.modules[0], config.modules[1]] = [config.modules[1], config.modules[0]];
    card.setConfig(config);
  });
  await expect(driver).toBeFocused();
  expect(await page.evaluate(() => window.fixtureCard.moduleNodes.get(window.fixtureCard.config.modules[0].id) === window.originalTimingModule)).toBe(true);
});

test('timing rows keep driver identity, expanded details and focus across position and column changes', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ preset: 'session' }));
  await page.locator('button.driver').first().click();
  await page.evaluate(() => {
    const module = [...window.fixtureCard.moduleNodes.values()].find(node => node.module.type === 'timing');
    window.retainedRow = module.shadowRoot.querySelector('tr[data-driver]');
    window.retainedButton = window.retainedRow.querySelector('button.driver');
    window.retainedButton.focus();
    module.model = { ...module.model, rows: [...module.model.rows].reverse() };
    module.module = { ...module.module, fields: [...module.module.fields].reverse() };
    window.timingModule = module;
  });
  await expect.poll(() => page.evaluate(() => {
    const node = window.timingModule;
    return {
      sameRow: node.shadowRoot.querySelector(`tr[data-driver="${window.retainedRow.dataset.driver}"]`) === window.retainedRow,
      sameButton: window.retainedRow.querySelector('button.driver') === window.retainedButton,
      focused: node.shadowRoot.activeElement === window.retainedButton,
      expanded: window.retainedButton.getAttribute('aria-expanded'),
      last: node.shadowRoot.querySelector('tr[data-driver]:last-of-type')?.dataset.driver === window.retainedRow.dataset.driver,
    };
  })).toMatchObject({ sameRow: true, sameButton: true, focused: true, expanded: 'true' });
});

test('all three styles retain timing content in light and dark themes', async ({ page }, info) => {
  await page.setViewportSize({ width: 1050, height: 950 });
  for (const style of ['f1', 'ha', 'minimal']) for (const mode of ['light', 'dark']) {
    await page.evaluate(({ style, mode }) => {
      const config = window.mountModular();
      config.appearance.style = style; config.appearance.mode = mode;
      config.appearance.logos = false;
      window.mountModular({ config });
    }, { style, mode });
    await expect(page.locator('tr[data-driver="16"] .time').first()).toHaveText('1:20.873');
    const results = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
    expect(results.violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
    await page.screenshot({ path: info.outputPath(`${style}-${mode}.png`), fullPage: true });
  }
});

test('custom CSS uses stable module targets, public parts and one reusable scoped stylesheet', async ({ page }) => {
  const styles = `body { --f1-outside-probe: changed; }\nha-card { --f1-card-radius: 31px; }\nf1-module-view[data-module-type="timing"] { --f1-cell-padding: 3px 7px; }\nf1-module-view[data-module-type="timing"]::part(module-title) { color: rgb(1, 2, 3); }`;
  await page.evaluate(styles => window.mountModular({ config: { styles, modules: [{ id: 'main-timing', type: 'timing', fields: ['position', 'driver', 'last_lap'] }] } }), styles);
  await expect.poll(() => page.evaluate(() => {
    const card = window.fixtureCard;
    const module = [...card.moduleNodes.values()][0];
    const style = card.shadowRoot.querySelector('style[data-f1-user-styles]');
    const surface = card.shadowRoot.querySelector('ha-card');
    const cell = module?.shadowRoot?.querySelector('td');
    const title = module?.shadowRoot?.querySelector('[part="module-title"]');
    return {
      styleCount: card.shadowRoot.querySelectorAll('style[data-f1-user-styles]').length,
      styleText: style?.textContent,
      radius: surface ? getComputedStyle(surface).borderRadius : null,
      moduleType: module?.dataset.moduleType,
      moduleId: module?.dataset.moduleId,
      modulePart: module?.getAttribute('part'),
      cellPadding: cell ? getComputedStyle(cell).padding : null,
      titleColor: title ? getComputedStyle(title).color : null,
      outsideProbe: getComputedStyle(document.body).getPropertyValue('--f1-outside-probe'),
    };
  })).toEqual({
    styleCount: 1,
    styleText: styles,
    radius: '31px',
    moduleType: 'timing',
    moduleId: 'main-timing',
    modulePart: 'module',
    cellPadding: '3px 7px',
    titleColor: 'rgb(1, 2, 3)',
    outsideProbe: '',
  });
  expect(await page.evaluate(() => {
    const card = window.fixtureCard;
    window.originalUserStyle = card.shadowRoot.querySelector('style[data-f1-user-styles]');
    card.setConfig({ ...card.config, styles: 'ha-card { --f1-card-radius: 18px; }' });
    card.revision++;
    return true;
  })).toBe(true);
  await expect.poll(() => page.evaluate(() => {
    const card = window.fixtureCard;
    const style = card.shadowRoot.querySelector('style[data-f1-user-styles]');
    return { same: style === window.originalUserStyle, text: style?.textContent, count: card.shadowRoot.querySelectorAll('style[data-f1-user-styles]').length };
  })).toEqual({ same: true, text: 'ha-card { --f1-card-radius: 18px; }', count: 1 });
  await page.evaluate(() => { const card = window.fixtureCard; const config = { ...card.config }; delete config.styles; card.setConfig(config); card.revision++; });
  await expect.poll(() => page.evaluate(() => window.fixtureCard.shadowRoot.querySelectorAll('style[data-f1-user-styles]').length)).toBe(0);
});

test('visual editor saves, previews and resets custom CSS', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: true, config: { modules: [{ type: 'timing' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.locator('summary').filter({ hasText: /^Appearance$/ }).click();
  await editor.locator('summary').filter({ hasText: /^Custom CSS \(advanced\)$/ }).click();
  const input = editor.getByLabel('Custom CSS', { exact: true });
  await input.fill('ha-card { --f1-card-radius: 27px; }');
  await expect.poll(() => page.evaluate(() => window.savedConfig?.styles)).toBe('ha-card { --f1-card-radius: 27px; }');
  await expect.poll(() => page.locator('#native-preview f1-sensor-card').evaluate(card => card.shadowRoot.querySelector('ha-card') && getComputedStyle(card.shadowRoot.querySelector('ha-card')).borderRadius)).toBe('27px');
  await editor.getByRole('button', { name: 'Reset custom CSS', exact: true }).click();
  await expect.poll(() => page.evaluate(() => Object.hasOwn(window.savedConfig, 'styles'))).toBe(false);
  await expect(input).toHaveValue('');
});

test('editor and preview remain operable with forced colors and enlarged text', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 950 });
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; window.mountModular({ preset: 'session', editor: true, nativePreview: true }); });
  await expect(page.getByText('DEMO · sample data', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '2. Timing', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('results, standings and document modules share UI options and protect all spoiler content', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'results', options: { content: 'race_results', spoiler_placeholder: 'CLASSIFIED', driver_image_type: 'headshot' } }, { type: 'standings', fields: ['result_position', 'driver', 'points', 'predicted_points', 'points_change'], options: { show_mode_badge: false, spoiler_placeholder: 'TABLE HIDDEN', driver_image_type: 'headshot' } }, { type: 'documents' }] } }));
  await expect(page.getByRole('heading', { name: 'Results', exact: true })).toBeVisible();
  await expect(page.locator('.chip').filter({ hasText: /^Race$/ })).toBeVisible();
  await expect(page.getByText('1:24:10.456', { exact: true })).toBeVisible();
  await page.getByLabel('Round', { exact: true }).selectOption('13');
  await expect(page.getByText('Previous Demo Grand Prix · Race · Round 13', { exact: false })).toBeVisible();
  await expect(page.getByText('1:24:10.456', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Projected points', exact: true })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Projected change', exact: true })).toBeVisible();
  await expect(page.getByText('+20', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Published standings', { exact: true })).toHaveCount(0);
  await expect(page.locator('.driver-headshot')).toHaveCount(2);
  await expect(page.getByRole('link', { name: /Demo · Provisional starting grid/ })).toHaveAttribute('rel', 'noopener noreferrer');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const results = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(results.violations.filter(item => ['critical', 'serious'].includes(item.impact))).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('season-modules-mobile.png'), fullPage: true });
  await page.evaluate(() => {
    const card = window.fixtureCard, config = structuredClone(card.config);
    config.modules.find(module => module.type === 'results').options.show_selector = false;
    config.modules.find(module => module.type === 'results').options.show_session_type_badge = false;
    card.setConfig(config);
  });
  await expect(page.getByRole('combobox', { name: 'Round', exact: true })).toHaveCount(0);
  await expect(page.locator('.chip').filter({ hasText: /^Race$/ })).toHaveCount(0);
  await page.evaluate(() => { const card = window.fixtureCard; card.hass = { ...card.hass, states: { ...card.hass.states, 'switch.f1_demo_spoilers': { state: 'on' } } }; });
  await expect(page.getByText('CLASSIFIED', { exact: true })).toBeVisible();
  await expect(page.getByText('TABLE HIDDEN', { exact: true })).toBeVisible();
  await expect(page.getByText('Spoiler protection is active.', { exact: true })).toHaveCount(1);
  await expect(page.getByRole('link')).toHaveCount(0);
  await expect(page.locator('.module-context')).toHaveCount(0);
});

test('global spoiler protection blocks every sensitive module and keeps sensitive resources closed', async ({ page }) => {
  const sensitive = await page.evaluate(async () => {
    const { MODULES } = await import('/custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js');
    return Object.entries(MODULES).filter(([type, definition]) => definition.spoiler || ['timing', 'race_control'].includes(type)).map(([type]) => type);
  });
  await page.evaluate(types => {
    const modules = [...types.map(type => ({ type })), { type: 'weather', options: { content: 'track_conditions' } }];
    window.mountModular({ config: { modules } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    const entry = structuredClone(demo.preview.entries[0]);
    window.spoilerResourceCalls = [];
    window.spoilerResourceStops = 0;
    const connection = {
      connected: true,
      addEventListener() {},
      removeEventListener() {},
      subscribeEvents: async (_callback, type) => {
        window.spoilerResourceCalls.push(`event:${type}`);
        return () => { window.spoilerResourceStops++; };
      },
      subscribeMessage: async (_callback, message) => {
        window.spoilerResourceCalls.push(`message:${message.type}`);
        return () => { window.spoilerResourceStops++; };
      },
    };
    const states = { ...demo.hass.states, [entry.global_entities.no_spoiler_mode]: { state: 'on', attributes: {} } };
    card.previewData = null;
    card.hass = {
      ...demo.hass,
      states,
      connection,
      callWS: async message => {
        window.spoilerResourceCalls.push(`ws:${message.type}`);
        if (message.type === 'f1_sensor/entities') return [entry];
        if (message.type === 'f1_sensor/race_control_log/get') return { items: [] };
        return {};
      },
    };
  }, sensitive);

  await expect(page.locator('f1-module-view')).toHaveCount(17);
  expect(await page.evaluate(() => [...window.fixtureCard.moduleNodes.values()].map(node => ({
    type: node.module.type,
    blocked: node.model.blocked,
    leakedPayload: ['rows', 'items', 'series', 'events', 'values', 'documents'].some(key => Object.hasOwn(node.model, key)),
  })))).toEqual([...sensitive, 'weather'].map(type => ({ type, blocked: 'Spoiler protection is active.', leakedPayload: false })));
  expect(await page.evaluate(() => window.spoilerResourceCalls.filter(call => call !== 'event:entity_registry_updated'))).toEqual(['ws:f1_sensor/entities']);

  await page.evaluate(() => {
    const card = window.fixtureCard, entity = card.entry.global_entities.no_spoiler_mode;
    card.hass = { ...card.hass, states: { ...card.hass.states, [entity]: { state: 'unavailable', attributes: {} } } };
  });
  await expect(page.getByText('Spoiler status cannot be verified. Refresh F1 Sensor before showing sensitive data.', { exact: true })).toHaveCount(17);
  expect(await page.evaluate(() => window.spoilerResourceCalls.filter(call => call !== 'event:entity_registry_updated'))).toEqual(['ws:f1_sensor/entities']);

  await page.evaluate(() => {
    const card = window.fixtureCard, entity = card.entry.global_entities.no_spoiler_mode;
    card.hass = { ...card.hass, states: { ...card.hass.states, [entity]: { state: 'off', attributes: {} } } };
  });
  await expect.poll(() => page.evaluate(() => window.spoilerResourceCalls)).toEqual(expect.arrayContaining([
    'message:f1_sensor/track_map/subscribe',
    'message:f1_sensor/analysis/subscribe',
    'event:f1_sensor_race_control_event',
    'event:f1_sensor_race_control_log_reset_event',
    'ws:f1_sensor/race_control_log/get',
  ]));

  await page.evaluate(() => {
    const card = window.fixtureCard, entity = card.entry.global_entities.no_spoiler_mode;
    card.hass = { ...card.hass, states: { ...card.hass.states, [entity]: { state: 'on', attributes: {} } } };
  });
  await expect(page.getByText('Spoiler protection is active.', { exact: true })).toHaveCount(17);
  await expect.poll(() => page.evaluate(() => window.spoilerResourceStops)).toBeGreaterThanOrEqual(4);
});

test('hidden championship availability guidance never hides an authentication problem', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'standings', fields: ['driver', 'points', 'predicted_points'], options: { show_availability_notice: false } }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.hass.states[entry.entities.championship_prediction_drivers] = { state: 'unavailable', attributes: {} };
    entry.entities.f1tv_token_status = 'sensor.f1_demo_f1tv_token_status';
    demo.hass.states[entry.entities.f1tv_token_status] = { state: 'expired', attributes: {} };
    card.hass = { ...demo.hass, states: { ...demo.hass.states } };
  });
  await expect(page.getByText('F1TV access needs attention, so live championship projections are hidden. Published standings remain available.', { exact: true })).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    demo.hass.states[entry.entities.f1tv_token_status] = { state: 'valid', attributes: {} };
    card.hass = { ...demo.hass, states: { ...demo.hass.states } };
  });
  await expect(page.getByText('Projection unavailable.', { exact: false })).toHaveCount(0);
  await expect(page.getByText('F1TV access needs attention', { exact: false })).toHaveCount(0);
});

test('result editor offers available rounds and grid columns while preserving custom choices', async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 1200 });
  await page.evaluate(async () => {
    window.mountModular({ editor: true, preset: 'results' });
    window.fixtureCard.entries = window.fixtureDemo.preview.entries;
  });
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByLabel('Result content', { exact: true }).selectOption('race_results');
  await editor.locator('.form').getByLabel('Round', { exact: true }).selectOption('13');
  expect(await page.evaluate(() => window.savedConfig.modules[0].options.round)).toBe('13');
  await editor.getByLabel('Result content', { exact: true }).selectOption('starting_grid');
  await expect(editor.getByRole('checkbox', { name: 'Grid', exact: true })).toBeChecked();
  expect(await page.evaluate(() => window.savedConfig.modules[0].fields)).toContain('qualifying_time');
  await editor.getByRole('checkbox', { name: 'Qualifying position', exact: true }).uncheck();
  const custom = await page.evaluate(() => window.savedConfig.modules[0].fields);
  await editor.getByLabel('Result content', { exact: true }).selectOption('race_results');
  expect(await page.evaluate(() => window.savedConfig.modules[0].fields)).toEqual(custom);
});

test('starting grid exposes migrated comparison columns and independent context visibility', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'results', options: {
    content: 'starting_grid', show_context: true, show_status: true, show_source: true,
  }, fields: ['grid_position', 'driver', 'qualifying_position', 'grid_delta', 'qualifying_segment', 'qualifying_time', 'qualifying_delta'] }] } }));
  const grid = page.getByRole('region', { name: 'Results', exact: true });
  await expect(grid.getByRole('columnheader', { name: 'Grid change', exact: true })).toBeVisible();
  await expect(grid.getByRole('columnheader', { name: 'Qualifying segment', exact: true })).toBeVisible();
  await expect(grid.getByRole('columnheader', { name: 'Qualifying gap', exact: true })).toBeVisible();
  await expect(grid.getByText('Grid status: Provisional', { exact: true })).toBeVisible();
  await expect(grid.getByText('Source: qualifying', { exact: true })).toBeVisible();
  await expect(grid.getByText('Demo Grand Prix · Race', { exact: false })).toBeVisible();
  await page.evaluate(() => { const config = structuredClone(window.fixtureCard.config); config.modules[0].options.show_context = false; config.modules[0].options.show_status = false; config.modules[0].options.show_source = false; window.fixtureCard.setConfig(config); });
  await expect(grid.locator('.module-context')).toHaveCount(0);
  await page.evaluate(() => { const config = structuredClone(window.fixtureCard.config); config.modules[0].options.presentation = 'grid'; window.fixtureCard.setConfig(config); });
  await expect(grid.locator('.result-grid li')).toHaveCount(5);
  await expect(grid.locator('.result-grid').getByText('Grid change', { exact: true }).first()).toBeVisible();
  await expect(grid.getByRole('columnheader')).toHaveCount(0);
});

test('tyre images reserve space with a letter fallback and track status keeps its text in forced colors', async ({ page }) => {
  await page.route('**/*_tyre.png*', route => route.abort());
  await page.evaluate(() => window.mountModular({ config: { appearance: { tyre_style: 'both' }, modules: [{ type: 'overview', fields: ['track_status'] }, { type: 'timing', fields: ['driver', 'tyre'] }] } }));
  await expect(page.getByText('Track clear', { exact: true })).toBeVisible();
  await expect(page.locator('.tyre').first()).toHaveAccessibleName('Tyre · Soft');
  await expect(page.locator('.compound img').first()).toBeHidden();
  await expect(page.locator('.tyre').first()).toContainText('S');
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  await expect(page.getByText('Track clear', { exact: true })).toBeVisible();
  const colors = await page.locator('.track-symbol').evaluate(node => ({ ink: getComputedStyle(node).color, paper: getComputedStyle(node).backgroundColor }));
  expect(colors.ink).not.toBe(colors.paper);
});

test('progression chart loads on demand, reflows at mobile width and exposes identical values as a table', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 1000 });
  const chartRequests = [];
  page.on('request', request => { if (request.url().includes('/modular/chart.js')) chartRequests.push(request.url()); });
  await page.evaluate(() => window.mountModular({ preset: 'weekend' }));
  expect(chartRequests).toEqual([]);
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'progression', options: { selected: ['LEC', 'NOR'] } }] } }));
  await expect(page.locator('f1-series-chart svg.plot')).toBeVisible();
  expect(chartRequests).toHaveLength(1);
  await expect(page.getByText('● Charles Leclerc', { exact: true })).toBeVisible();
  await expect(page.getByText('■ Lando Norris', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Show data table', exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'Charles Leclerc', exact: true })).toBeVisible();
  const last = page.locator('f1-series-chart tbody tr').last();
  await expect(last).toContainText('4 · Future Demo Grand Prix');
  await expect(last.locator('td')).toHaveText(['—', '—']);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('progression-mobile.png'), fullPage: true });
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  const violations = (await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations;
  expect(violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('progression chart applies legacy legend, point, label, future-round and height choices', async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 900 });
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'progression', options: {
    selected: ['LEC', 'NOR'], legend_position: 'right', show_legend_points: true,
    show_points: false, show_round_labels: false, show_future_rounds: false, chart_height: 500,
  } }] } }));
  const chart = page.locator('f1-series-chart');
  await expect(chart.locator('.chart-layout')).toHaveAttribute('data-legend', 'right');
  await expect(chart.locator('svg.plot')).toHaveAttribute('viewBox', / 500$/);
  await expect(chart.locator('svg.plot .marker')).toHaveCount(0);
  await expect(chart.locator('svg.plot .round-label')).toHaveCount(0);
  await expect(chart.locator('.chart-legend .muted')).toHaveText(['68 pts', '64 pts']);
  await chart.getByRole('button', { name: 'Show data table', exact: true }).click();
  await expect(chart.locator('tbody tr')).toHaveCount(3);
  await page.evaluate(() => { const card = window.fixtureCard, config = structuredClone(card.config); config.modules[0].options.show_legend = false; card.setConfig(config); });
  await expect(chart.locator('.chart-legend')).toHaveCount(0);
});

test('progression uses team colors and toggles drivers from either the legend or chart line', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'progression', options: { selected: ['LEC', 'NOR'] } }] } }));
  const chart = page.locator('f1-series-chart');
  const leclerc = chart.locator('[data-series="LEC"]');
  const norris = chart.locator('[data-series="NOR"]');
  await expect(leclerc.locator('.series-line').first()).toHaveAttribute('style', /stroke:#ed1131/);
  await expect(norris.locator('.series-line').first()).toHaveAttribute('style', /stroke:#f47600/);
  const legend = chart.locator('.chart-legend');
  const leclercLegend = legend.getByRole('button', { name: 'Charles Leclerc: visible. Hide series.', exact: true });
  const norrisLegend = legend.getByRole('button', { name: 'Lando Norris: visible. Hide series.', exact: true });
  await expect(leclercLegend).toHaveAttribute('aria-pressed', 'true');

  const linePoint = await leclerc.locator('.series-line').first().evaluate(node => {
    const point = node.getPointAtLength(node.getTotalLength() / 2), matrix = node.getScreenCTM();
    return { x: point.x * matrix.a + point.y * matrix.c + matrix.e, y: point.x * matrix.b + point.y * matrix.d + matrix.f };
  });
  await page.mouse.click(linePoint.x, linePoint.y);
  await expect(chart.locator('[data-series="LEC"]')).toHaveCount(0);
  await expect(legend.getByRole('button', { name: 'Charles Leclerc: hidden. Show series.', exact: true })).toHaveAttribute('aria-pressed', 'false');
  await chart.getByRole('button', { name: 'Show data table', exact: true }).click();
  await expect(chart.getByRole('columnheader', { name: 'Charles Leclerc', exact: true })).toHaveCount(0);
  await expect(chart.getByRole('columnheader', { name: 'Lando Norris', exact: true })).toBeVisible();

  await legend.getByRole('button', { name: 'Charles Leclerc: hidden. Show series.', exact: true }).click();
  await expect(chart.locator('[data-series="LEC"]')).toHaveCount(1);
  await norrisLegend.click();
  await expect(chart.locator('[data-series="NOR"]')).toHaveCount(0);
  await expect(legend.getByRole('button', { name: 'Lando Norris: hidden. Show series.', exact: true })).toHaveAttribute('aria-pressed', 'false');

  await page.evaluate(() => {
    const card = window.fixtureCard, config = structuredClone(card.config);
    config.appearance.team_colors = false; card.setConfig(config);
  });
  await expect(chart.locator('[data-series="LEC"] .series-line').first()).not.toHaveAttribute('style', /stroke:#ed1131/);
});

test('limited result tables disclose their row count and expand locally without changing saved defaults', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'results', options: { rows: 2 } }] } }));
  await expect(page.getByText('2 of 5 competitors', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Show all', exact: true }).click();
  await expect(page.getByText('5 of 5 competitors', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.fixtureCard.config.modules[0].options.rows)).toBe(2);
  await page.getByRole('button', { name: 'Show fewer', exact: true }).click();
  await expect(page.locator('tr[data-driver]')).toHaveCount(2);
});

test('tyres, stops and incidents provide independent fields, semantic graphics and accessible mobile content', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => window.mountModular({ config: { appearance: { tyre_style: 'both' }, modules: [
    { type: 'tyres', options: { rows: 2 } },
    { type: 'tyres', title: 'Compound comparison', options: { content: 'statistics' }, fields: ['tyre', 'compound_best', 'compound_gap', 'new_sets', 'total_stints', 'best_runs'] },
    { type: 'pit_stops', fields: ['driver', 'stop_lap', 'stop_time', 'lane_time', 'pit_delta'] },
    { type: 'incidents' }, { type: 'incidents', title: 'Track limits', options: { content: 'track_limits' } },
  ] } }));
  const tyres = page.getByRole('region', { name: 'Tyres', exact: true });
  await expect(tyres.getByRole('img', { name: 'Tyre · Soft', exact: true })).toBeVisible();
  const compounds = page.getByRole('region', { name: 'Compound comparison', exact: true });
  await expect(compounds.getByText('1:20.873', { exact: true })).toHaveCount(2);
  await expect(compounds.getByText('0.000 s', { exact: true })).toBeVisible();
  await expect(page.getByText('Estimated lap loss:', { exact: false })).toBeVisible();
  await expect(page.getByText('After the race', { exact: true })).toBeVisible();
  await expect(page.getByText('Decision time', { exact: true })).toBeVisible();
  await expect(page.getByText('Lap time deleted', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze(); expect(axe.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('session-modules-mobile.png'), fullPage: true });
  await page.emulateMedia({ forcedColors: 'active' });
  await expect(page.getByText('Under investigation', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await page.evaluate(() => { window.fixtureCard.hass = { ...window.fixtureCard.hass, states: { ...window.fixtureCard.hass.states, 'switch.f1_demo_spoilers': { state: 'on', attributes: {} } } }; });
  await expect(page.getByText('Spoiler protection is active.', { exact: true })).toHaveCount(5);
  await expect(page.locator('.incident-list')).toHaveCount(0); await expect(page.locator('.stint-runs')).toHaveCount(0);
});

test('tyre editor switches starter profiles and keeps custom columns and unavailable selections', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1000 });
  await page.evaluate(() => { window.mountModular({ editor: true, nativePreview: true, config: { modules: [{ type: 'tyres' }] } }); window.fixtureCard.entries = window.fixtureDemo.preview.entries; });
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByLabel('Tyre content', { exact: true }).selectOption('statistics');
  await expect(editor.getByRole('checkbox', { name: 'Best recorded lap', exact: true })).toBeChecked();
  await expect(editor.getByRole('checkbox', { name: 'Show compound name', exact: true })).toBeChecked();
  await editor.getByRole('checkbox', { name: 'Show compound name', exact: true }).uncheck();
  await editor.getByRole('checkbox', { name: 'Fastest recorded stints', exact: true }).check();
  await editor.getByLabel('Fastest stints per compound', { exact: true }).fill('1');
  await editor.getByLabel('Fastest stints per compound', { exact: true }).press('Tab');
  const statistics = page.locator('#native-preview f1-sensor-card').getByRole('region', { name: 'Tyres', exact: true });
  await expect(statistics.getByRole('img', { name: 'Tyre · Soft', exact: true })).toBeVisible();
  await expect(statistics.getByText('Soft', { exact: true })).toHaveCount(0);
  await expect(statistics.locator('tbody tr').first().locator('.stint-runs li')).toHaveCount(1);
  expect(await page.evaluate(() => window.savedConfig.modules[0].options)).toMatchObject({ show_compound_name: false, best_times_limit: 1 });
  await expect(editor.getByLabel('Pinned driver', { exact: true })).toHaveCount(0);
  await editor.getByRole('checkbox', { name: 'Stints recorded', exact: true }).check();
  await editor.getByLabel('Tyre content', { exact: true }).selectOption('current');
  expect(await page.evaluate(() => window.savedConfig.modules[0].fields)).toContain('total_stints');
  await expect(editor.getByLabel('Pinned driver', { exact: true })).toBeVisible();
  await editor.getByLabel('Pinned driver', { exact: true }).selectOption('16');
  expect(await page.evaluate(() => window.savedConfig.modules[0].driver)).toBe('16');
});

test('pit capability and compound waiting states explain missing sources without inventing zeros', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ scene: 'missing', config: { modules: [{ type: 'pit_stops' }, { type: 'tyres', options: { content: 'statistics' } }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    demo.hass.states[demo.preview.entries[0].entities.tyre_statistics] = { state: 'unknown', attributes: { status: 'waiting_for_compound_data', compounds: {} } };
    card.hass = { ...demo.hass };
  });
  await expect(page.getByText('Pit stop timing needs F1TV access', { exact: false })).toBeVisible();
  await expect(page.getByText('Waiting for compound information', { exact: false })).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(0);
});

test('pit availability notice can be hidden but authentication warnings remain visible', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ scene: 'missing', config: { modules: [{ type: 'pit_stops', options: { show_availability_notice: false } }] } });
  });
  await expect(page.getByText('Pit stop timing needs F1TV access', { exact: false })).toHaveCount(0);
  await expect(page.getByText('No session data is currently available', { exact: false })).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
    entry.entities.f1tv_token_status = 'sensor.f1_demo_f1tv_token_status';
    demo.hass.states[entry.entities.f1tv_token_status] = { state: 'rejected', attributes: { auth_configured: true }, last_updated: '2026-09-13T13:30:00Z' };
    card.hass = { ...demo.hass };
  });
  await expect(page.getByText('F1TV access needs attention', { exact: false })).toBeVisible();
});

test('pit editor exposes status and availability choices and renders current driver status', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: true, config: { modules: [{ type: 'pit_stops' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await expect(editor.getByRole('checkbox', { name: 'Status', exact: true })).toBeChecked();
  await expect(editor.getByRole('checkbox', { name: 'Explain F1TV availability', exact: true })).toBeChecked();
  await expect(page.locator('#native-preview f1-sensor-card').getByText('On track', { exact: true }).first()).toBeVisible();
  await editor.getByRole('checkbox', { name: 'Status', exact: true }).uncheck();
  await expect(page.locator('#native-preview f1-sensor-card').getByText('On track', { exact: true })).toHaveCount(0);
});

test('automatic timing profile follows the sample session and a column edit becomes a persistent custom choice', async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 1100 });
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: true, scene: 'qualifying', config: { modules: [{ type: 'timing' }] } }));
  await page.evaluate(() => { window.fixtureCard.entries = window.fixtureDemo.preview.entries; });
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByLabel('Column profile', { exact: true }).selectOption('auto');
  await page.getByLabel('Sample session', { exact: true }).selectOption('sprint_qualifying');
  const card = page.locator('#native-preview f1-sensor-card');
  await expect(card.getByRole('columnheader', { name: 'SQ1 best', exact: true })).toBeVisible();
  await expect(card.getByText('SQ1 · eliminated', { exact: true })).toHaveCount(2);
  await editor.getByRole('checkbox', { name: 'Q3 best', exact: true }).uncheck();
  await expect(editor.getByLabel('Column profile', { exact: true })).toHaveValue('custom');
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.modules[0].fields).toContain('q1_time'); expect(saved.modules[0].fields).not.toContain('q3_time');
  await page.getByLabel('Sample session', { exact: true }).selectOption('race');
  await expect(card.getByRole('columnheader', { name: 'Q1 best', exact: true })).toBeVisible();
  await expect(card.getByText('Q/SQ columns are available during qualifying sessions.', { exact: false })).toBeVisible();
  expect(await page.evaluate(() => window.savedConfig.modules[0].fields)).toEqual(saved.modules[0].fields);
});

test('personal best sector laps and theoretical sum keep separate labels and qualifying part provenance', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ scene: 'qualifying', config: { modules: [{ type: 'timing', driver: '16', fields: ['driver', 'best_sector_1', 'best_sector_2', 'best_sector_3', 'theoretical_lap'] }] } }));
  await expect(page.getByRole('cell').getByText('Lap 10', { exact: true })).toBeVisible();
  await expect(page.getByRole('cell').getByText('Lap 12', { exact: true })).toBeVisible();
  await expect(page.getByText('Sum of personal-best sectors · may span laps', { exact: true })).toBeVisible();
  await expect(page.getByText('1:20.774', { exact: true })).toBeVisible();
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze(); expect(axe.violations).toEqual([]);
});

test('timeline distinguishes estimates from source events and protects all details when spoilers activate', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'timeline', fields: ['event_time', 'analysis_title', 'incident_drivers', 'analysis_source', 'analysis_quality'] }] } }));
  await expect(page.getByText('Derived estimate', { exact: true })).toBeVisible();
  await expect(page.getByText('55%', { exact: true })).toBeVisible();
  await expect(page.getByText('Demo · track clear', { exact: true })).toBeVisible();
  await expect(page.getByText('Evidence score measures support, not probability.', { exact: true })).toBeVisible();
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze(); expect(axe.violations).toEqual([]);
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await page.evaluate(() => { const card = window.fixtureCard; card.hass = { ...card.hass, states: { ...card.hass.states, 'switch.f1_demo_spoilers': { state: 'on', attributes: {} } } }; });
  await expect(page.getByText('Spoiler protection is active.', { exact: true })).toBeVisible();
  await expect(page.getByText('Demo · track clear', { exact: true })).toHaveCount(0);
});

test('real analysis subscription refreshes a card and changing modules only releases the frontend consumer', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'timeline' }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    window.analysisRequests = []; window.analysisUnsubscribed = 0; window.analysisServices = 0;
    card.entries = demo.preview.entries; card.previewData = null;
    card.hass = { ...demo.hass, connection: { subscribeEvents: async () => () => {}, subscribeMessage: async (callback, message) => { window.analysisRequests.push(message); window.analysisCallback = callback; callback(demo.preview.analysis); return () => window.analysisUnsubscribed++; } }, callWS: async () => demo.preview.entries, callService: () => window.analysisServices++ };
  });
  await expect(page.getByText('Demo · track clear', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.analysisRequests)).toHaveLength(1);
  await page.evaluate(() => window.analysisCallback({ ...window.fixtureDemo.preview.analysis, timeline: { events: [] } }));
  await expect(page.getByText('Demo · track clear', { exact: true })).toHaveCount(0);
  await page.evaluate(() => window.fixtureCard.setConfig({ modules: [{ type: 'overview' }] }));
  await expect.poll(() => page.evaluate(() => window.analysisUnsubscribed)).toBe(1);
  expect(await page.evaluate(() => window.analysisServices)).toBe(0);
});

test('strategy displays coverage and estimated pace with accessible compound graphics', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'strategy', driver: '16', fields: ['driver', 'tyre', 'clean_pace', 'raw_pace', 'clean_samples', 'excluded_samples', 'degradation', 'analysis_quality'] }] } }));
  await expect(page.getByText('Local estimate', { exact: true })).toBeVisible();
  await expect(page.getByText(/Session coverage · all drivers\s*Clean laps: 30 · Recorded: 40 · Excluded: 10/, { exact: false })).toBeVisible();
  await expect(page.getByText('1:21.120', { exact: true })).toBeVisible();
  await expect(page.getByText('1:21.500', { exact: true })).toBeVisible();
  await expect(page.getByText('+0.053 s/lap', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze(); expect(axe.violations).toEqual([]);
});

test('map exposes driver labels, noncolor stale status and an accessible mobile list with stable local choices', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'map' }] } }));
  const map = page.locator('f1-track-map-view');
  await expect(map.getByRole('img', { name: 'Driver positions on the track' })).toBeVisible();
  await expect(map.locator('.marker')).toHaveCount(5);
  expect(await map.evaluate(node => {
    const frame = node.shadowRoot.querySelector('svg').getBoundingClientRect();
    return [...node.shadowRoot.querySelectorAll('.marker text')].every(label => { const bounds = label.getBoundingClientRect(); return bounds.width > 0 && bounds.left >= frame.left && bounds.right <= frame.right && bounds.top >= frame.top && bounds.bottom <= frame.bottom; });
  })).toBe(true);
  await expect(map.getByText('Saved position · stale', { exact: true })).toBeVisible();
  const driver = map.getByRole('button', { name: /16 · LEC/ });
  await driver.focus(); await page.keyboard.press('Enter');
  await expect(driver).toHaveAttribute('aria-pressed', 'true');
  await expect(map.locator('.marker.selected')).toHaveCount(1);
  await map.locator('summary').click();
  await page.evaluate(() => { window.fixtureCard.revision++; });
  await expect(map.locator('details')).not.toHaveAttribute('open');
  await map.locator('summary').click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze(); expect(axe.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('map-mobile.png'), fullPage: true });
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  await expect(map.getByText('Saved position · stale', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await page.evaluate(() => { const card = window.fixtureCard; card.hass = { ...card.hass, states: { ...card.hass.states, 'switch.f1_demo_spoilers': { state: 'on', attributes: {} } } }; });
  await expect(page.getByText('Spoiler protection is active.', { exact: true })).toBeVisible();
  await expect(map).toHaveCount(0);
});

test('map renders migrated session, lap, track-status, layout and footer choices', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'map', options: {
    layout_mode: 'full', show_footer: true, show_session_info: true, show_lap_progress: true,
    show_track_status: true, track_status_line_mode: 'full',
  } }] } }));
  const map = page.locator('f1-track-map-view');
  await expect(map.locator('.map-shell.full')).toBeVisible();
  await expect(map.getByText('Demo Grand Prix · Race', { exact: true })).toBeVisible();
  await expect(map.getByText('Lap 12 / 53', { exact: true })).toBeVisible();
  await expect(map.getByText('Track: Clear', { exact: true })).toBeVisible();
  await expect(map.locator('.track.status-full')).toHaveCount(1);
  await expect(map.locator('.map-footer')).toContainText('Live positions');
  await page.evaluate(() => { const card = window.fixtureCard; card.setConfig({ modules: [{ type: 'map', options: {
    layout_mode: 'compact', show_footer: false, show_session_info: false, show_lap_progress: false,
    show_track_status: false, track_status_line_mode: 'off',
  } }] }); });
  await expect(map.locator('.map-shell.compact')).toBeVisible();
  await expect(map.locator('.map-meta')).toHaveCount(0);
  await expect(map.locator('.map-footer')).toHaveCount(0);
  await expect(map.locator('.track-status-accent')).toHaveCount(0);
  await expect(map.locator('.track.status-full')).toHaveCount(0);
});

test('map interpolates new positions and snaps when reduced motion is requested', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'map' }] } }));
  const map = page.locator('f1-track-map-view');
  await expect(map).toBeVisible();
  const movement = await map.evaluate(async view => {
    await view.updateComplete;
    const rowIndex = view.model.rows.filter(row => row.point && row.point.every(value => value >= 0 && value <= 100)).findIndex(row => row.id === '16');
    const marker = () => view.shadowRoot.querySelectorAll('.marker')[rowIndex].getAttribute('transform');
    const initial = marker();
    const model = structuredClone(view.model);
    const row = model.rows.find(item => item.id === '16');
    row.point = [Math.min(95, row.point[0] + 15), Math.min(95, row.point[1] + 15)];
    const target = `translate(${row.point[0]} ${row.point[1]})`;
    view.model = model;
    await view.updateComplete;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    return { initial, target, current: marker(), duration: view.motions.get('16').duration };
  });
  expect(movement.current).not.toBe(movement.initial);
  expect(movement.current).not.toBe(movement.target);
  expect(movement.duration).toBeGreaterThanOrEqual(850);
  await expect.poll(() => map.evaluate(node => {
    const rowIndex = node.model.rows.filter(row => row.point && row.point.every(value => value >= 0 && value <= 100)).findIndex(row => row.id === '16');
    return node.shadowRoot.querySelectorAll('.marker')[rowIndex].getAttribute('transform');
  })).toBe(movement.target);

  const refreshedMovement = await map.evaluate(async view => {
    view.model = structuredClone(view.model);
    await view.updateComplete;
    view.model = structuredClone(view.model);
    await view.updateComplete;
    const model = structuredClone(view.model), row = model.rows.find(item => item.id === '16');
    row.point = [Math.max(5, row.point[0] - 5), Math.max(5, row.point[1] - 5)];
    view.model = model;
    await view.updateComplete;
    return view.motions.get('16').duration;
  });
  expect(refreshedMovement).toBeGreaterThanOrEqual(850);

  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, accessibility: { ...card.config.accessibility, motion: 'reduced' } });
  });
  const snapped = await map.evaluate(async view => {
    await view.updateComplete;
    const model = structuredClone(view.model), row = model.rows.find(item => item.id === '16');
    row.point = [Math.max(5, row.point[0] - 10), Math.max(5, row.point[1] - 10)];
    const target = `translate(${row.point[0]} ${row.point[1]})`;
    view.model = model;
    await view.updateComplete;
    const rowIndex = view.model.rows.filter(item => item.point && item.point.every(value => value >= 0 && value <= 100)).findIndex(item => item.id === '16');
    return { target, current: view.shadowRoot.querySelectorAll('.marker')[rowIndex].getAttribute('transform') };
  });
  expect(snapped.current).toBe(snapped.target);
});

test('live map becomes stale on its deadline, handles new sessions and releases its subscriber without replay actions', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-13T13:30:00Z') });
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'map' }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    window.mapRequests = []; window.mapUnsubscribed = 0; window.mapServices = 0;
    card.entries = demo.preview.entries; card.previewData = null;
    card.hass = { ...demo.hass, connection: { subscribeEvents: async () => () => {}, subscribeMessage: async (callback, message) => {
      window.mapRequests.push(message); window.mapCallback = callback;
      callback({ protocol_version: 2, type: 'snapshot', entry_id: 'demo', sequence: 1, geometry_revision: 1, snapshot: demo.preview.map });
      return () => window.mapUnsubscribed++;
    } }, callWS: async () => demo.preview.entries, callService: () => window.mapServices++ };
  });
  const map = page.locator('f1-track-map-view');
  await expect(map.locator('.marker')).toHaveCount(5);
  expect(await page.evaluate(() => window.mapRequests.map(item => item.type))).toEqual(['f1_sensor/track_map/subscribe']);
  await page.clock.fastForward(10_001);
  await expect(map.getByText('Saved positions · updates delayed', { exact: true })).toBeVisible();
  await expect(map.locator('.marker.stale')).toHaveCount(5);
  await page.evaluate(() => window.mapCallback({ protocol_version: 2, type: 'delta', entry_id: 'demo', sequence: 2, base_sequence: 1, changes: {}, removed: [], patch: { session: { session_key: 'next' }, track: null } }));
  await expect(map.locator('.marker')).toHaveCount(0);
  await expect(map.getByText('No driver positions are available.', { exact: false })).toBeVisible();
  await page.evaluate(() => window.fixtureCard.setConfig({ modules: [{ type: 'overview' }] }));
  await expect.poll(() => page.evaluate(() => window.mapUnsubscribed)).toBe(1);
  expect(await page.evaluate(() => window.mapServices)).toBe(0);
});

test('map editor controls labels and orientation and map-only mode keeps the text alternative available', async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'map', fields: ['track_map'] }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByLabel('Driver labels', { exact: true }).selectOption('number');
  await editor.getByLabel('Orientation', { exact: true }).selectOption('raw');
  const map = page.locator('#native-preview f1-track-map-view');
  await expect(map.locator('.marker text').filter({ hasText: /^16$/ })).toBeVisible();
  await expect(map.locator('details')).not.toHaveAttribute('open');
  await map.locator('summary').click();
  await expect(map.getByRole('button', { name: /16 · LEC/ })).toBeVisible();
  expect(await page.evaluate(() => window.savedConfig.modules[0].options)).toMatchObject({ labels: 'number', orientation: 'raw' });
  await editor.getByLabel('Driver labels', { exact: true }).selectOption('off');
  await expect(map.locator('.marker text')).toHaveCount(0);
  await expect(map.getByText('Driver labels are hidden.', { exact: false })).toBeAttached();
  await map.locator('summary').click();
  await expect(map.getByRole('button', { name: /16 · LEC/ })).toBeVisible();
  expect(await page.evaluate(() => window.savedConfig.modules[0].options.labels)).toBe('off');
  await editor.getByLabel('Show driver count', { exact: true }).uncheck();
  await expect(map.locator('summary')).toHaveText('Driver positions and status');
});

test('battle views distinguish estimates, preserve start/end history and expose accessible position changes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => window.mountModular({ config: { modules: [
    { type: 'battles', title: 'Current battles' },
    { type: 'battles', title: 'Recorded battles', options: { content: 'battle_history', presentation: 'table' } },
    { type: 'battles', title: 'Position observations', options: { content: 'position_exchanges' } },
  ] } }));
  await expect(page.getByText('Active battle estimate', { exact: true })).toBeVisible();
  await expect(page.getByText('Battle started', { exact: true })).toBeVisible();
  await expect(page.getByText('Battle ended', { exact: true })).toBeVisible();
  await expect(page.getByText('Position exchange', { exact: true })).toBeVisible();
  await expect(page.getByText('Likely on-track overtake', { exact: true })).toHaveCount(0);
  await expect(page.getByText('LEC: 1 → 2', { exact: true })).toBeVisible();
  await expect(page.getByText('NOR: 2 → 1', { exact: true })).toBeVisible();
  await expect(page.getByText('Pit stop context', { exact: false })).toBeVisible();
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze(); expect(axe.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.emulateMedia({ forcedColors: 'active' });
  await expect(page.getByText('Position exchange', { exact: true })).toBeVisible();
});

test('battle editor switches useful starter fields and applies evidence filters without changing backend analysis', async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: true, config: { modules: [{ type: 'battles' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByLabel('Observations', { exact: true }).selectOption('position_exchanges');
  await expect(editor.getByRole('checkbox', { name: 'Before → after', exact: true })).toBeChecked();
  await expect(page.locator('#native-preview f1-sensor-card').getByText('LEC: 1 → 2', { exact: true })).toBeVisible();
  await editor.getByLabel('Minimum evidence score (%)', { exact: true }).fill('70');
  await editor.getByLabel('Minimum evidence score (%)', { exact: true }).press('Tab');
  await expect(page.locator('#native-preview f1-sensor-card').getByText('No matching observations for this session.', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.savedConfig.modules[0].options.minimum_score)).toBe(70);
});

test('strategy comparison views preserve uncertainty, compound graphics and accessible underlying values', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => window.mountModular({ config: { modules: [
    { type: 'strategy', options: { content: 'teammates' }, driver: 'HAM' },
    { type: 'strategy', options: { content: 'crossover' } },
    { type: 'strategy', options: { content: 'pit_outcomes' } },
  ] } }));
  await expect(page.getByText('HAM: 1:21.320', { exact: true })).toBeVisible();
  await expect(page.getByText('0.200 s', { exact: true })).toBeVisible();
  await expect(page.getByText('8.5 laps', { exact: true })).toBeVisible();
  await expect(page.getByText('5–12 laps', { exact: true })).toBeVisible();
  await expect(page.getByText('Undercut observed', { exact: true })).toBeVisible();
  await expect(page.getByText('HAM: 10', { exact: true })).toBeVisible();
  await expect(page.getByText('HAM: 3 → 2', { exact: true })).toBeVisible();
  await page.locator('.analysis-explanation summary').nth(1).click();
  await expect(page.getByText('It is not a recommended pit-stop lap.', { exact: false })).toBeVisible();
  await page.locator('.analysis-explanation summary').nth(1).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze(); expect(axe.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('strategy-comparisons-mobile.png'), fullPage: true });
});

test('strategy editor exposes relevant comparison fields and quality controls while preserving the selected content', async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: true, config: { modules: [{ type: 'strategy' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByLabel('Minimum clean laps per row', { exact: true }).fill('10');
  await editor.getByLabel('Minimum clean laps per row', { exact: true }).press('Tab');
  await expect(page.locator('#native-preview f1-sensor-card').getByText('No estimates meet the selected evidence and sample requirements.', { exact: true })).toBeVisible();
  await editor.getByLabel('Analysis content', { exact: true }).selectOption('crossover');
  await expect(editor.getByRole('checkbox', { name: 'Observed tyre-age range', exact: true })).toBeChecked();
  await expect(editor.getByLabel('Minimum clean laps per row', { exact: true })).toHaveCount(0);
  await expect(editor.getByLabel('Pinned driver', { exact: true })).toHaveCount(0);
  await expect(page.locator('#native-preview f1-sensor-card').getByText('8.5 laps', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.savedConfig.modules[0].options)).toMatchObject({ content: 'crossover', minimum_clean_laps: 10 });
});

test('stint graphics use observed lap extents, show coverage without color and retain missing ranges as text', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'strategy', options: { presentation: 'chart' } }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    demo.preview.analysis.strategy.stints[0].first_lap = null;
    demo.preview.analysis.strategy.stints[1].first_lap = 5;
    card.previewData = { ...demo.preview };
  });
  await expect(page.locator('.stint-bars li')).toHaveCount(5);
  await expect(page.locator('.stint-bar')).toHaveCount(4);
  await expect(page.getByText('Lap range unavailable', { exact: true })).toBeVisible();
  await expect(page.getByText('Clean: 6 · Recorded: 8 · Excluded: 2', { exact: true })).toHaveCount(5);
  await expect(page.locator('.stint-bars [data-stint$=":4:0"] .stint-bar')).toHaveAttribute('style', /left:50%;width:50%/);
  await page.getByRole('button', { name: 'Show data table', exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'Median clean pace', exact: true })).toBeVisible();
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze(); expect(axe.violations).toEqual([]);
  await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' });
  await expect(page.getByText('Lap range unavailable', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('stint-graphics-forced-colors.png'), fullPage: true });
});

test('Race Control editor offers a compact latest view and driver focus keeps global messages as an explicit choice', async ({ page }) => {
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.evaluate(() => window.mountModular({ editor: true, nativePreview: true, config: { modules: [{ type: 'race_control', driver: 'NOR' }] } }));
  const editor = page.locator('f1-sensor-card-editor'), card = page.locator('#native-preview f1-sensor-card');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByLabel('Message view', { exact: true }).selectOption('latest_message');
  await expect(editor.getByLabel('Messages to show', { exact: true })).toHaveCount(0);
  await expect(card.getByText('TRACK CLEAR', { exact: true })).toBeVisible();
  await expect(card.locator('.events li')).toHaveCount(1);
  await editor.getByLabel('Session-wide messages with driver focus', { exact: true }).selectOption('hide');
  await expect(card.getByText('CAR 4 · TRACK LIMITS AT TURN 7 · LAP TIME DELETED', { exact: true })).toBeVisible();
  await expect(card.getByText('TRACK CLEAR', { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => window.savedConfig.modules[0].options)).toMatchObject({ presentation: 'latest_message', global_messages: 'hide' });
});

test('Race Control retains legacy filters, list height and FIA visibility', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'race_control', options: {
      presentation: 'list', list_max_height: 240, hide_blue_flags: true,
      hide_track_limits: true, show_fia_logo: true,
    } }] } });
    window.fixtureCard.previewData = { ...window.fixtureDemo.preview, events: [...window.fixtureDemo.preview.events,
      { event_id: 'blue', utc: '2026-09-13T13:30:00Z', category: 'Flag', flag: 'BLUE', message: 'BLUE FLAG' }] };
  });
  const control = page.getByRole('region', { name: 'Race Control', exact: true });
  await expect(control.getByText('TRACK CLEAR', { exact: true })).toBeVisible();
  await expect(control.getByText(/TRACK LIMITS/)).toHaveCount(0);
  await expect(control.getByText('BLUE FLAG', { exact: true })).toHaveCount(0);
  await expect(control.getByText('FIA', { exact: true })).toBeVisible();
  await expect(control.locator('ol.events')).toHaveAttribute('style', /max-height:240px/);
  await page.evaluate(() => { const config = structuredClone(window.fixtureCard.config); Object.assign(config.modules[0].options, { hide_blue_flags: false, hide_track_limits: false, show_fia_logo: false }); window.fixtureCard.setConfig(config); });
  await expect(control.getByText(/TRACK LIMITS/)).toBeVisible();
  await expect(control.getByText('BLUE FLAG', { exact: true })).toBeVisible();
  await expect(control.getByText('FIA', { exact: true })).toHaveCount(0);
});

test('Race Control latest messages honor their minimum display time', async ({ page }) => {
  await page.clock.install();
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'race_control', options: { presentation: 'latest_message', min_display_time: 5 } }] } }));
  const control = page.getByRole('region', { name: 'Race Control', exact: true });
  await expect(control.getByText('TRACK CLEAR', { exact: true })).toBeVisible();
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.previewData = { ...card.previewData, events: [{ event_id: 'new-message', utc: '2026-09-13T13:30:01Z', category: 'SafetyCar', message: 'SAFETY CAR DEPLOYED' }, ...card.previewData.events] };
  });
  await expect(control.getByText('TRACK CLEAR', { exact: true })).toBeVisible();
  await expect(control.getByText('SAFETY CAR DEPLOYED', { exact: true })).toHaveCount(0);
  await page.clock.fastForward(4000);
  await expect(control.getByText('TRACK CLEAR', { exact: true })).toBeVisible();
  await page.clock.fastForward(1000);
  await expect(control.getByText('SAFETY CAR DEPLOYED', { exact: true })).toBeVisible();
});

test('Race Control clear requires confirmation and targets only the discovered entity', async ({ page }) => {
  await page.clock.install();
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'race_control', options: { presentation: 'list', show_clear_button: true } }] } });
    window.serviceCalls = [];
  });
  const control = page.getByRole('region', { name: 'Race Control', exact: true });
  const clear = control.getByRole('button', { name: 'Clear saved messages', exact: true });
  await expect(clear).toBeDisabled();
  await page.evaluate(() => {
    const card = window.fixtureCard, demo = window.fixtureDemo, connection = { connected: true, subscribeEvents: async () => () => {} };
    card.previewData = null; card.entries = demo.preview.entries; card.eventState = { status: 'connected', data: demo.preview.events };
    card.hass = { ...demo.hass, connection, callService: async (...args) => { window.serviceCalls.push(args); } };
    card.connection = connection; card.eventKey = demo.preview.entries[0].entities.race_control;
  });
  await expect(clear).toBeEnabled();
  await clear.click();
  await expect(control.getByRole('button', { name: 'Confirm clear', exact: true })).toBeVisible();
  await page.clock.fastForward(5000);
  await expect(clear).toBeVisible();
  await clear.click();
  await control.getByRole('button', { name: 'Confirm clear', exact: true }).click();
  await expect(control.getByText('No matching messages yet.', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.serviceCalls)).toEqual([['f1_sensor', 'clear_race_control_log', { entity_id: 'sensor.f1_demo_race_control' }]]);
});

test('overview clocks show backend pause and separate meanings, remain stationary without pushes and obey spoiler protection', async ({ page }) => {
  await page.clock.install();
  await page.evaluate(() => window.mountModular({ scene: 'replay', config: { modules: [{ type: 'overview', fields: ['session_time_elapsed', 'session_time_remaining', 'race_time_to_three_hour_limit'] }] } }));
  await expect(page.getByText('0:30:00', { exact: true })).toBeVisible();
  await expect(page.getByText('1:30:00', { exact: true })).toBeVisible();
  await expect(page.getByText('2:30:00', { exact: true })).toBeVisible();
  await expect(page.getByText('Paused · Official clock', { exact: true })).toHaveCount(2);
  await expect(page.getByText('From race start · includes session interruptions · Replay paused', { exact: true })).toBeVisible();
  await page.clock.fastForward(60_000);
  await expect(page.getByText('0:30:00', { exact: true })).toBeVisible();
  await page.evaluate(() => { const card = window.fixtureCard; card.hass = { ...card.hass, states: { ...card.hass.states, 'switch.f1_demo_spoilers': { state: 'on', attributes: {} } } }; });
  await expect(page.getByText('Spoiler protection is active.', { exact: true })).toHaveCount(3);
  await expect(page.getByText('0:30:00', { exact: true })).toHaveCount(0);
});

test('overview renders migrated Live Session lap progress, layout and flag visibility', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ config: {
    appearance: { flags: false },
    modules: [{ type: 'overview', fields: ['meeting', 'lap_progress'], options: { layout_mode: 'compact' } }],
  } }));
  const overview = page.locator('.overview.compact');
  await expect(overview).toBeVisible();
  await expect(overview.getByText('Lap progress', { exact: true })).toBeVisible();
  await expect(overview.getByText('12 / 53', { exact: true })).toBeVisible();
  await expect(overview.locator('img.flag')).toHaveCount(0);
});

test('Next Race overview retains the circuit map, history and circuit-time schedule', async ({ page }) => {
  await page.route('https://flagcdn.com/**', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="27"><rect width="40" height="27" fill="green"/></svg>' }));
  await page.evaluate(() => window.mountModular({ config: { modules: [
    { type: 'overview', fields: ['meeting', 'circuit_map', 'circuit_history'] },
    { type: 'calendar', options: { show_track_time: true } },
  ] } }));
  const overview = page.getByRole('region', { name: 'Overview', exact: true });
  await expect(overview.getByRole('region', { name: 'Circuit map', exact: true }).locator('img')).toHaveAttribute('src', 'https://example.com/demo-circuit-map.webp');
  const history = overview.getByRole('region', { name: 'Circuit history', exact: true });
  await expect(history.getByText('Charles Leclerc · Ferrari · 2025', { exact: true }).first()).toBeVisible();
  await expect(history.getByText('60%', { exact: true })).toBeVisible();
  await expect(history.getByText('Last podium · 2025', { exact: true })).toBeVisible();
  const schedule = page.getByRole('region', { name: 'Schedule', exact: true });
  await expect(schedule.getByText('Circuit time · Europe/Rome', { exact: true })).toHaveCount(5);
  await expect(schedule.locator('img.flag')).toHaveCount(0);
  const flag = overview.locator('.hero img.flag');
  await expect(flag).toBeVisible();
  for (const width of [360, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    const flagBox = await flag.boundingBox();
    const nameBox = await overview.locator('.hero strong').boundingBox();
    expect(Math.abs(flagBox.y + flagBox.height / 2 - nameBox.y - nameBox.height / 2)).toBeLessThan(1);
  }
});


test('weather profiles expose distinct data, a real rain indicator and a compact accessible mobile view', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 360, height: 1000 });
  await page.evaluate(() => window.mountModular({ config: { modules: [
    { type: 'weather', options: { content: 'current_conditions' } },
    { type: 'weather', options: { content: 'race_forecast' } },
    { type: 'weather', fields: ['temperature', 'track_temperature', 'rainfall', 'wind_direction'], options: { content: 'track_conditions', presentation: 'compact_list' } },
  ] } }));
  const current = page.getByRole('region', { name: 'Current circuit weather', exact: true });
  const forecast = page.getByRole('region', { name: 'Race-start forecast', exact: true });
  const track = page.getByRole('region', { name: 'Track weather observations', exact: true });
  await expect(current.getByText('24.5 °C', { exact: true })).toBeVisible();
  await expect(forecast.getByText('22.8 °C', { exact: true })).toBeVisible();
  await expect(forecast.getByText('0.4 mm', { exact: true })).toBeVisible();
  await expect(track.getByText('No rain detected', { exact: true })).toBeVisible();
  await expect(track.getByRole('definition').filter({ hasText: '225°' })).toBeVisible();
  await expect(track.getByText(/mm/)).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const audit = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(audit.violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('weather-mobile.png'), fullPage: true });
  await page.evaluate(() => { const demo = window.fixtureDemo; demo.hass.states[demo.preview.entries[0].entities.track_weather].attributes.rainfall = null; window.fixtureCard.hass = { ...demo.hass }; });
  await expect(track.getByText('No rain detected', { exact: true })).toHaveCount(0);
  await page.evaluate(() => { const card = window.fixtureCard; card.setConfig({ ...card.config, context: { ...card.config.context, spoilers: 'hide' } }); });
  await expect(track.getByText('Spoiler protection is active.', { exact: true })).toBeVisible();
  await expect(forecast.getByText('22.8 °C', { exact: true })).toBeVisible();
});

test('weather conditions fill the spare row and icons support color, monochrome and text', async ({ page }) => {
  await page.setViewportSize({ width: 520, height: 1000 });
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'weather', fields: ['temperature', 'humidity', 'wind', 'weather_condition'], options: { content: 'current_conditions' } }] } }));
  const condition = page.locator('.weather-item').filter({ hasText: 'Partly cloudy' });
  const icon = condition.locator('ha-icon');
  await expect(icon).toHaveAttribute('icon', 'mdi:weather-partly-cloudy');
  await expect(icon).toHaveCSS('color', 'rgb(213, 154, 36)');
  const conditionBox = await condition.boundingBox();
  const rowBox = await page.locator('dl.overview').boundingBox();
  expect(conditionBox.width).toBeCloseTo(rowBox.width, 0);
  const textLines = await condition.locator('.weather-condition-text').evaluate(el => {
    const range = document.createRange(); range.selectNodeContents([...el.childNodes].find(node => node.nodeType === Node.TEXT_NODE && node.textContent.includes('Partly cloudy')));
    return range.getClientRects().length;
  });
  expect(textLines).toBe(1);
  const iconBox = await icon.boundingBox();
  const textBox = await condition.locator('.weather-condition-text').boundingBox();
  expect(Math.abs(iconBox.y + iconBox.height / 2 - textBox.y - textBox.height / 2)).toBeLessThan(1);
  await page.evaluate(() => { const card = window.fixtureCard; const config = structuredClone(card.config); config.modules[0].options.colored_icons = false; card.setConfig(config); });
  expect(await icon.evaluate(el => getComputedStyle(el).color === getComputedStyle(el.parentElement).color)).toBe(true);
  await page.setViewportSize({ width: 320, height: 1000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => { const card = window.fixtureCard; const config = structuredClone(card.config); config.accessibility.signals = 'text'; card.setConfig(config); });
  await expect(condition.locator('ha-icon')).toHaveCount(0);
  await expect(condition).toContainText('Partly cloudy');
});

test('weather editor changes source and presentation without losing custom fields on reload', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1000 });
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'weather' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByLabel('Weather source', { exact: true }).selectOption('track_conditions');
  await editor.getByLabel('Weather layout', { exact: true }).selectOption('compact_list');
  await expect(editor.getByRole('checkbox', { name: 'Colored weather icons', exact: true })).toBeChecked();
  await editor.getByRole('checkbox', { name: 'Colored weather icons', exact: true }).uncheck();
  await expect(editor.getByRole('checkbox', { name: 'Track temperature', exact: true })).toBeChecked();
  await editor.getByRole('checkbox', { name: 'Wind from', exact: true }).check();
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.modules[0].fields).toContain('wind_direction');
  expect(saved.modules[0].options.colored_icons).toBe(false);
  await editor.getByLabel('Weather source', { exact: true }).selectOption('race_forecast');
  expect(await page.evaluate(() => window.savedConfig.modules[0].fields)).toEqual(saved.modules[0].fields);
  await page.reload(); await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.getByText('No rain detected', { exact: true })).toBeVisible();
  await expect(page.locator('dl.weather-list')).toBeVisible();
});

test('track-limit summary renders per-driver warnings as text and survives an editor round trip', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1000 });
  await page.evaluate(() => window.mountModular({ editor: true, config: { modules: [{ type: 'incidents' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByLabel('Incident content', { exact: true }).selectOption('track_limits_summary');
  await expect(editor.getByRole('checkbox', { name: 'Deleted times', exact: true })).toBeChecked();
  await expect(editor.getByLabel('Summary order', { exact: true })).toBeVisible();
  await editor.getByRole('checkbox', { name: 'Latest recorded event', exact: true }).check();
  const saved = await page.evaluate(() => window.savedConfig);
  await page.reload(); await page.waitForFunction(() => window.modularReady);
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.getByRole('columnheader', { name: 'Deleted times', exact: true })).toBeVisible();
  await expect(page.locator('tr[data-driver="4"]').getByRole('cell').filter({ hasText: 'Warning recorded' })).toBeVisible();
  await expect(page.getByText('No penalty recorded', { exact: true })).toHaveCount(1);
  await expect(page.locator('tr[data-driver="4"]')).toContainText('NOR');
  await page.emulateMedia({ forcedColors: 'active' });
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(axe.violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});


test('lap charts show source gaps, keep isolated samples visible and provide the same lap times in an accessible table', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'lap_chart', options: { selected: ['16'] } }] } });
    const d = window.fixtureDemo, e = d.preview.entries[0], driver = d.hass.states[e.entities.driver_positions].attributes.drivers[0];
    driver.completed_laps = 130;
    driver.laps = Object.fromEntries(Array.from({ length: 130 }, (_, i) => [i + 1, 81.5 + (i % 5) / 10]));
    delete driver.laps[109]; delete driver.laps[111];
    window.fixtureCard.hass = { ...d.hass };
  });
  const chart = page.locator('f1-series-chart');
  await expect(chart.getByRole('img')).toBeVisible();
  await expect(chart.locator('[data-series="16"] .series-line')).toHaveCount(3);
  const isolatedIsVisible = await chart.evaluate(node => {
    const group = node.shadowRoot.querySelector('[data-series="16"]');
    const path = [...group.querySelectorAll('.series-line')].find(node => !node.getAttribute('d').includes('L'));
    const [x, y] = path.getAttribute('d').slice(1).split(',').map(Number);
    return [...group.querySelectorAll('circle.marker')].some(node => Number(node.getAttribute('cx')) === x && Number(node.getAttribute('cy')) === y);
  });
  expect(isolatedIsVisible).toBe(true);
  expect(await chart.locator('[data-series="16"] .marker').count()).toBeLessThan(80);
  await chart.getByRole('button', { name: 'Show data table', exact: true }).click();
  await expect(chart.getByRole('columnheader', { name: 'Lap', exact: true })).toBeVisible();
  await expect(chart.getByRole('row').filter({ has: page.getByRole('rowheader', { name: '109', exact: true }) })).toContainText('—');
  await expect(chart.getByRole('row').filter({ has: page.getByRole('rowheader', { name: '110', exact: true }) })).toContainText('1:21.900');
  await chart.getByRole('button', { name: 'Hide data table', exact: true }).click();
  const axe = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(axe.violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('lap-history-mobile.png'), fullPage: true });
});

test('lap chart editor saves driver, measure and lap interval without requiring YAML', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 1000 });
  await page.evaluate(() => { window.mountModular({ editor: true, config: { modules: [{ type: 'lap_chart' }] } }); window.fixtureCard.entries = window.fixtureDemo.preview.entries; });
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Module options', { exact: true }).click();
  await editor.getByLabel('Measure', { exact: true }).selectOption('lap_change');
  await editor.getByRole('checkbox', { name: 'Charles Leclerc', exact: true }).check();
  await editor.getByLabel('First lap (0 = first observed)', { exact: true }).fill('11');
  await editor.getByLabel('First lap (0 = first observed)', { exact: true }).press('Tab');
  await editor.getByLabel('Presentation', { exact: true }).selectOption('table');
  const saved = await page.evaluate(() => window.savedConfig);
  expect(saved.modules[0].options).toMatchObject({ selected: ['16'], metric: 'lap_change', start_lap: 11, presentation: 'table' });
  await page.reload(); await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config }), saved);
  await expect(page.getByRole('cell', { name: '-0.443 s', exact: true })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Charles Leclerc', exact: true })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Lando Norris', exact: true })).toHaveCount(0);
});

test('replay controls are inert in previews and only explicit actions affect the discovered player', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.evaluate(() => { window.mountModular({ scene: 'replay', config: { modules: [{ type: 'replay' }] } }); window.replayCalls = []; window.fixtureCard.hass = { ...window.fixtureDemo.hass, connection: { connected: true, subscribeEvents: async () => () => {} }, callWS: async () => window.fixtureDemo.preview.entries, callService: async (...args) => window.replayCalls.push(args) }; });
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeDisabled();
  await expect(page.getByText('From replay start: 0:30:00 / 2:00:00', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => window.replayCalls)).toEqual([]);
  await page.evaluate(() => { window.fixtureCard.entries = window.fixtureDemo.preview.entries; window.fixtureCard.previewData = null; });
  await page.getByRole('button', { name: 'Play replay', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.replayCalls.length)).toBe(1);
  expect(await page.evaluate(() => window.replayCalls[0])).toEqual(['media_player', 'media_play', { entity_id: 'media_player.f1_demo_replay_player' }]);
  await page.getByRole('button', { name: 'Back 30 s', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.replayCalls.length)).toBe(2);
  expect(await page.evaluate(() => window.replayCalls[1][2].seek_position)).toBe(1770);
  const seek = page.getByRole('slider', { name: 'Replay position in seconds', exact: true });
  await seek.focus(); await seek.press('Home');
  await expect(seek).toHaveAttribute('aria-valuetext', '0:00:00');
  expect(await page.evaluate(() => window.replayCalls.length)).toBe(2);
  await page.getByRole('button', { name: 'Go to replay position', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.replayCalls.length)).toBe(3);
  expect(await page.evaluate(() => window.replayCalls[2][2].seek_position)).toBe(0);
  await page.getByRole('button', { name: 'Freeze view', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Resume', exact: true }).click();
  await page.getByText('Choose replay', { exact: true }).click();
  await expect(page.getByLabel('Replay year', { exact: true })).toBeDisabled();
  await expect(page.getByText('Stop the loaded replay before changing its year, session or start reference.', { exact: true })).toBeVisible();
  await page.getByText('Choose replay', { exact: true }).click();
  const audit = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(audit.violations.filter(item => ['serious', 'critical'].includes(item.impact))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('replay-controls-mobile.png'), fullPage: true });
  await page.evaluate(() => { const card = window.fixtureCard; card.setConfig({ ...card.config, appearance: { ...card.config.appearance, style: 'minimal' } }); card.remove(); document.querySelector('#root').append(card); });
  expect(await page.evaluate(() => window.replayCalls.length)).toBe(3);
});

test('replay loading blocks duplicate clicks, reports service failures and rejects commands from a previous session', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'replay' }] } });
    const d = window.fixtureDemo, e = d.preview.entries[0], status = d.hass.states[e.entities.replay_status];
    status.state = 'selected'; status.attributes.selected_session = 'Demo Grand Prix · Race';
    const card = window.fixtureCard; card.entries = d.preview.entries; card.previewData = null;
    window.replayCalls = [];
    card.hass = { ...d.hass, connection: { connected: true, subscribeEvents: async () => () => {} }, callWS: async () => d.preview.entries, callService: (...args) => { window.replayCalls.push(args); return new Promise((_resolve, reject) => { window.rejectReplay = reject; }); } };
  });
  await page.getByText('Choose replay', { exact: true }).click();
  await page.getByRole('button', { name: 'Load selected replay', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Load selected replay', exact: true })).toBeDisabled();
  await expect(page.getByLabel('Replay year', { exact: true })).toBeDisabled();
  expect(await page.evaluate(() => window.replayCalls)).toEqual([['button', 'press', { entity_id: 'button.f1_demo_replay_load' }]]);
  await page.evaluate(() => window.rejectReplay(new Error('test service failure')));
  await expect(page.getByRole('alert')).toContainText('The replay command failed');
  await page.evaluate(() => {
    const card = window.fixtureCard, view = [...card.moduleNodes.values()][0], context = view.model.controlContext;
    card.hass.states[card.entry.entities.replay_status].attributes.selected_session = 'Another session';
    view.dispatchEvent(new CustomEvent('f1-replay-action', { detail: { module: view.module.id, action: 'load', context } }));
  });
  expect(await page.evaluate(() => window.replayCalls.length)).toBe(1);
});

test('compact replay visibility choices retain essential accessible controls', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ scene: 'replay', config: { modules: [{ type: 'replay', options: {
    display: 'compact', secondary_selects: false, start_reference: false,
    seek_controls: false, refresh: false, status_details: false,
  } }] } }));
  await expect(page.getByText(/Controls replay for/)).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Play replay', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Back 30 s', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Forward 30 s', exact: true })).toHaveCount(0);
  await expect(page.getByRole('slider', { name: 'Replay position in seconds', exact: true })).toHaveCount(0);
  await expect(page.getByRole('progressbar', { name: 'Replay progress', exact: true })).toBeVisible();
  await page.getByText('Choose replay', { exact: true }).click();
  await expect(page.getByLabel('Recorded session', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Replay year', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Start reference', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Refresh session list', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Load selected replay', exact: true })).toBeVisible();
  await page.evaluate(() => window.mountModular({ scene: 'replay', editor: true, config: { modules: [{ type: 'replay', options: {
    display: 'compact', secondary_selects: false, start_reference: false,
    seek_controls: false, refresh: false, status_details: false,
  } }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.locator('summary').filter({ hasText: /^Module options$/ }).click();
  await expect(editor.getByLabel('Replay layout', { exact: true })).toHaveValue('compact');
  for (const label of ['Show year and reference choices', 'Show start reference', 'Show seek controls', 'Show refresh action', 'Show scope details']) {
    await expect(editor.getByRole('checkbox', { name: label, exact: true })).not.toBeChecked();
  }
});

test('replay button labels can be hidden without hiding accessible action names', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ scene: 'replay', config: { modules: [{ type: 'replay', options: { show_button_labels: false } }] } }));
  const play = page.getByRole('button', { name: 'Play replay', exact: true });
  const back = page.getByRole('button', { name: 'Back 30 s', exact: true });
  await expect(play).toBeVisible();
  await expect(back).toBeVisible();
  await expect(play.locator('.sr')).toHaveText('Play replay');
  await expect(back.locator('.sr')).toHaveText('Back 30 s');
  await expect(play).toHaveClass(/icon-only/);
  await expect(back).toHaveClass(/icon-only/);
});

test('historical archive shows lap gaps, inverted positions and accessible data on mobile', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 360, height: 900 });
  await page.evaluate(() => window.mountModular({ config: { modules: [{ type: 'archive', options: { year: 2024, content: 'lap_position', presentation: 'both', selected: ['demo-driver-16', 'demo-driver-4'] } }] } }));
  await expect(page.getByRole('heading', { name: 'Historical archive' })).toBeVisible();
  await expect(page.getByText('Position at lap completion', { exact: true }).first()).toBeVisible();
  await expect(page.locator('f1-series-chart tbody tr')).toHaveCount(12);
  await expect(page.getByText(/not simultaneous track positions/)).toBeVisible();
  const ys = await page.locator('f1-series-chart [data-series="demo-driver-16"] .marker').evaluateAll(nodes => nodes.map(node => Number(node.getAttribute('cy'))));
  expect(ys[0]).toBeGreaterThan(ys[4]);
  await page.evaluate(() => {
    const card = window.fixtureCard, config = structuredClone(card.config);
    Object.assign(config.modules[0].options, { show_points: false, show_round_labels: false, chart_height: 700 });
    card.setConfig(config);
  });
  await expect(page.locator('f1-series-chart svg.plot')).toHaveAttribute('viewBox', / 700$/);
  await expect(page.locator('f1-series-chart svg.plot .marker')).toHaveCount(0);
  await expect(page.locator('f1-series-chart svg.plot .round-label')).toHaveCount(0);
  await page.getByRole('combobox', { name: 'Session', exact: true }).selectOption('demo:2024:2:qualifying');
  await expect(page.getByText('Historical lap times and positions are available for races only.')).toBeVisible();
  await expect(page.locator('f1-series-chart')).toHaveCount(0);
  await page.getByRole('combobox', { name: 'Session', exact: true }).selectOption('demo:2024:2:race');
  await page.emulateMedia({ forcedColors: 'active' });
  const accessibility = await new AxeBuilder({ page }).include('f1-sensor-card').analyze();
  expect(accessibility.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.emulateMedia({ forcedColors: 'none' });
  await page.screenshot({ path: testInfo.outputPath('archive-mobile.png'), fullPage: true });
  await page.evaluate(() => {
    const card = window.fixtureCard, config = structuredClone(card.config);
    config.modules[0].options.show_session_selector = false;
    card.setConfig(config);
  });
  await expect(page.getByRole('combobox', { name: 'Year', exact: true })).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'Grand Prix', exact: true })).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'Session', exact: true })).toHaveCount(0);
});

test('archive discards late sessions, retries manually, and clears requests and results under spoiler protection', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ config: { modules: [{ type: 'archive', options: { year: 2024 } }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    window.archiveRequests = []; window.archiveFail = false; window.archiveDelayed = null;
    const connection = new EventTarget(); connection.connected = true;
    card.previewData = null;
    card.hass = { ...demo.hass, connection, callService: () => { throw new Error('Unexpected replay service'); }, callWS: async query => {
      window.archiveRequests.push(query);
      if (query.type === 'f1_sensor/entities') return demo.preview.entries;
      if (window.archiveFail && query.type.endsWith('/results')) throw new Error('Temporary failure');
      const payload = demo.preview.history(query).data.payload;
      if (query.type.endsWith('/results')) {
        payload.results[0].driver_name = `Historical round ${query.round}`;
        if (query.round === 2) return new Promise(resolve => { window.archiveDelayed = () => resolve(payload); });
      }
      return payload;
    } };
  });
  await expect(page.getByText('Loading archive…')).toBeVisible();
  await page.waitForFunction(() => window.archiveDelayed);
  await page.getByRole('combobox', { name: 'Grand Prix', exact: true }).selectOption('1');
  await expect(page.getByRole('button', { name: /Historical round 1/ })).toBeVisible();
  await page.evaluate(() => window.archiveDelayed());
  await expect(page.getByRole('button', { name: /Historical round 2/ })).toHaveCount(0);
  await page.evaluate(() => { window.archiveFail = true; });
  await page.getByRole('combobox', { name: 'Session', exact: true }).selectOption('demo:2024:1:qualifying');
  await expect(page.getByRole('button', { name: 'Retry archive', exact: true })).toBeVisible();
  const before = await page.evaluate(() => window.archiveRequests.length);
  await page.waitForTimeout(1100); expect(await page.evaluate(() => window.archiveRequests.length)).toBe(before);
  await page.evaluate(() => { window.archiveFail = false; });
  await page.getByRole('button', { name: 'Retry archive', exact: true }).click();
  await expect(page.getByRole('button', { name: /Historical round 1/ })).toBeVisible();
  await page.evaluate(() => { const card = window.fixtureCard; card.hass = { ...card.hass, states: { ...card.hass.states, 'switch.f1_demo_spoilers': { state: 'on', attributes: {} } } }; });
  await expect(page.getByText('Spoiler protection is active.')).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Grand Prix', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => window.fixtureCard.history.resources.size)).toBe(0);
  await expect(page.getByRole('button', { name: /Historical round 1/ })).toHaveCount(0);
});

test('archive editor saves source choices and fields, resetting dependent choices only when the context changes', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ editor: true, config: { modules: [{ type: 'archive', options: { year: 2024 } }] } });
    const editor = window.fixtureCard, demo = window.fixtureDemo, connection = new EventTarget(); connection.connected = true;
    editor.hass = { ...demo.hass, connection, callWS: async query => query.type === 'f1_sensor/entities' ? demo.preview.entries : demo.preview.history(query).data.payload };
  });
  const settings = page.getByRole('region', { name: 'Selected module' });
  await page.getByText('Module options', { exact: true }).click();
  await settings.getByRole('combobox', { name: 'Grand Prix', exact: true }).selectOption('1');
  await settings.getByRole('combobox', { name: 'Session', exact: true }).selectOption('demo:2024:1:qualifying');
  await expect(settings.getByRole('checkbox', { name: 'Q1 time', exact: true })).toBeChecked();
  await settings.getByRole('checkbox', { name: 'Q1 time', exact: true }).uncheck();
  await settings.getByRole('checkbox', { name: 'Q1 time', exact: true }).check();
  await settings.getByRole('checkbox', { name: 'Charles Leclerc', exact: true }).check();
  expect(await page.evaluate(() => window.savedConfig.modules[0])).toMatchObject({ fields: ['result_position', 'driver', 'team', 'q2_time', 'q3_time', 'q1_time'], options: { profile: 'custom', year: 2024, round: '1', session_key: 'demo:2024:1:qualifying', selected: ['demo-driver-16'] } });
  await settings.getByRole('combobox', { name: 'Archive view', exact: true }).selectOption('lap_time');
  expect(await page.evaluate(() => window.savedConfig.modules[0].fields)).toContain('q1_time');
  await settings.getByRole('spinbutton', { name: 'Year', exact: true }).fill('2023');
  await settings.getByRole('spinbutton', { name: 'Year', exact: true }).blur();
  expect(await page.evaluate(() => window.savedConfig.modules[0].options)).toMatchObject({ year: 2023, round: '', session_key: '', selected: [] });
  const saved = await page.evaluate(() => window.savedConfig);
  await page.reload(); await page.waitForFunction(() => window.modularReady);
  await page.evaluate(config => window.mountModular({ config, editor: true }), saved);
  expect(await page.evaluate(() => window.fixtureCard.config)).toEqual(saved);
});

test('telemetry curves show units, patterns, gaps and accessible sample tables on mobile', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 360, height: 900 });
  await page.evaluate(() => window.mountModular({ scene: 'replay', config: { modules: [{ type: 'telemetry', fields: ['telemetry_speed', 'telemetry_throttle', 'telemetry_delta_s'], options: { axis: 'distance' } }] } }));
  await expect(page.getByRole('heading', { name: 'Replay telemetry', exact: true })).toBeVisible();
  await expect(page.getByText('About the telemetry', { exact: true })).toBeVisible();
  await expect(page.locator('f1-telemetry-view svg.plot')).toHaveCount(3);
  await expect(page.getByText('Estimated distance (m)', { exact: true }).first()).toBeVisible();
  const paths = await page.locator('f1-telemetry-view svg.plot').first().locator('[data-series="16:2"] path').count();
  expect(paths).toBe(2);
  await page.getByRole('button', { name: 'Show data table', exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'Throttle (%)', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: /lap 2/ })).toBeVisible();
  await page.getByRole('combobox', { name: 'Table for lap', exact: true }).selectOption('16:2');
  expect((await page.getByRole('combobox', { name: 'Table for lap', exact: true }).boundingBox()).height).toBeGreaterThanOrEqual(44);
  await expect(page.locator('f1-telemetry-view table caption')).toContainText('lap 2');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const violations = (await new AxeBuilder({ page }).include('f1-sensor-card').analyze()).violations;
  expect(violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('telemetry-mobile.png'), fullPage: true });
  await page.emulateMedia({ forcedColors: 'active' });
  const forced = await page.locator('f1-telemetry-view svg.plot').first().locator('path.curve').first().evaluate(node => ({ stroke: getComputedStyle(node).stroke, text: getComputedStyle(node.getRootNode().host).color, surface: getComputedStyle(document.querySelector('f1-sensor-card').shadowRoot.querySelector('ha-card')).backgroundColor }));
  expect(forced.stroke).toBe(forced.text); expect(forced.stroke).not.toBe(forced.surface);
});

test('telemetry fetches only explicit comparisons, retries manually and discards late replay responses', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ scene: 'replay', config: { modules: [{ type: 'telemetry' }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    window.telemetryRequests = []; window.telemetryFail = false; window.telemetryHold = false;
    card.previewData = null;
    card.hass = { ...demo.hass, connection: { subscribeEvents: async () => () => {} }, callService: () => { throw new Error('Unexpected replay action'); }, callWS: async query => {
      window.telemetryRequests.push(query);
      if (query.type === 'f1_sensor/entities') return demo.preview.entries;
      const payload = demo.preview.telemetry(query).data.payload;
      payload.session_id = query.expected_session_id;
      if (query.type.endsWith('telemetry_compare')) {
        if (window.telemetryFail) throw new Error('Unavailable telemetry');
        if (window.telemetryHold) return new Promise(resolve => { window.finishTelemetry = () => resolve(payload); });
      }
      return payload;
    } };
  });
  const view = page.locator('f1-telemetry-view');
  await expect(view.getByRole('combobox', { name: 'Driver to add', exact: true })).toBeEnabled();
  await view.getByRole('combobox', { name: 'Driver to add', exact: true }).selectOption('4');
  await view.getByRole('button', { name: 'Add lap', exact: true }).click();
  expect(await page.evaluate(() => window.telemetryRequests.filter(query => query.type.endsWith('telemetry_compare')).length)).toBe(0);
  await view.getByRole('button', { name: 'Compare selected laps', exact: true }).click();
  await expect(view.locator('svg.plot')).toHaveCount(3);
  expect(await page.evaluate(() => window.telemetryRequests.find(query => query.type.endsWith('telemetry_compare')))).toMatchObject({ expected_session_id: 'demo-replay', selections: [{ driver_number: 4, lap_number: 2 }] });
  await view.locator('summary').filter({ hasText: 'Selected laps' }).click();
  await view.getByRole('combobox', { name: 'Recorded lap', exact: true }).selectOption('3');
  await view.getByRole('button', { name: 'Add lap', exact: true }).click();
  await expect(view.locator('svg.plot')).toHaveCount(0);
  await page.evaluate(() => { window.telemetryFail = true; });
  await view.getByRole('button', { name: 'Compare selected laps', exact: true }).click();
  await expect(view.getByRole('alert')).toBeVisible();
  const count = await page.evaluate(() => window.telemetryRequests.length);
  await page.waitForTimeout(1100);
  expect(await page.evaluate(() => window.telemetryRequests.length)).toBe(count);
  await page.evaluate(() => { window.telemetryFail = false; window.telemetryHold = true; });
  await view.getByRole('button', { name: 'Compare selected laps', exact: true }).click();
  await page.waitForFunction(() => window.finishTelemetry);
  await page.evaluate(() => {
    const card = window.fixtureCard, id = window.fixtureDemo.preview.entries[0].entities.replay_player;
    card.hass = { ...card.hass, states: { ...card.hass.states, [id]: { ...card.hass.states[id], attributes: { ...card.hass.states[id].attributes, selected_session_id: 'new-replay' } } } };
  });
  await expect(view.getByText(/Saved laps belong to another replay/)).toBeVisible();
  await page.evaluate(() => window.finishTelemetry());
  await expect(view.locator('svg.plot')).toHaveCount(0);
  await page.evaluate(() => { const card = window.fixtureCard; card.setConfig({ ...card.config, context: { ...card.config.context, spoilers: 'hide' } }); });
  await expect(page.getByText('Spoiler protection is active.', { exact: true })).toBeVisible();
  await expect(view).toHaveCount(0);
  expect(await page.evaluate(async () => { const { connectionDiagnostics } = await import('/custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js'); return connectionDiagnostics(window.fixtureCard.hass.connection).resources; })).toBe(1);
});

test('telemetry editor saves chosen laps and channels without fetching samples', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ editor: true, scene: 'replay', config: { modules: [{ type: 'telemetry' }] } });
    const editor = window.fixtureCard, demo = window.fixtureDemo;
    window.telemetryEditorRequests = [];
    editor.hass = { ...demo.hass, connection: { subscribeEvents: async () => () => {} }, callWS: async query => {
      window.telemetryEditorRequests.push(query);
      if (query.type === 'f1_sensor/entities') return demo.preview.entries;
      if (query.type.endsWith('telemetry_compare')) throw new Error('Editor cannot fetch telemetry');
      return demo.preview.telemetry(query).data.payload;
    } };
  });
  const form = page.locator('.form');
  await form.getByText('Module options', { exact: true }).click();
  await form.getByRole('combobox', { name: 'Driver to add', exact: true }).selectOption('16');
  await form.getByRole('combobox', { name: 'Recorded lap', exact: true }).selectOption('3');
  await form.getByRole('button', { name: 'Add lap', exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.savedConfig?.modules[0].options.selected)).toEqual(['16:3']);
  expect(await page.evaluate(() => window.savedConfig.modules[0].options.session_id)).toBe('demo-replay');
  await form.getByRole('checkbox', { name: 'Gear', exact: true }).check();
  expect(await page.evaluate(() => window.savedConfig.modules[0].fields)).toContain('telemetry_gear');
  expect(await page.evaluate(() => window.telemetryEditorRequests.some(query => query.type.endsWith('telemetry_compare')))).toBe(false);
});
