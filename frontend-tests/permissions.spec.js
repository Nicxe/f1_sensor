const { test, expect } = require('@playwright/test');

for (const admin of [false, true]) {
  test(`${admin ? 'administrator' : 'standard user'} can discover the modular card and read Race Control history and updates`, async ({ page }) => {
    await page.goto('/frontend-tests/modular.html');
    await page.waitForFunction(() => window.modularReady);
    await page.evaluate(admin => {
      window.mountModular({ config: { modules: [{ type: 'race_control', options: { display_mode: 'list' } }] } });
      const card = window.fixtureCard, demo = window.fixtureDemo, entry = demo.preview.entries[0];
      const handlers = new Map();
      const connection = new EventTarget();
      connection.connected = true;
      window.permissionCalls = { native: [], subscriptions: [], requests: [], services: [] };
      const subscribe = (type, callback) => {
        if (!handlers.has(type)) handlers.set(type, new Set());
        handlers.get(type).add(callback);
        return () => handlers.get(type).delete(callback);
      };
      connection.subscribeEvents = async (callback, type) => {
        window.permissionCalls.native.push(type);
        if (!admin && type !== 'entity_registry_updated') throw { code: 'unauthorized', message: 'Unauthorized' };
        return subscribe(type, callback);
      };
      connection.subscribeMessage = async (callback, message) => {
        if (message.type !== 'f1_sensor/events/subscribe') throw new Error(`Unexpected subscription: ${message.type}`);
        window.permissionCalls.subscriptions.push(message);
        return subscribe(message.event_type, callback);
      };
      window.permissionEmit = (type, data) => {
        for (const callback of handlers.get(type) ?? []) callback({ event_type: type, data });
      };
      window.permissionEntity = entry.entities.race_control;
      card.previewData = null;
      card.hass = {
        ...demo.hass, connection,
        callService: (...args) => window.permissionCalls.services.push(args),
        callWS: async message => {
          window.permissionCalls.requests.push(message.type);
          if (message.type === 'f1_sensor/entities') return [entry];
          if (message.type === 'f1_sensor/race_control_log/get') return { items: [
            { event_id: 'history-one', utc: '2026-09-13T13:31:00Z', message: 'MARSHALS CHECKING TURN 4', category: 'Other' },
            { event_id: 'history-two', utc: '2026-09-13T13:31:30Z', message: 'TURN 4 INSPECTION COMPLETE', category: 'Other' },
          ] };
          throw new Error(`Unexpected request: ${message.type}`);
        },
      };
    }, admin);

    const card = page.locator('f1-sensor-card');
    await expect(card.getByText('MARSHALS CHECKING TURN 4', { exact: true })).toBeVisible();
    await expect(card.getByText('TURN 4 INSPECTION COMPLETE', { exact: true })).toBeVisible();
    await expect(card).not.toContainText('Unauthorized');
    expect(await page.evaluate(() => window.permissionCalls.native)).toEqual(['entity_registry_updated']);
    expect(await page.evaluate(() => window.permissionCalls.requests)).toEqual(['f1_sensor/entities', 'f1_sensor/race_control_log/get']);

    await page.evaluate(() => window.permissionEmit('f1_sensor_race_control_event', {
      entity_id: window.permissionEntity,
      log_item: { event_id: 'live-three', utc: '2026-09-13T13:32:00Z', message: 'RACE CONTROL TEST UPDATE', category: 'Other' },
    }));
    await expect(card.getByText('RACE CONTROL TEST UPDATE', { exact: true })).toBeVisible();
    await expect(card.getByText('MARSHALS CHECKING TURN 4', { exact: true })).toBeVisible();

    await page.evaluate(() => window.permissionEmit('f1_sensor_race_control_log_reset_event', { entity_id: window.permissionEntity }));
    await expect(card.getByText('RACE CONTROL TEST UPDATE', { exact: true })).toHaveCount(0);
    await expect(card.getByText('MARSHALS CHECKING TURN 4', { exact: true })).toHaveCount(0);
    await expect(card.getByText('TURN 4 INSPECTION COMPLETE', { exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => window.permissionCalls.services)).toEqual([]);
  });
}
