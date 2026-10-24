# Test policy and migration evidence

## Product verification

Runtime Python must retain strictly more than 95% line coverage globally. Module and branch percentages are review evidence, not independent gates. A small module does not fail merely because one line changes its percentage sharply. Coverage counts must remain consistent; empty, malformed or inconsistent reports fail closed. Authentication, migrations, setup/unload, live windows, replay and thread safety retain blocking behavioral regressions. No meaningful regression is removed merely to reduce the test count.

The practice and next-race suites load complete bundled JavaScript modules in Node. Browser/Lit boundaries are simulated only in unit tests; Chromium tests render the real modules and Lit implementation. Installation tests observe actual custom-element registration and versioned module/image requests, rather than requiring a particular import spelling or cache-helper expression. Platform setup tests prove that the typed runtime owns entities even when stale legacy state exists.

Blocking browser tests run without test retries in both local and GitHub environments. Locator auto-wait and bounded polling are normal synchronization, not rerunning a failed test. Failure traces are retained. Functional responsive layout, keyboard use, accessibility, shared subscriptions and resource cleanup remain blocking. Broad pixel comparisons are opt-in visual review with `F1_VISUAL_REVIEW=1 npm run test:frontend`; timing benchmarks are opt-in with `F1_MAINTENANCE=1 npm run test:frontend`. Neither is an ordinary merge requirement. The independent supported-card baseline protects existing registrations without freezing the total number of cards.

Control tools have separate offline tests for invalid audit responses, bounded retries, coverage measurement, branch routing and aggregation, release recovery, pagination/idempotence and safe Git synchronization. The installed-ZIP smoke test uses real HA, coordinators, entities and WebSocket handling, with external HTTP responses simulated. It verifies the packaged import path, a TrackStatus update, discovered entity IDs and unload. Use `python scripts/test_installed_release.py --archive /path/to/f1_sensor.zip --version <expected-version>` to test a downloaded draft or published artifact, with its adjacent `.sha256` and `.spdx.json` files. This validates the original archive and extracts its exact bytes without rebuilding or changing it. Without `--archive`, the normal CI check builds and verifies a temporary archive from the checkout. Neither mode claims live F1 network or physical-dashboard validation.

## Check selection and verdicts

Changes select checks by impact on every development and PR branch, including promotions. Translation-only work selects translation verification. Issue metadata and synchronization automation select automation tests; documentation tooling selects documentation and its automation contracts. Shared verification/environment inputs conservatively select the full safety profile. Unknown inputs retain a conservative fallback. HACS/hassfest remain required remote validation when integration inputs change.

`CI required` is the product/affected-change verdict, not an additional independent test suite. Its summary identifies failed root jobs rather than presenting downstream gates as separate defects. Beta/main release verification separates product checks, documentation verification and full release security readiness. Creating a release draft requires successful product verification and security readiness; an unrelated documentation presentation failure does not redefine product correctness. An affected documentation PR still requires its documentation tests.

PR reuse accepts only successful same-repository `dev`/`content` pushes with an identical complete Git tree and all applicable jobs passed. Evidence must be at most two hours old when selected. Later verification still checks immutable run, attempt, commit, tree and job identity, but does not fail solely because time elapsed while other jobs ran. This can include remote HACS/hassfest, never registry audits. Missing trust must not become success. Release product checks run fresh. Local receipts and contributor artifacts are not substitutes for GitHub evidence.

## Living translations

Both nested integration catalogs and flat card catalogs use one structural validator. Duplicate keys, malformed structure, invalid values and blank or incorrect placeholder values for active keys fail. Missing target keys use English fallback. Obsolete unused target keys awaiting Weblate cleanup produce warnings and are not a functional error. Tests derive real-language expectations from independent catalog reads and use sentinel catalogs to prove region-to-base-to-English fallback, language selection and action wiring. Wording and language counts are not fixed contracts.

## Local readiness

Local and remote wrappers share executable commands through `scripts/verification.py`. Run `npm run setup:ci`, then `npm run verify:changed` before committing. Use `npm run verify:dev` for a complete snapshot and `npm run verify:release -- --target beta` or `--target main` for full destination readiness, including full security health. Local verification collects every selected failure and records named command results in `test-results/verification.json`. A green changed-profile result is not a promise that every release-safety condition passed.

Preflight validates pinned tools, locked installation/browser inputs, workflow syntax and manifest order. Unknown comparisons do not produce an empty successful plan. Evidence binds to complete source contents and installed tool/dependency metadata; drift invalidates it. GitHub merge-result verification and HACS/hassfest remain explicitly pending until their actual remote jobs pass.

## Security responsibilities

Ordinary development and promotion changes block newly introduced high/critical dependency exposure relative to the immutable base, using current advisories for both snapshots. Changes to the evaluator or risk policy require the full gate. Release security readiness and daily branch health evaluate all high/critical findings. Low/moderate findings are warnings. An unchanged release-tooling risk does not masquerade as a product regression, but an unaccepted severe risk still prevents release creation. Development dependencies are not blindly excluded: build and release tools can have their own exposure and credentials.

Each advisory is matched to its actual lockfile version and path using the pinned npm's maintained semver implementation. A package-wide node list cannot falsely assign a version-specific vulnerability to an unaffected copy. Invalid/missing evidence is an unavailable assessment, not a clean report. Approved exceptions remain explained, path-scoped and expiring; active expired exceptions fail full security readiness. Repaired dependencies and retired exceptions may disappear without breaking their regression tests.

The daily monitor must be launched from the default branch. Its trusted evaluator reads only dependency snapshots from `dev`, `beta` and `main`, without installing or executing the scanned branch. During rollout, an older stable branch can therefore be assessed by reviewed tools independently of product-code promotion. Merely adding a schedule on dev/beta does not activate it.

## Documentation delivery

Push verification never defers to queued or successful PR-head evidence: PRs test merge results, which may differ. Metadata edits do not restart code checks; target changes do. Documentation delivery uses separate workflows and immutable verified commits for both channels, so publication failures cannot masquerade as product-test failures. Cleanup treats an already missing merged branch as an idempotent success without hiding permission errors or deleting an advanced branch.

The independent publisher starts on beta/main pushes using that branch's workflow. It requires authoritative successful product and documentation jobs from the same trusted release-verification run and exact commit/attempt. Release-tool security or draft-creation failure alone cannot invalidate verified documentation. Failed, skipped or missing product/documentation proof never authorizes publication. Both the target and companion channel use immutable verified sources; an older verified main remains compatible with the first beta promotion. Superseded pushes do not publish, and waiting does not hold the Pages lock. Documentation publication never publishes a release draft.

## Regression acceptance

Legitimate rewording, a new locale, obsolete unused translation cleanup, equivalent module syntax, removal of an affected dependency and retirement of a temporary exception must pass. Broken fallback, invalid placeholders, missing supported cards, leaking subscriptions, unsafe HA callbacks, corrupt packages, new severe dependency paths and unverified publication sources must still fail. Success is not established by one green PR: inspect first-attempt browser outcomes and follow normal development, promotion and publication runs separately.
