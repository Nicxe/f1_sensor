<!--
Target standalone documentation or blueprint work to `content`; target code to
`dev`. Maintainers promote code with merge commits: `dev` → `beta` → `main`.
-->

## Summary

<!-- What changed, why, and how does it affect users? Keep this short. -->

## Release editorial (promotion PRs only)

<!-- Use only for `dev` → `beta` and `beta` → `main`. Leave it blank for a routine release. -->
<!-- Write the short user-facing introduction for the whole release here. Do not list individual fixes or features; those come from the preserved Conventional Commits. This text is inserted into the release draft after merge. -->
<!-- release-editorial:start -->
<!-- Write one to three user-facing sentences here. You can include a beta-testing focus or thank contributors. -->
<!-- release-editorial:end -->

## Testing

<!-- What did you verify? Add only the relevant checks. -->

## Checklist

- [ ] Correct target branch and Conventional Commit
- [ ] Relevant tests or Home Assistant checks pass
- [ ] English source text is updated; target-language translations are handled through Weblate when applicable
- [ ] Breaking changes are either absent, or marked with `!` and include the required user action
