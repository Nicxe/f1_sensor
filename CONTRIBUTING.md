# Contributing

Thank you for your interest in contributing to f1_sensor!

## Branch model

This project uses two contribution paths depending on what you are changing.

### Code changes

For changes to the integration itself — sensors, binary sensors, configuration flow, coordinator logic, fixes, features, tests — use the code path:

- `dev` — the active development branch. All code contributions must target this branch.
- `beta` — pre-release testing. Promoted from `dev` by the maintainer.
- `main` — stable production releases. Promoted from `beta` by the maintainer.

The `beta` and `main` branches are managed exclusively by the maintainer. PRs targeting those branches are closed automatically.

### Documentation and blueprint changes

For changes to documentation (`docs/`) or blueprints (`blueprints/`) that are independent of any code change, use the content path:

- `content` — the dedicated branch for documentation and blueprint contributions. PRs targeting this branch are merged directly to `main` by the maintainer, without going through beta.

No version bump or release is triggered when only documentation or blueprint files change.

### Which branch should I target?

| What I am changing | Target branch |
|---|---|
| Integration code, sensors, fixes, features | `dev` |
| Tests only | `dev` |
| Documentation for an upcoming code change | `dev` (keep docs with the code) |
| Standalone documentation fix or update | `content` |
| New or updated blueprint (standalone) | `content` |

If your PR mixes code changes with documentation changes, target `dev`. The docs will be published when the code ships.

## How to submit a pull request

1. Fork the repository.
2. Identify the correct target branch using the table above.
3. Create a feature branch based on that target branch in your fork.
4. Make your changes and commit them with clear messages.
5. Open a pull request against the correct branch of this repository.

## Questions

If you are unsure whether a change fits the project direction, open an issue before starting work. This prevents effort being spent on contributions that may not be accepted.
