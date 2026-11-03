const {test, expect} = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');

test('the local reading and heading fonts load successfully', async ({page}) => {
  await page.goto('');
  const faces = await page.evaluate(async () => {
    await document.fonts.ready;
    return [...document.fonts].map(face => ({family: face.family, weight: face.weight, status: face.status}));
  });
  for (const [family, weight] of [['Barlow Condensed', '600'], ['Source Sans 3', '400']]) {
    expect(faces.some(face => face.family.replace(/["']/g, '') === family && face.weight === weight && face.status === 'loaded'), `${family} ${weight} failed to load`).toBe(true);
  }
});

test('the introduction and channel are prominent links without an embedded player', async ({page}) => {
  await page.goto('');
  const introduction = page.getByRole('link', {name: /Watch Meet F1 Sensor/});
  await expect(introduction).toHaveAttribute('href', 'https://www.youtube.com/watch?v=R72LXKdiNxA');
  await expect(page.getByRole('link', {name: /More videos by Niklas Vilnersson/})).toHaveAttribute('href', 'https://www.youtube.com/@niklasvilnersson');
  await expect(page.locator('iframe')).toHaveCount(0);
  const image = introduction.locator('img');
  await expect.poll(() => image.evaluate(img => img.complete && img.naturalWidth >= 640)).toBe(true);
  const position = await introduction.boundingBox();
  expect(position.y).toBeLessThan(900);
});

test('flag lighting stays still until played and can be paused', async ({page, request}) => {
  await page.goto('');
  const demo = page.getByLabel('Flag lighting demonstration', {exact: true});
  await demo.scrollIntoViewIfNeeded();
  await expect(demo).toBeVisible();
  await expect(demo).not.toHaveAttribute('autoplay');
  await expect(demo).not.toHaveAttribute('loop');
  await expect(demo).toHaveAttribute('preload', 'none');
  const base = new URL(test.info().project.use.baseURL).pathname;
  await expect(demo).toHaveAttribute('poster', `${base}img/home/flag-light-demo-poster.jpg`);
  expect(await demo.evaluate(video => video.paused && video.currentTime === 0)).toBe(true);
  await page.getByRole('button', {name: 'Play demonstration', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Pause demonstration', exact: true})).toBeVisible();
  await expect.poll(() => demo.evaluate(video => video.currentTime)).toBeGreaterThan(0);
  await page.getByRole('button', {name: 'Pause demonstration', exact: true}).click();
  expect(await demo.evaluate(video => video.paused)).toBe(true);
  await expect(page.getByRole('button', {name: 'Play demonstration', exact: true})).toBeVisible();
  const source = await demo.locator('source').getAttribute('src');
  const response = await request.get(source);
  expect(response.ok()).toBe(true);
  expect(await response.body()).toEqual(fs.readFileSync(path.resolve(__dirname, '../static/img/home/flag-light-demo.mp4')));
  const original = await request.get(`${base}img/flag-light-demo.gif`);
  expect(original.ok()).toBe(true);
  expect(await original.body()).toEqual(fs.readFileSync(path.resolve(__dirname, '../static/img/flag-light-demo.gif')));
});
