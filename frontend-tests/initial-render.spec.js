const { test, expect } = require('@playwright/test');

test('removing a card before its first animation frame releases the queued render', async ({ page }) => {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(() => {
    window.originalRAF = window.requestAnimationFrame;
    window.originalCancelRAF = window.cancelAnimationFrame;
    window.queuedFrames = new Map(); let id = 0;
    window.requestAnimationFrame = callback => { window.queuedFrames.set(++id, callback); return id; };
    window.cancelAnimationFrame = id => window.queuedFrames.delete(id);
    window.mountModular({ config: { modules: [{ type: 'timing' }] } });
  });
  await expect.poll(() => page.evaluate(() => window.queuedFrames.size)).toBe(1);
  const result = await page.evaluate(async () => {
    const card = window.fixtureCard, completion = card.updateComplete;
    card.remove();
    const completed = await Promise.race([completion.then(() => true), new Promise(resolve => setTimeout(() => resolve(false), 1000))]);
    const queued = window.queuedFrames.size;
    window.requestAnimationFrame = window.originalRAF;
    window.cancelAnimationFrame = window.originalCancelRAF;
    document.querySelector('#root').append(card);
    return { completed, queued };
  });
  expect(result).toEqual({ completed: true, queued: 0 });
  await expect(page.getByRole('columnheader', { name: 'Driver', exact: true })).toBeVisible();
});
