<!--
  Target the correct branch:
  - Docs or blueprint changes (standalone, no code) → `content` branch
  - Code changes (integration, sensors, bundled card code, fixes, features, tests) → `dev` branch
  - PRs targeting `main` or `beta` are closed automatically.
  If you are unsure whether your change fits the project direction, open an issue first.
-->

## Description

<!-- What does this PR change, and why? Be specific about what behavior changes, what was broken, or what is new. -->

## Related issue

<!-- Link to the issue this PR fixes or relates to. If there is no issue, explain why the change is needed. -->

Fixes #

## Type of change

- [ ] 🐛 Bug fix (corrects existing behavior without breaking anything)
- [ ] 🚀 New feature (adds functionality)
- [ ] ⚠️ Breaking change (existing automations, entities, or config will stop working or behave differently)
- [ ] 🏎️ Bundled live data card code
- [ ] 📋 Blueprint (new or updated blueprint)
- [ ] 📚 Documentation only
- [ ] 🔧 Refactoring or internal cleanup

## How has this been tested?

<!-- Describe how you tested the change. Be specific about your setup and what you verified. -->

- [ ] Tested locally with a real Home Assistant instance
- [ ] Existing automations and dashboards still work as expected after the change

## Checklist

- [ ] I have read [CONTRIBUTING.md](../CONTRIBUTING.md) and am targeting the correct branch
- [ ] Changes under `custom_components/f1_sensor/www/**` target `dev` as bundled card code, not the standalone documentation path — if applicable
- [ ] Code is formatted and passes lint check (`ruff format` and `ruff check`) — if applicable
- [ ] Tests have been added or updated and pass locally — if applicable
- [ ] Translations updated if new UI strings were added — if applicable
- [ ] No merge conflicts with the target branch

<!-- Blueprint only -->
If this adds or changes a blueprint:

- [ ] The blueprint has been imported and tested in Home Assistant
- [ ] Triggers and conditions work as expected in a live environment

<!-- Breaking changes only -->
If this is a breaking change:

- [ ] I have clearly described what will break and what users need to do to adapt
