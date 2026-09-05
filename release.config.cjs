const config = require("@nicxe/semantic-release-config")({
  componentDir: "custom_components/f1_sensor",
  manifestPath: "custom_components/f1_sensor/manifest.json",
  projectName: "F1 Sensor",
  repoSlug: "Nicxe/f1_sensor",
  notifyIssues: false
});

const githubPlugin = config.plugins.find(
  (plugin) => Array.isArray(plugin) && plugin[0] === "@semantic-release/github"
);

if (githubPlugin?.[1]) {
  githubPlugin[1].successCommentCondition = false;
  githubPlugin[1].assets = [
    { path: "f1_sensor.zip", label: "F1 Sensor" },
    { path: "f1_sensor.zip.sha256", label: "SHA-256 checksum" },
    { path: "f1_sensor.zip.spdx.json", label: "SPDX SBOM" }
  ];
}

const execPlugin = config.plugins.find(
  (plugin) => Array.isArray(plugin) && plugin[0] === "@semantic-release/exec"
);

if (execPlugin?.[1]) {
  execPlugin[1].prepareCmd = [
    "python3 scripts/build_release.py",
    "--component custom_components/f1_sensor",
    "--output f1_sensor.zip",
    "--version ${nextRelease.version}",
    "&& python3 scripts/verify_release.py f1_sensor.zip --version ${nextRelease.version}"
  ].join(" ");
}

module.exports = config;
