---
id: dependency-and-source-policy
title: Dependency and data-source policy
description: Maintain dependency, source, release archive, and documentation evidence for F1 Sensor.
---

This policy describes the checks maintainers use for dependencies, external sources, and release contents. It also links the supporting evidence and documentation workflow.

## Runtime and build dependencies

F1 Sensor ships without third-party Python runtime dependencies. JavaScript packages in the repository support documentation, testing, and releases; they are not copied into the Home Assistant release archive.

Every pull request runs an npm audit gate. A finding can be temporarily accepted only when it is build-only, has no upstream fix, names the exact advisory, explains the exposure, and has an expiry date. Expired entries fail the quality check. Runtime findings are never accepted through this allowlist.

## External data and media

External data and media sources are listed in [`quality/data-sources.json`](https://github.com/Nicxe/f1_sensor/blob/dev/quality/data-sources.json). Maintainers must review the source URL, terms or license, attribution requirements, data minimisation, and continued necessity before the review date and whenever a source changes. The release quality workflow fails stale source reviews.

## Release archive

The release builder packages only the runtime allowlist, scans the archive for common secret patterns, produces a SHA-256 checksum and SPDX SBOM, and verifies deterministic output. Tests, replay fixtures, maintenance utilities, local instructions, and documentation are excluded from the release archive.


## Documentation changes

Standalone content corrections follow the `content` contribution path. Docusaurus components, CSS, configuration, build tooling, tests, and documentation tied to unreleased code follow `dev`. The [contribution guide](https://github.com/Nicxe/f1_sensor/blob/dev/CONTRIBUTING.md) defines the branch and review workflow.

Run `npm run test:docs` for the production build, documentation checks, and browser tests. Use `npm run capture:docs-cards` when updating reproducible card images, then visually inspect the results. Follow the [documentation style guide](https://github.com/Nicxe/f1_sensor/blob/dev/doc-style-guide.md) for metadata, page templates, images, and navigation.

Keep public routes and important fragment links working when pages are reorganized. The Token Helper pairing URL and its parameters are part of the integration’s behavior; its privacy policy also retains a stable URL.

## Evidence and security reporting

[Bronze evidence](https://github.com/Nicxe/f1_sensor/blob/dev/quality/bronze-evidence.md) links the internal quality checklist to executable checks. It is an internal evidence register, not a claim of official Home Assistant certification. Update evidence only after the corresponding behavior has been verified.

Use the [security policy](https://github.com/Nicxe/f1_sensor/blob/dev/SECURITY.md) for supported versions and private vulnerability reporting. Do not publish credentials, pairing data, or private diagnostic archives in public issues.
