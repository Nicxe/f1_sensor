const fs = require("fs");
const path = require("path");

// NOTE:
// In current versions, `conventional-changelog-conventionalcommits` exports an async preset factory
// (it does not expose `writerOpts` synchronously). That means we cannot rely on the preset's
// default writer transform here. Instead we do the type->section mapping ourselves so the
// handlebars template can render nice headings (commitGroups[].title).

const RELEASE_NOTE_TYPES = [
  { type: "feat", section: "New features" },
  { type: "fix", section: "Bug fixes" },
  { type: "docs", section: "Documentation" },
  { type: "refactor", section: "Refactoring" },
  { type: "chore", section: "Maintenance" },
  { type: "*", section: "Other changes" }
];

const TYPE_TO_SECTION = RELEASE_NOTE_TYPES.reduce((acc, { type, section }) => {
  acc[type] = section;
  return acc;
}, {});

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
        presetConfig: {
          types: RELEASE_NOTE_TYPES
        },
        writerOpts: {
          mainTemplate,
          // `@semantic-release/release-notes-generator` (via conventional-changelog) does NOT
          // automatically expose semantic-release's branch config like `{ prerelease: true }`
          // to the Handlebars template context. We inject our own boolean so `{{#if prerelease}}`
          // in `.release/release-notes.hbs` behaves predictably.
          finalizeContext: (context) => {
            const v = String(context?.version || "");
            // prerelease versions include a "-" suffix, e.g. "1.2.3-beta.1"
            context.prerelease = v.includes("-");
            return context;
          },
          groupBy: "type",
          commitGroupsSort: "title",
          commitsSort: ["scope", "subject"],
          transform: (commit, context) => {
            const header = commit.header || commit.subject || "";

            // Don't include GitHub merge commits in release notes
            if (/^merge pull request/i.test(header) || /^merge branch/i.test(header)) {
              return null;
            }

            const transformed = { ...commit };

            // Make sure we always have a subject, otherwise skip the commit
            transformed.subject =
              transformed.subject || commit.subject || commit.header || "";
            if (!transformed.subject.trim()) {
              return null;
            }

            // Some conventional-changelog presets mark certain commit types (e.g. docs/chore)
            // as hidden by default. We want them visible in our release notes.
            transformed.hidden = false;

            // Map conventional type -> pretty section title (this becomes commitGroups[].title)
            let rawType = transformed.type || commit.type;
            if (typeof rawType !== "string" || !rawType.trim()) {
              rawType = "*";
            }
            rawType = rawType === "*" ? "*" : rawType.toLowerCase();
            transformed.type = TYPE_TO_SECTION[rawType] || TYPE_TO_SECTION["*"];

            // Optional: include commit body/description (everything after the first blank line)
            // and pre-indent it so it renders nicely under the bullet in Markdown.
            const body = (transformed.body || commit.body || "").trim();
            if (body) {
              transformed.bodyIndented = body
                .split(/\r?\n/)
                .map((line) => `  ${line}`) // 2-space indent => continues the list item
                .join("\n");
            }

            // Sanitize/normalize dates to avoid "RangeError: Invalid time value"
            const rawDate =
              commit.committerDate ||
              commit.authorDate ||
              transformed.committerDate ||
              transformed.authorDate ||
              commit.commit?.committer?.date ||
              commit.commit?.author?.date;

            const date = new Date(rawDate);
            transformed.committerDate = Number.isNaN(date.getTime())
              ? new Date().toISOString()
              : date.toISOString();

            return transformed;
          }
        }
      }
    ],

    [
      "@semantic-release/exec",
      {
        prepareCmd:
          "node .release/update-manifest-version.js --file custom_components/f1_sensor/manifest.json --version \"${nextRelease.version}\" && (cd custom_components && rm -f f1_sensor.zip && zip -r f1_sensor.zip f1_sensor)",

        // After a successful release, comment on issues referenced via "Fixes #123" etc
        // in commits included in this release. GitHub will still close issues automatically
        // when the PR is merged (closing keyword), this just adds "Included in X" context.
        successCmd:
          "node .release/notify-issues.js --range \"${lastRelease.gitHead}..${nextRelease.gitHead}\" --version \"${nextRelease.version}\" --git-tag \"${nextRelease.gitTag}\" --channel \"${nextRelease.channel}\"",
      }
    ],

    [
      "@semantic-release/github",
      {
        draftRelease: true,
        // Disable automated PR/issue comments from semantic-release
        // (the "🎉 This PR is included in version ..." message)
        successComment: false,
        failComment: false,
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
