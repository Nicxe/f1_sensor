const {test, expect} = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

test('the homepage displays the original animated GIF directly', async ({page, request}) => {
  await page.goto('');
  const demo = page.getByRole('img', {name: 'Yellow flag on TV with a lamp glowing yellow'});
  await expect(demo).toBeVisible();
  await demo.scrollIntoViewIfNeeded();
  await expect(demo).toHaveAttribute('src', '/f1_sensor/img/flag-light-demo.gif');
  await expect.poll(() => demo.evaluate(img => img.complete && img.naturalWidth === 480 && img.naturalHeight === 270)).toBe(true);
  const response = await request.get(await demo.getAttribute('src'));
  expect(response.ok()).toBe(true);
  expect(response.headers()['content-type']).toContain('image/gif');
  expect(await response.body()).toEqual(fs.readFileSync(path.resolve(__dirname, '../static/img/flag-light-demo.gif')));
  const firstFrame = await demo.screenshot();
  await expect.poll(async () => !Buffer.from(await demo.screenshot()).equals(firstFrame), {message: 'The original GIF must animate in the rendered page'}).toBe(true);
  await expect(page.locator('video')).toHaveCount(0);
});
