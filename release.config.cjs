const config = require("@nicxe/semantic-release-config")({
  componentDir: "custom_components/f1_sensor",
  manifestPath: "custom_components/f1_sensor/manifest.json",
  projectName: "F1 Sensor",
  repoSlug: "Nicxe/f1_sensor"
});

const githubPlugin = config.plugins.find(
  (plugin) => Array.isArray(plugin) && plugin[0] === "@semantic-release/github"
);

if (githubPlugin?.[1]) {
  githubPlugin[1].successCommentCondition = false;
}

module.exports = config;
