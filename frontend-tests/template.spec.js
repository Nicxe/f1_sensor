const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
});

test('named template is reviewed before replacement and can be undone', async ({ page }) => {
  await page.evaluate(() => window.mountModular({ editor: true, config: { title: 'Current', appearance: { style: 'minimal' }, modules: [{ type: 'calendar' }] } }));
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Reusable templates', { exact: true }).click();
  await editor.getByLabel('Template JSON', { exact: true }).fill(JSON.stringify({
    format: 'f1-sensor-template', version: 1, name: 'Timing copy',
    card: { type: 'custom:f1-sensor-card', version: 1, title: 'Imported', appearance: { style: 'f1' }, modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] },
  }));
  await editor.getByRole('button', { name: 'Review template', exact: true }).click();
  const review = editor.getByRole('region', { name: 'Template review', exact: true });
  await expect(review).toContainText('Current content: Schedule');
  await expect(review).toContainText('Template content: Timing');
  expect(await page.evaluate(() => window.fixtureCard.config.title)).toBe('Current');
  await review.getByRole('button', { name: 'Apply template', exact: true }).click();
  expect(await page.evaluate(() => window.savedConfig)).toMatchObject({ title: 'Imported', appearance: { style: 'f1' }, modules: [{ type: 'timing', fields: ['driver', 'last_lap'] }] });
  await editor.getByRole('button', { name: 'Undo', exact: true }).click();
  expect(await page.evaluate(() => window.savedConfig)).toMatchObject({ title: 'Current', appearance: { style: 'minimal' }, modules: [{ type: 'calendar' }] });
});

test('template with an unavailable installation requires an explicit replacement', async ({ page }) => {
  await page.evaluate(() => {
    window.mountModular({ editor: true, config: { modules: [{ type: 'overview' }] } });
    window.fixtureCard.entries = window.fixtureDemo.preview.entries;
  });
  const editor = page.locator('f1-sensor-card-editor');
  await editor.getByText('Reusable templates', { exact: true }).click();
  await editor.getByLabel('Template JSON', { exact: true }).fill(JSON.stringify({
    format: 'f1-sensor-template', version: 1, name: 'Other home',
    card: { type: 'custom:f1-sensor-card', version: 1, f1_entry_id: 'missing-entry', modules: [{ type: 'calendar' }] },
  }));
  await editor.getByRole('button', { name: 'Review template', exact: true }).click();
  const review = editor.getByRole('region', { name: 'Template review', exact: true });
  const apply = review.getByRole('button', { name: 'Apply template', exact: true });
  await expect(apply).toBeDisabled();
  await review.getByLabel('F1 Sensor installation for template', { exact: true }).selectOption('demo');
  await expect(apply).toBeEnabled();
  await apply.click();
  expect(await page.evaluate(() => window.savedConfig.f1_entry_id)).toBe('demo');
});
