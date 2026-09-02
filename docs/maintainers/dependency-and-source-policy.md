# Dependency and data-source policy

F1 Sensor ships without third-party Python runtime dependencies. JavaScript packages in the repository support documentation, testing, and releases; they are not copied into the Home Assistant release archive.

Every pull request runs an npm audit gate. A finding can be temporarily accepted only when it is build-only, has no upstream fix, names the exact advisory, explains the exposure, and has an expiry date. Expired entries fail the quality check. Runtime findings are never accepted through this allowlist.

External data and media sources are listed in `quality/data-sources.json`. Maintainers must review the source URL, terms or license, attribution requirements, data minimisation, and continued necessity before the review date and whenever a source changes. The release quality workflow fails stale source reviews.

The release builder packages only the runtime allowlist, scans the archive for common secret patterns, produces a SHA-256 checksum and SPDX SBOM, and verifies deterministic output. Tests, replay fixtures, maintenance utilities, local instructions, and documentation are excluded from the release archive.
