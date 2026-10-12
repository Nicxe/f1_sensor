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
