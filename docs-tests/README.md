# Documentation verification

Run `npm run setup:ci`, then `npm run verify:changed` for the affected checks in
the project's pinned environment. The documentation lane builds the site and
runs the build guards and browser journeys. Local success is separate from
GitHub checks and publication.

## Building both documentation channels locally

When changing `F1_DOCS_BASE_URL` in one checkout, use
`DOCUSAURUS_NO_PERSISTENT_CACHE=1` for the channel builds, or run
`npm run clear` before switching. Docusaurus 3.10.2 can otherwise reuse compiled
font URLs from the other base path. `clear` also removes the local build output.
The publisher already builds stable and beta in separate checkouts.

For a beta build, set `F1_DOCS_CHANNEL=beta` and
`F1_DOCS_BASE_URL=/f1_sensor/beta/`. Use a separate output directory with
`npm run build -- --out-dir <directory>`. Point the tests at that directory with
`F1_DOCS_TEST_BUILD_DIR`; keep `F1_DOCS_BASE_URL` set for both
`npm run test:docs:build` and `npm run test:docs:browser`.
`F1_DOCS_TEST_PORT` selects a separate test server port.

## Coverage and manual checks

The guards cover older routes and anchors, privacy content, local images and
stylesheet assets, complete community downloads, and module registry coverage.
Browser journeys cover search, setup navigation, filters, native disclosure
links, the module list without JavaScript, loaded fonts, keyboard access,
reflow, contrast, and user-controlled media.

Also inspect the rendered desktop and mobile pages, real browser zoom, and
screen-reader behavior. Automated accessibility checks and a readable
accessibility tree do not establish a successful VoiceOver test. Record an
unavailable manual check as pending, with its owner; do not call it passed.
