const fs = require("fs");
const path = require("path");

const mainTemplate = fs.readFileSync(
  path.join(__dirname, ".release", "release-notes.hbs"),
  "utf8"
);

module.exports = {
  tagFormat: "v${version}",

  branches: [
    "main",
    { name: "beta", prerelease: true }
  ],

  plugins: [
    [
      "@semantic-release/commit-analyzer",
      { preset: "conventionalcommits" }
    ],

    [
      "@semantic-release/release-notes-generator",
      {
        preset: "conventionalcommits",
        writerOpts: {
          mainTemplate
        }
      }
    ],

    [
      "@semantic-release/exec",
      {
        prepareCmd:
          "jq '.version = \"${nextRelease.version}\"' custom_components/f1_sensor/manifest.json > manifest.tmp && mv manifest.tmp custom_components/f1_sensor/manifest.json && cd custom_components && zip -r f1_sensor.zip f1_sensor"
      }
    ],

    [
      "@semantic-release/github",
      {
        draftRelease: true,
        commentOnSuccess: false
        assets: [
          {
            path: "custom_components/f1_sensor.zip",
            label: "f1_sensor.zip"
          }
        ]
      }
    ]
  ]
};