import assert from 'node:assert/strict';
import test from 'node:test';
import { MODULES } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';
import { duplicateModule, exportConfig, importConfig, normalizeConfig } from '../../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';

for (const type of Object.keys(MODULES)) {
  test(`${type} preserves visible defaults and independent session/explanation choices`, () => {
    const shown = normalizeConfig({ modules: [{ type }] }).modules[0];
    assert.equal(shown.options.show_context, true);
    assert.equal(shown.options.show_explanation, true);
    for (const option of ['show_context', 'show_explanation']) {
      const config = normalizeConfig({ modules: [{ id: 'original', type, options: { [option]: false } }] });
      assert.equal(config.modules[0].options[option], false);
      assert.equal(config.modules[0].options[option === 'show_context' ? 'show_explanation' : 'show_context'], true);
      assert.deepEqual(importConfig(exportConfig(config)), config);
      assert.equal(duplicateModule(config, 'original').modules[1].options[option], false);
      assert.throws(() => normalizeConfig({ modules: [{ type, options: { [option]: 'false' } }] }), new RegExp(option));
    }
  });
}

test('map notice and driver-list choices are independent of selected map layers and legacy status options', () => {
  const shown = normalizeConfig({ modules: [{ type: 'map' }] }).modules[0];
  assert.equal(shown.options.show_experimental_notice, true);
  assert.equal(shown.options.show_driver_list, true);
  for (const option of ['show_experimental_notice', 'show_driver_list']) {
    const config = normalizeConfig({ modules: [{ type: 'map', fields: ['track_map', 'map_corners'], options: { [option]: false, show_session_info: false } }] });
    assert.equal(config.modules[0].options[option], false);
    assert.equal(config.modules[0].options.show_session_info, false);
    assert.equal(config.modules[0].options.show_context, true);
    assert.deepEqual(config.modules[0].fields, ['track_map', 'map_corners']);
    assert.deepEqual(importConfig(exportConfig(config)), config);
    assert.throws(() => normalizeConfig({ modules: [{ type: 'map', options: { [option]: 'false' } }] }), new RegExp(option));
  }
});

test('saved Results event-context choice remains supported', () => {
  const config = normalizeConfig({ modules: [{ type: 'results', options: { show_context: false, show_status: true } }] });
  assert.equal(config.modules[0].options.show_context, false);
  assert.equal(config.modules[0].options.show_status, true);
  assert.deepEqual(importConfig(exportConfig(config)), config);
});
