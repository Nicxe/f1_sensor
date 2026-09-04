# Contributing

Thank you for your interest in contributing to f1_sensor!

## Branch model

This project uses two contribution paths depending on what you are changing.

### Code changes

For changes to the integration itself — sensors, binary sensors, configuration flow, coordinator logic, bundled Live Data Card code, fixes, features, tests — use the code path:

- `dev` — the active development branch. All code contributions must target this branch.
- `beta` — pre-release testing. Promoted from `dev` by the maintainer.
- `main` — stable production releases. Promoted from `beta` by the maintainer.

The `beta` and `main` branches are managed exclusively by the maintainer. Incorrectly targeted contributor PRs receive guidance explaining how to edit the base branch. Only maintainer promotions target beta or main.

### Documentation and blueprint changes

For changes to documentation (`docs/`) or blueprints (`blueprints/`) that are independent of any code change, use the content path:

- `content` — the dedicated branch for documentation and blueprint contributions. PRs targeting this branch are merged directly to `main` by the maintainer, without going through beta.

No version bump or release is triggered when only documentation or blueprint files change.

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

## CI migration

Full selective CI, HA 2026.9 compatibility and the 95 percent runtime line-coverage gate are active on `dev` and `beta`. The older `main` and `content` code keeps its existing test baseline until the next normal `dev → beta → main` promotion. No unreleased integration code is copied into stable solely for this migration.

Issue labels and release comments already use tested, trusted scripts. Conflict checks only read PR metadata and update labels; they never execute fork code. Synchronization preserves the exact published commit and later work without force pushes. Its PRs are explicitly verified: full `CI required` for dev/beta, and clearly named `Legacy content verification` for the temporary content baseline. No additional reviewer is required. Full CI replaces this bootstrap during normal code promotion; remove the temporary `sync-legacy.yml` verifier after the full content rollout.
