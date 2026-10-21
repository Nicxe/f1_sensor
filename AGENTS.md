# F1 Sensor source parity

A completed F1 Sensor code change must exist in both the local Git checkout and
the Home Assistant development instance. The corresponding integration trees
are:

- `/Users/niklas/GitHub/f1_sensor/custom_components/f1_sensor`
- `/Volumes/config/custom_components/f1_sensor`

Before editing or synchronizing, inspect both trees and preserve unrelated
work. Synchronize every intended changed, added, renamed, or deleted file to
both trees as part of the same task; do not use a blanket overwrite when either
tree contains unrelated differences. Before reporting the code change as
complete, require a byte-for-byte comparison of the complete integration trees
to return no differences, excluding only runtime-generated cache artifacts such
as `__pycache__`, `*.pyc`, and `.DS_Store`.

# Local dev CI preflight

Run `npm run setup:ci` to create the isolated Python, Node, npm, browser and
workflow-validator environment. Versions and dependency inputs are recorded;
preflight refreshes stale setup rather than trusting an existing directory.
Before considering a code change ready for commit, run
`npm run verify:changed`. It uses the same check commands and selection policy
as GitHub, including strict runtime coverage for integration changes. Fix every
failure before reporting readiness. `--print-plan` and a no-change result are
not successful verification.

Run `npm run verify:dev` for a complete development snapshot. Before proposing
a substantial promotion, run `npm run verify:release -- --target beta` or
`npm run verify:release -- --target main` for its actual destination. These full
profiles include the security gate. Evidence in `test-results/verification.json`
is valid only for the recorded source fingerprint, tools and dependencies;
changes during a run invalidate the result. Never describe local success as
GitHub success, a published release, or a Home Assistant runtime activation.

Weblate target-language text and the number of supported languages are not
fixed test contracts. Test catalog structure, placeholders, delivered assets,
locale selection and per-key fallback against independent fixtures or current
catalogs. Target-language-only changes use the translations lane; changes to
English sources, localization code or tooling retain broader verification.

Publication changes must preserve the normal `dev → beta → main` rollout.
Beta documentation must work on its first promotion without requiring the new
publisher on `main`. Test that transition explicitly. Keep Pages failures out
of product verification and never publish unverified companion-branch content.

HACS and hassfest remain GitHub-only verification gates. Local verification is
the agent's pre-commit quality gate; passing it does not replace the required
remote checks after the user pushes with GitHub Desktop. A failed selected job
cannot be excused as a skipped check or replaced by unrelated green evidence.

If `/Volumes/config` is unavailable or unrelated changes prevent safe
synchronization, report the limitation and do not call the code change
complete. Source parity proves delivery to both file trees, not that Home
Assistant has reloaded the integration or is running the new code; runtime
activation must be verified separately when required.

# Release notes and commit policy

F1 Sensor uses Conventional Commits and semantic-release. Preserve individual
Conventional Commits when promoting `dev` to `beta` and `beta` to `main` with a
merge commit; never squash or rebase a promotion.

Write commit summaries in English as plain text, without Markdown, issue
numbers, PR numbers, or implementation details. Use `feat:` for a new
user-facing capability and `fix:` for a correction. Prefer a scope when it
clarifies the affected user area: `integration`, `card`, `blueprint`, or
`translations`.

Commit bodies are published in release notes. Omit the body when the summary is
self-explanatory. Otherwise use at most two concise user-facing sentences. If a
commit fully resolves an issue, end the body with `Fixes #<number>`; retain this
reference because it drives issue handling and lets users reach the context.

Use `chore(translations):`, `chore(i18n):`, `chore(accessibility):`,
`chore(a11y):`, or `chore(compatibility):` for user-visible improvements that
do not change semantic-release versioning. Internal chores, refactors, tests,
CI, build work, branch synchronization, release tooling, and formatting must
not appear in user-facing release notes.

Use `feat(blueprint):` for a new or materially expanded blueprint. For a
breaking change, write `feat(scope)!:` or `fix(scope)!:` and include a final
`BREAKING CHANGE:` footer explaining what users must change.

The generated release keeps the download shield, beta notice, sponsorship
message, and sponsor buttons. Add a short manual editorial summary only when a
release has a main story, a beta-testing focus, or an external contributor to
thank; remove or leave the HTML prompt comment otherwise.
