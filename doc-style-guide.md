# Documentation Style Guide

Use this guide when changing the Docusaurus site, examples, or reference pages. Write public documentation in English and organize it around what the reader wants to do.

## Frontmatter

Every documentation page needs a stable `id`, a descriptive `title`, and a short `description`:

```yaml
---
id: track-status
title: Track Status
description: Use track flags and Safety Car states in F1 dashboards and automations.
---
```

Use kebab-case IDs. Keep existing routes when reorganizing content. Use `slug` only when the public route needs to differ from the normal file route; the introduction keeps `slug: /`.

## Page Structure

Start with one or two sentences explaining the outcome and who the page is for. Use `##` for main sections and `###` for subsections. Keep requirements visible before the user starts; put optional detail after the basic workflow.

### Guides

Use this order:

1. What the user can achieve.
2. Prerequisites and data availability.
3. Numbered setup or usage steps.
4. What the user should see when it works.
5. Common problems and recovery.
6. Useful next steps.

Put complete entity schemas in the reference area. A guide can summarize the controls and link to their reference without repeating every attribute.

### Card pages

Start with the card’s purpose and an accurate screenshot with a caption. Explain session, entity, and optional authentication requirements. Show the visual editor workflow first, then a minimal YAML example, card-specific options, empty or waiting states, and related references.

Shared options belong in the shared settings page. Do not copy the entire common table onto every card page. Link each card from the catalog and sidebar.

### Blueprint pages

Explain the result, provide the import link, list requirements, and show the smallest working configuration. Put optional filters, presence/media conditions, WLED controls, and advanced notification templates afterwards. Keep actual defaults and guards consistent with the blueprint source.

## Entity Documentation

Each focused entity page includes its standard entity ID, purpose, data availability, state, example, and attributes. Use this pattern:

````markdown
## State

`sensor.f1_example` reports a count, or has no value when the required data is missing.

```text
12
```

## Attributes

| Attribute | Type | Description |
| --- | --- | --- |
| example_attribute | number | What the value means and when it can be unknown |
````

If there are no extra attributes, use `| (none) | | No extra attributes |`.

Keep entity IDs, attribute names, enum values, and service/action names exact. Explain that existing installations can have renamed or older entity IDs. Distinguish `unknown`, `unavailable`, a paused replay, and missing upstream data instead of describing them as one failure.

## Admonitions

Use Docusaurus admonitions for information that changes a decision or prevents a common mistake:

```markdown
:::info[Optional F1TV access]
Public live timing works without a token. Some extra live data requires optional F1TV access.
:::
```

Use `tip` for a shortcut, `info` for context, and `warning` for a consequence the user needs to understand before acting. Avoid stacking several notices above the first useful instruction.

## Links

Use root-relative internal links:

```markdown
[Installation](/getting-started/installation)
[Track Status reference](/entities/track-status)
```

Link text should describe the destination. Do not use `#` as a placeholder link or send a specific feature link to the site homepage.

When splitting a page, preserve its existing route and heading anchors with short links to the new pages. `quality/docs-legacy-routes.json` records the previous routes. Keep a heading’s generated ID when its wording is unchanged. If a heading must be renamed, use Docusaurus’s explicit MDX heading ID so the old fragment remains part of the table of contents and link validation:

```markdown
## Formation start ready {/* #race-about-to-start--formation-lap */}
```

The Token Helper route `/help/f1tv-token-helper` is part of Home Assistant pairing. Preserve its URL and query/fragment behavior. Its privacy policy also keeps a stable URL. Do not introduce a generic redirect or tracking mechanism into pairing.

## Images

Keep product images in `static/img/` and use descriptive filenames, meaningful alt text, and a short caption when context matters:

```markdown
![Track Map displaying driver markers during replay](/img/track-map-replay.png)
```

Screenshots must show the real card or Home Assistant UI. State whether they use replay or demonstration data; do not present fixture data as a live session. Remove secrets and personal account information before adding images.

Use `npm run capture:docs-cards` to regenerate the reproducible card images. Review the output and image provenance before replacing existing assets. Prefer SVG/HTML for explanations and screenshots for product UI. Keep long animations optional, respect reduced motion, and provide the same instructions in text.

## Code Blocks

Specify a language: `yaml` for Home Assistant configuration, `json` for JSON payloads, `text` for state values, and `bash` for commands.

````markdown
```yaml
action: number.set_value
target:
  entity_id: number.f1_live_delay
data:
  value: 30
```
````

Say where the user should paste an example. Use placeholders only for values the user must replace, such as their notification target. Validate examples against the intended release’s entity and action contracts. Large complete payloads can be collapsed, but the field reference must stay readable and searchable.

## Step-by-Step Instructions

Use numbered lists and bold labels matching the actual UI: **Settings**, **Devices & services**, **Add card**. Do not rely on screenshots alone. State the observable result after a procedure and link to the relevant troubleshooting page.

## Collapsible Sections

Use native details for optional or lengthy material:

```markdown
<details>
<summary>Complete example payload</summary>

Optional reference content.

</details>
```

Never hide prerequisites, authentication requirements, or a consequence that must be understood before setup.

## Writing Style

Use present tense, short paragraphs, and direct instructions. Separate setup guides from exact reference details. Avoid guarantees such as perfect synchronization, complete data capture, or error-free AI-generated configuration.

Treat confirmed incident detection as a timing-based indication, not proof of a crash. Distinguish public live data, optional authenticated data, and archive-dependent replay. Mark unreleased features according to the site’s release/channel information.

## Limitations Section

Describe the specific condition and its effect: “Live Track Map requires usable position data during an active session.” Explain the next useful check. Do not turn every normal waiting state into an error.

## File Organization

| Content | Location |
| --- | --- |
| Installation and first-use guides | `docs/getting-started/` |
| Feature workflows | `docs/features/` |
| Card catalog and individual cards | `docs/cards/` |
| Entity references | `docs/entities/` |
| Controls, state values, and device triggers | `docs/reference/` |
| Ready-made automations | `docs/blueprints/` |
| Community examples | `docs/example/` |
| Troubleshooting and help | `docs/help/` |
| Maintainer policies | `docs/maintainers/` |

## Sidebar

Add every new canonical page to `sidebars.js` and to the relevant overview. Group references by user task; avoid a single unstructured list of dozens of entities. Compatibility bridges may remain accessible through their old URLs without competing with canonical pages in the main navigation.

## Verification

Run `npm run test:docs` to build and check documentation routes, links, and browser behavior. Review important pages on mobile and desktop, in light and dark mode, with keyboard navigation. Check search results, screenshots, tables, copyable examples, old fragments, and the Token Helper pairing route.

For changes that also touch integration or card behavior, run the required integration and frontend checks described in the repository instructions. A documentation preview is not evidence of real Home Assistant runtime behavior.
