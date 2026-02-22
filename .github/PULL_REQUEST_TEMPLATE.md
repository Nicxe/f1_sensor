<!--
  IMPORTANT: Target the correct branch for your change.
  - Documentation or blueprint changes (standalone, no code): target the `content` branch
  - Code changes (integration, sensors, fixes, features, tests): target the `dev` branch
  - PRs targeting `main` or `beta` are closed automatically.
  If you are unsure whether your change fits the project direction, open an issue first.
-->

## What does this PR do?

<!-- Describe what this PR changes and why. Be specific — what behavior changes, what was broken, what is new. -->

## Type of change

<!-- Check all that apply -->

- [ ] Bug fix (corrects existing behavior without breaking anything)
- [ ] New feature (adds functionality to the integration)
- [ ] Breaking change (existing automations, entities, or config options will stop working or behave differently)
- [ ] Blueprint (new or updated blueprint)
- [ ] Documentation only (no code changes)
- [ ] Refactoring or internal cleanup (no user-visible changes)
- [ ] Dependency update

## What area does this affect?

<!-- Check all that apply -->

- [ ] Integration core (data fetching, coordinator, SignalR, API)
- [ ] Sensor entities
- [ ] Binary sensors, buttons, selects, switches, or other platforms
- [ ] Configuration flow or options
- [ ] Live delay / calibration
- [ ] Replay mode
- [ ] Blueprint
- [ ] Documentation
- [ ] Tests
- [ ] CI / release pipeline

## Have you tested this?

<!-- Describe how you tested the change. Be specific. -->

- [ ] Tested locally with a real Home Assistant instance
- [ ] Tested with replay mode (if applicable)
- [ ] Verified that existing automations or dashboards still work as expected after the change

## Checklist

- [ ] I have read [CONTRIBUTING.md](../CONTRIBUTING.md) and am targeting the correct branch
- [ ] My PR targets `content` (for standalone docs/blueprint changes) or `dev` (for code changes)
- [ ] The code has no commented-out blocks left behind
- [ ] Code is formatted with Ruff (`ruff format custom_components`) — if applicable
- [ ] Code passes Ruff lint check (`ruff check custom_components`) — if applicable
- [ ] Tests have been added or updated to cover the change — if applicable
- [ ] All tests pass locally (`pytest custom_components/f1_sensor/tests`) — if applicable
- [ ] Hassfest validation passes (`python3 -m script.hassfest`) — if applicable
- [ ] Translations updated if new config options or UI strings were added — if applicable
- [ ] This PR has no merge conflicts with its target branch

If this PR changes user-facing behavior, entities, or configuration:

- [ ] I have noted what users need to update or be aware of in the PR description above

If this PR adds or changes a blueprint:

- [ ] The blueprint has been imported and tested in Home Assistant
- [ ] Triggers and conditions work as expected in a live environment

If this is a breaking change:

- [ ] I have clearly described in the PR description what will break and what users need to do to adapt
