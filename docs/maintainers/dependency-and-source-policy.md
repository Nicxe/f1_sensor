---
id: dependency-and-source-policy
title: Dependency and data-source policy
description: Maintain dependency, source, release archive, and documentation evidence for F1 Sensor.
---

This policy describes the checks maintainers use for dependencies, external sources, and release contents. It also links the supporting evidence and documentation workflow.

## Runtime and build dependencies

F1 Sensor ships without third-party Python runtime dependencies. JavaScript packages in the repository support documentation, testing, and releases; they are not copied into the Home Assistant release archive.

Dependency and tooling changes run npm audit. Ordinary changes, including promotions, compare current advisories against both exact lockfiles and block newly introduced high or critical exposure. Release security readiness, security-policy changes and daily checks inspect all current high and critical findings, including development dependencies. Low and moderate findings remain visible warnings. An unavailable or invalid registry response is an incomplete assessment, not a fabricated vulnerability or a clean report.

Each advisory is evaluated against the installed version and dependency path. A finding in a release tool does not mean that the Home Assistant integration ships that package, but build and release tools can still have security exposure. Unaccepted severe findings prevent release creation. The daily monitor uses reviewed tools to read dependency snapshots from `dev`, `beta` and `main` without installing or executing the scanned branch. Its launcher must exist on the default branch before its schedule can run.

A finding can be temporarily accepted only when it is build-only, has no upstream fix, names the exact advisory and installed dependency path, explains the exposure, and has an expiry date. An active expired exception fails full security readiness; an expired entry for a vulnerability no longer present does not block unrelated work. Removing a repaired dependency or retired exception is valid. Runtime findings are never accepted through this allowlist. Weekly grouped npm and GitHub Actions version-update PRs target `dev`; major updates remain separate. No new automatic merging is enabled by this policy.

## External data and media

External data and media sources are listed in [`quality/data-sources.json`](https://github.com/Nicxe/f1_sensor/blob/dev/quality/data-sources.json). Maintainers must review the source URL, terms or license, attribution requirements, data minimisation, and continued necessity before the review date and whenever a source changes. The release quality workflow fails stale source reviews.

## Release archive

The release builder packages only the runtime allowlist, scans the archive for common secret patterns, produces a SHA-256 checksum and SPDX SBOM, and verifies deterministic output. Tests, replay fixtures, maintenance utilities, local instructions, and documentation are excluded from the release archive.


## Documentation changes

Standalone content corrections follow the `content` contribution path. Docusaurus components, CSS, configuration, build tooling, tests, and documentation tied to unreleased code follow `dev`. The [contribution guide](https://github.com/Nicxe/f1_sensor/blob/dev/CONTRIBUTING.md) defines the branch and review workflow.

Run `npm run test:docs` for the production build, documentation checks, and browser tests. Use `npm run capture:docs-cards` when updating reproducible card images, then visually inspect the results. Follow the [documentation style guide](https://github.com/Nicxe/f1_sensor/blob/dev/doc-style-guide.md) for metadata, page templates, images, and navigation.

Product verification, documentation verification and release security readiness have separate results. Publication requires authoritative successful product and documentation jobs for immutable commits in both channels. A failed Pages deployment is a delivery failure, not an integration regression. A release-tool security or draft-creation failure alone does not invalidate verified documentation. Release publication remains manual.

Publication starts on a push to beta or main and waits for the exact commit's trusted product and documentation evidence. Failed, skipped or missing evidence never authorizes publication. Beta documentation does not require promotion to main, including the first publication-workflow rollout. After repairing verification or a waiting timeout, rerun Documentation publication without another code change or release publication.

Keep public routes and important fragment links working when pages are reorganized. The Token Helper pairing URL and its parameters are part of the integration’s behavior; its privacy policy also retains a stable URL.

## Evidence and security reporting

[Bronze evidence](https://github.com/Nicxe/f1_sensor/blob/dev/quality/bronze-evidence.md) links the internal quality checklist to executable checks. It is an internal evidence register, not a claim of official Home Assistant certification. Update evidence only after the corresponding behavior has been verified.

Use the [security policy](https://github.com/Nicxe/f1_sensor/blob/dev/SECURITY.md) for supported versions and private vulnerability reporting. Do not publish credentials, pairing data, or private diagnostic archives in public issues.
