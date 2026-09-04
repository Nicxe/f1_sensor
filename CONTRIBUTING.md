# Contributing

Thank you for your interest in contributing to f1_sensor!

## Branch model

This project uses two contribution paths depending on what you are changing.

### Code changes

For changes to the integration itself — sensors, binary sensors, configuration flow, coordinator logic, bundled Live Data Card code, fixes, features, tests — use the code path:

- `dev` — the active development branch. All code contributions must target this branch.
- `beta` — pre-release testing. Promoted from `dev` by the maintainer.
- `main` — stable production releases. Promoted from `beta` by the maintainer.

Promotions to `beta` and `main` must use a merge commit. Squash or rebase
merges remove the individual conventional commits that semantic-release uses
to determine the version and generate complete release notes.

The `beta` and `main` branches are managed exclusively by the maintainer. Contributor PRs must target `dev` or `content`. A routing comment explains how to change the base branch when necessary; the same PR can be kept.

### Documentation and blueprint changes

For changes to documentation (`docs/`) or blueprints (`blueprints/`) that are independent of any code change, use the content path:

- `content` — the dedicated branch for documentation and blueprint contributions. PRs targeting this branch are merged directly to `main` by the maintainer, without going through beta.

Use `docs:` or `chore:` commits for standalone content so semantic-release does not create a version solely for that change.

### Which branch should I target?

| What I am changing | Target branch |
|---|---|
| Integration code, sensors, fixes, features | `dev` |
| Bundled Live Data Card code in `custom_components/f1_sensor/www/**` | `dev` |
| Docusaurus components, CSS, configuration, build scripts, or documentation tests | `dev` |
| Tests only | `dev` |
| Documentation for an upcoming code change | `dev` (keep docs with the code) |
| Standalone documentation fix or update | `content` |
| New or updated blueprint (standalone) | `content` |

If your PR mixes code changes with documentation changes, target `dev`. A site redesign that changes Docusaurus components, styles, configuration, or build behavior also follows the `dev` path. Keep documentation for unreleased integration features with the corresponding code; do not publish it as stable before that release ships.

## Documentation workflow

Read [the documentation style guide](doc-style-guide.md) before adding or restructuring a page. Public text stays in English. Use stable IDs, a descriptive title and description, exact entity names, and examples checked against the release you are documenting.

1. Start from `content` for an independent documentation correction, or `dev` for a site/code change or documentation of an upcoming feature.
2. Make the focused change and update the sidebar and relevant overview if you add a page.
3. Preserve existing public routes and important heading anchors when splitting content. The old page can link readers to the new focused reference.
4. Run the documentation checks from the repository root:

```bash
npm ci
npm run test:docs
```

For a development preview, run `npm start`. The production documentation check is still required because search indexing and generated routes can behave differently from the development server.

To refresh reproducible card screenshots:

```bash
npm run capture:docs-cards
```

Review the resulting images before committing them. Use meaningful alt text and captions, identify demonstration or replay data, and keep the image source/provenance alongside the capture workflow. Do not include credentials or private Home Assistant details.

Check a representative guide, reference table, and card page at mobile and desktop widths, in light and dark modes. Verify search, keyboard navigation, and the old links affected by the change. The Token Helper pairing page and privacy policy have stable public URLs; preserve query and fragment behavior during site changes.

Include the changed user journey, validation performed, and any limitations in the pull request. Integration or card behavior changes also require their normal Python, frontend, and Home Assistant checks; documentation checks do not replace them.

## How to submit a pull request

1. Fork the repository.
2. Identify the correct target branch using the table above.
3. Create a feature branch based on that target branch in your fork.
4. Make your changes and commit them with clear messages.
5. Open a pull request against the correct branch of this repository.

## Questions

If you are unsure whether a change fits the project direction, open an issue before starting work. This prevents effort being spent on contributions that may not be accepted.

## Automated checks

`CI required` summarizes all applicable checks. Code PRs run on the proposed merge result with read-only permissions and without secrets, including PRs from forks. Metadata workflows read trusted default-branch scripts and use the GitHub API; they never install or execute contributor code. A first-time contributor may still need the maintainer to start GitHub's restricted workflow run.

Standalone content runs documentation checks and, for blueprints, HA blueprint tests. Integration changes run Python, frontend, lint, HACS/hassfest and package checks. Dependency or workflow changes and code promotions run the complete set. Npm audit runs for dependency changes, releases and weekly maintenance; an unavailable registry is reported separately from a vulnerability.

The maintainer can push directly to `dev`. Promotions use `dev → beta → main` and merge commits. No additional reviewer is required. Release drafts are created only after checks pass on the same final commit. Publishing a draft remains a manual maintainer action. Publication notifies referenced issues and synchronizes the exact released history through a fast-forward or a CI-checked synchronization PR. Conflicts are resolved normally without force-pushing either side.

For a release retry, run **Actions → CI → Run workflow**, choose `beta` or `main`, leave the PR number empty and enable the release option. CI verifies that branch head again. An existing published tag is left untouched; an interrupted draft can be recovered without changing its version. Bot-created synchronization PRs use the PR-number input to explicitly check the proposed merge when `GITHUB_TOKEN` does not trigger PR workflows.

Use Python 3.14 with `requirements/ha-current.txt` for the complete HA suite, or Python 3.12 with `requirements/ha-minimum.txt` for the supported minimum. From the checkout root:

```bash
python -m pip install -r requirements/ha-current.txt
python scripts/run_ci_tests.py
python scripts/test_installed_release.py
npm ci
npm run test:automation
npm run test:frontend:unit
npx playwright install chromium
npm run test:frontend
npm run test:docs
```

Python line coverage must remain at least 95 percent across shipped code; branch coverage is reported separately. Tests should protect user behavior, lifecycle and external boundaries rather than specific source formatting. The weekly maintenance workflow checks latest stable HA compatibility on `dev`, WebKit smoke flows, timing budgets, npm audit and review dates. Review-date checks document overdue manual review; they do not verify a remote service's security.
