const {nonReleaseRules} = require("./semantic-release-policy.json");
const {configuredStage} = require("./.github/scripts/release-stage.cjs");
const path = require("node:path");

const sharedOptions = {
  componentDir: "custom_components/f1_sensor",
  manifestPath: "custom_components/f1_sensor/manifest.json",
  projectName: "F1 Sensor",
  repoSlug: "Nicxe/f1_sensor",
  f1Theme: true,
  templatePath: path.join(__dirname, ".release/release-notes.hbs"),
  notifyIssues: false
};
const createSharedConfig = () => require("@nicxe/semantic-release-config")(sharedOptions);
const config = createSharedConfig();
config.branches = ["main", {name: "beta", channel: "beta", prerelease: configuredStage() === "rc" ? "rc" : "beta"}];

const notesIndex = config.plugins.findIndex(
  plugin => Array.isArray(plugin) && plugin[0] === "@semantic-release/release-notes-generator"
);
config.plugins[notesIndex] = ["./.github/scripts/release-notes.cjs", {
  createOptions: () => createSharedConfig().plugins.find(
    plugin => Array.isArray(plugin) && plugin[0] === "@semantic-release/release-notes-generator"
  )[1]
}];

const analyzerPlugin = config.plugins.find(
  (plugin) => Array.isArray(plugin) && plugin[0] === "@semantic-release/commit-analyzer"
);

if (analyzerPlugin?.[1]) {
  analyzerPlugin[1].releaseRules = [
    ...(analyzerPlugin[1].releaseRules || []),
    ...nonReleaseRules
  ];
}

const githubPlugin = config.plugins.find(
  (plugin) => Array.isArray(plugin) && plugin[0] === "@semantic-release/github"
);

if (githubPlugin?.[1]) {
  githubPlugin[1].draftRelease = true;
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
