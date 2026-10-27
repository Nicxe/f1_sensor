/** Independent catalog expectations; never imports the production translator. */
const {readFileSync, readdirSync} = require('node:fs');
const path = require('node:path');
const directory = path.join(__dirname, '..', 'custom_components/f1_sensor/www/f1-sensor-live-data-card/localization/locales');
const filenames = readdirSync(directory).filter(name => name.endsWith('.json'));
const catalogs = Object.fromEntries(filenames.map(name => [name.slice(0, -5).toLowerCase(),
  JSON.parse(readFileSync(path.join(directory, name), 'utf8'))]));
const expectedMessage = (language, key) => {
  const parts = language.replaceAll('_', '-').toLowerCase().split('-');
  while (parts.length) {
    const value = catalogs[parts.join('-')]?.[key];
    if (value !== undefined) return value;
    parts.pop();
  }
  return catalogs.en[key];
};
module.exports = {catalogs, filenames, expectedMessage};
