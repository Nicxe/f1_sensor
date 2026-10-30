const { test, expect } = require('@playwright/test');

async function mountMasonry(page, responseDelay, scene = 'race') {
  await page.goto('/frontend-tests/modular.html');
  await page.waitForFunction(() => window.modularReady);
  await page.evaluate(({ responseDelay, scene }) => {
    window.mountModular({ scene, config: { modules: [{ id: 'overview', type: 'overview' }] } });
    const card = window.fixtureCard, demo = window.fixtureDemo;
    const root = document.querySelector('#root');
    root.style.width = '480px';
    window.masonryStats = { requests: 0, activeSubscriptions: 0, moves: 0 };
    const connection = {
      connected: true,
      subscribeEvents: async () => {
        window.masonryStats.activeSubscriptions++;
        return () => { window.masonryStats.activeSubscriptions--; };
      },
      subscribeMessage: async () => {
        window.masonryStats.activeSubscriptions++;
        return () => { window.masonryStats.activeSubscriptions--; };
      },
    };
    card.previewData = null;
    card.hass = { ...demo.hass, connection, callWS: async message => {
      if (message.type !== 'f1_sensor/entities') throw new Error(`Unexpected request: ${message.type}`);
      window.masonryStats.requests++;
      await new Promise(resolve => setTimeout(resolve, responseDelay));
      return demo.preview.entries;
    } };
    let iteration = 0;
    // hui-view refreshes the cards array on card-updated. Masonry replaces
    // its columns, awaits each card's size, then reattaches the same nodes.
    // A microtask mirrors HA's scheduled update instead of moving the card
    // synchronously inside the card's own Lit update.
    window.rebuildMasonry = async () => {
      const token = ++iteration;
      const column = document.createElement('div');
      root.replaceChildren(column);
      await card.getCardSize();
      if (token !== iteration) return;
      column.append(card);
      window.masonryStats.moves++;
    };
    card.addEventListener('card-updated', () => queueMicrotask(window.rebuildMasonry));
  }, { responseDelay, scene });
}

async function settleFrames(page, count = 20) {
  await page.evaluate(async count => {
    for (let frame = 0; frame < count; frame++) await new Promise(requestAnimationFrame);
  }, count);
}

for (const [responseDelay, scene] of [[0, 'race'], [40, 'race'], [200, 'missing']]) {
  test(`Masonry overview settles with ${responseDelay}ms discovery and ${scene} data`, async ({ page }) => {
    await mountMasonry(page, responseDelay, scene);
    await expect(page.getByRole('region', { name: 'Overview', exact: true })).toBeVisible();
    await settleFrames(page);
    const settled = await page.evaluate(() => ({ ...window.masonryStats }));
    expect(settled.requests).toBe(1);
    expect(settled.activeSubscriptions).toBe(2);
    await settleFrames(page);
    expect(await page.evaluate(() => window.masonryStats)).toEqual(settled);
    await expect(page.getByText('Waiting for F1 Sensor…', { exact: true })).toHaveCount(0);
  });
}

test('leaving Masonry edit mode and resizing content settle, and removal releases discovery', async ({ page }) => {
  await mountMasonry(page, 40);
  await expect(page.getByRole('region', { name: 'Overview', exact: true })).toBeVisible();
  await settleFrames(page);
  await page.evaluate(async () => {
    window.fixtureCard.preview = true;
    await window.fixtureCard.updateComplete;
    // Done removes the edit wrapper and places the same card in the column.
    window.fixtureCard.preview = false;
    await window.rebuildMasonry();
  });
  await expect(page.getByRole('region', { name: 'Overview', exact: true })).toBeVisible();
  await settleFrames(page);
  const settled = await page.evaluate(() => ({ ...window.masonryStats }));
  expect(settled.requests).toBe(2);
  expect(settled.activeSubscriptions).toBe(2);
  await page.evaluate(() => {
    const card = window.fixtureCard;
    card.setConfig({ ...card.config, title: 'A much longer Formula One overview title that wraps in a narrow column' });
    document.querySelector('#root').style.width = '280px';
  });
  await settleFrames(page);
  expect(await page.evaluate(() => window.masonryStats)).toEqual(settled);
  const size = await page.evaluate(async () => ({ reported: await window.fixtureCard.getCardSize(), height: window.fixtureCard.shadowRoot.querySelector('ha-card').getBoundingClientRect().height }));
  expect(size.reported).toBe(Math.ceil(size.height / 50));
  await page.evaluate(() => window.fixtureCard.remove());
  await expect.poll(() => page.evaluate(() => window.masonryStats.activeSubscriptions)).toBe(0);
});
