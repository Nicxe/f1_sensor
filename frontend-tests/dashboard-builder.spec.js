const { test, expect } = require('@playwright/test');

async function openFixture(page) {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
}

test('three complete dashboard views are built in one editor and survive a separate frontend instance', async ({ page, context }) => {
  await openFixture(page);
  const cases = [
    {
      preset: /^Race weekend/,
      title: 'Weekend overview',
      modules: ['Overview', 'Schedule', 'Automatic current weather', 'Race-start forecast'],
      verify: async target => {
        await expect(target.getByRole('region', { name: 'Overview', exact: true }).getByText('Demo Grand Prix', { exact: true })).toBeVisible();
        await expect(target.getByRole('region', { name: 'Schedule', exact: true })).toBeVisible();
      },
    },
    {
      preset: /^Follow the session/,
      title: 'Detailed timing',
      modules: ['Overview', 'Timing', 'Race Control'],
      verify: async target => {
        await expect(target.getByRole('region', { name: 'Timing', exact: true }).locator('tr[data-driver]')).toHaveCount(5);
        await expect(target.getByRole('region', { name: 'Race Control', exact: true })).toBeVisible();
      },
    },
    {
      preset: /^My driver/,
      title: 'Favorite driver',
      modules: ['Overview', 'Timing', 'Race Control'],
      driver: '16',
      verify: async target => {
        await expect(target.getByRole('region', { name: 'Timing', exact: true }).locator('tr[data-driver="16"]')).toBeVisible();
        await expect(target.getByRole('region', { name: 'Timing', exact: true }).locator('tr[data-driver]')).toHaveCount(1);
      },
    },
  ];

  for (const scenario of cases) {
    await page.evaluate(() => {
      window.savedConfig = null;
      window.mountModular({ editor: true, config: { modules: [] } });
      window.fixtureCard.entries = window.fixtureDemo.preview.entries;
      window.fixtureCard.requestUpdate();
    });
    const editor = page.locator('f1-sensor-card-editor');
    await editor.getByText('Start from a template', { exact: true }).click();
    await editor.getByRole('button', { name: scenario.preset }).click();
    await editor.getByRole('textbox', { name: 'Card title', exact: true }).fill(scenario.title);
    await editor.getByRole('textbox', { name: 'Card title', exact: true }).press('Tab');
    if (scenario.driver) {
      await editor.getByText('Layout and shared focus', { exact: true }).click();
      await editor.getByLabel('Default driver', { exact: true }).selectOption(scenario.driver);
    }
    for (const [index, module] of scenario.modules.entries()) await expect(editor.getByRole('button', { name: `${index + 1}. ${module}`, exact: true })).toBeVisible();

    const serialized = await page.evaluate(() => JSON.stringify(window.savedConfig));
    expect(serialized).toBeTruthy();
    const saved = JSON.parse(serialized);
    expect(saved.title).toBe(scenario.title);
    expect(saved.modules).toHaveLength(scenario.modules.length);
    if (scenario.driver) expect(saved.context.driver).toBe(scenario.driver);

    await page.evaluate(config => window.mountModular({ config }), saved);
    await expect(page.locator('f1-sensor-card').getByText(scenario.title, { exact: true })).toBeVisible();
    await scenario.verify(page.locator('f1-sensor-card'));

    const other = await context.newPage();
    await openFixture(other);
    await other.evaluate(config => window.mountModular({ config }), JSON.parse(serialized));
    await expect(other.locator('f1-sensor-card').getByText(scenario.title, { exact: true })).toBeVisible();
    await scenario.verify(other.locator('f1-sensor-card'));
    await other.evaluate(config => window.mountModular({ editor: true, config }), JSON.parse(serialized));
    await expect(other.locator('f1-sensor-card-editor').getByRole('textbox', { name: 'Card title', exact: true })).toHaveValue(scenario.title);
    for (const [index, module] of scenario.modules.entries()) await expect(other.locator('f1-sensor-card-editor').getByRole('button', { name: `${index + 1}. ${module}`, exact: true })).toBeVisible();
    await other.close();
  }
});
