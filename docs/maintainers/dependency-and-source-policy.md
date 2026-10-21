---
id: dependency-and-source-policy
title: Dependency and data-source policy
description: Maintain dependency, source, release archive, and documentation evidence for F1 Sensor.
---

This policy describes the checks maintainers use for dependencies, external sources, and release contents. It also links the supporting evidence and documentation workflow.

## Runtime and build dependencies

F1 Sensor ships without third-party Python runtime dependencies. JavaScript packages in the repository support documentation, testing, and releases; they are not copied into the Home Assistant release archive.

Dependency and tooling changes run npm audit. Development changes compare with the exact base lockfile and block newly introduced high or critical exposure. Promotions, releases, security-policy changes, and daily checks on `dev`, `beta`, and `main` inspect all current high and critical findings, including development dependencies. Low and moderate findings remain visible warnings. An unavailable or invalid registry response fails with a transport diagnostic, not a fabricated vulnerability.

A finding can be temporarily accepted only when it is build-only, has no upstream fix, names the exact advisory and installed dependency path, explains the exposure, and has an expiry date. An active expired exception fails; an expired entry for a vulnerability no longer present does not block unrelated work. Runtime findings are never accepted through this allowlist. Weekly grouped npm and GitHub Actions version-update PRs target `dev`; major updates remain separate. No new automatic merging is enabled by this policy.

## External data and media

External data and media sources are listed in [`quality/data-sources.json`](https://github.com/Nicxe/f1_sensor/blob/dev/quality/data-sources.json). Maintainers must review the source URL, terms or license, attribution requirements, data minimisation, and continued necessity before the review date and whenever a source changes. The release quality workflow fails stale source reviews.

## Release archive

The release builder packages only the runtime allowlist, scans the archive for common secret patterns, produces a SHA-256 checksum and SPDX SBOM, and verifies deterministic output. Tests, replay fixtures, maintenance utilities, local instructions, and documentation are excluded from the release archive.


## Documentation changes

Standalone content corrections follow the `content` contribution path. Docusaurus components, CSS, configuration, build tooling, tests, and documentation tied to unreleased code follow `dev`. The [contribution guide](https://github.com/Nicxe/f1_sensor/blob/dev/CONTRIBUTING.md) defines the branch and review workflow.

Run `npm run test:docs` for the production build, documentation checks, and browser tests. Use `npm run capture:docs-cards` when updating reproducible card images, then visually inspect the results. Follow the [documentation style guide](https://github.com/Nicxe/f1_sensor/blob/dev/doc-style-guide.md) for metadata, page templates, images, and navigation.

Documentation verification and publication are separate workflows. Publication uses immutable commits from successful release verification for both channels. A failed Pages deployment is a delivery failure and does not invalidate product verification or publish a release draft. Release publication remains manual.

Publication starts on a push to `beta` or `main` and waits for successful verification of that same commit. Beta documentation does not require a promotion to `main`, including when the new publication workflow first reaches `beta`. If release verification succeeds only after a retry, rerun Documentation publication to deliver it without another code change.

Keep public routes and important fragment links working when pages are reorganized. The Token Helper pairing URL and its parameters are part of the integration’s behavior; its privacy policy also retains a stable URL.

## Evidence and security reporting

[Bronze evidence](https://github.com/Nicxe/f1_sensor/blob/dev/quality/bronze-evidence.md) links the internal quality checklist to executable checks. It is an internal evidence register, not a claim of official Home Assistant certification. Update evidence only after the corresponding behavior has been verified.

Use the [security policy](https://github.com/Nicxe/f1_sensor/blob/dev/SECURITY.md) for supported versions and private vulnerability reporting. Do not publish credentials, pairing data, or private diagnostic archives in public issues.
