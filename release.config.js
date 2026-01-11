// Wrapper to ensure semantic-release consistently discovers the config.
// Some versions/tools only auto-load `release.config.js` (not `.cjs`).
module.exports = require("./release.config.cjs");

