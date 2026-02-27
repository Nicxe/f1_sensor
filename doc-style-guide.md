# Documentation Style Guide

Format and structure patterns for F1 Sensor documentation.

## Frontmatter

Every page requires YAML frontmatter:

```yaml
---
id: feature-name
title: Feature Title
---
```

Use kebab-case for `id`. Title should be user-friendly.

## Page Structure

### Introduction

Start with 1-2 sentences explaining what the feature does and why a user would use it.

### Sections

Use `##` for main sections, `###` for subsections.

Common section patterns:

- Overview / How it works
- Step-by-step instructions (numbered)
- Configuration options
- Limitations / Notes

## Entity Documentation

For sensors and other entities, use this structure:

```markdown
## Entity Name

Brief description of what this entity does and when it updates.

**State**
- Description of possible state values

**Example**
\`\`\`text
example_value
\`\`\`

**Attributes**

| Attribute | Type | Description |
| --- | --- | --- |
| attribute_name | string | What this attribute contains |
| other_attribute | number | What this represents |
```

If no attributes: `| (none) | | No extra attributes |`

## Admonitions

Use Docusaurus admonition syntax:

```markdown
:::info
Information note
:::

:::tip
Helpful tip
:::

::::info Title
Note with custom title
::::
```

Available types: `info`, `tip`, `warning`, `danger`

## Links

Internal links use root-relative paths:

```markdown
[Link text](/entities/live-data)
[Installation guide](/getting-started/installation)
```

## Images

```markdown
![Alt text](/img/filename.png)
```

Images go in `/static/img/`. Use descriptive filenames.

## Code Blocks

For YAML configuration:

```markdown
\`\`\`yaml
automation:
  trigger:
    - platform: state
      entity_id: sensor.f1_track_status
\`\`\`
```

For state examples:

```markdown
\`\`\`text
CLEAR
\`\`\`
```

## Step-by-Step Instructions

Use numbered lists with clear action verbs:

```markdown
### Step 1 - Install the integration

1. Open **HACS** in Home Assistant
2. Search for **F1 Sensor**
3. Click **Download**
```

Bold UI elements: **Settings**, **Add Integration**, **Download**

## Collapsible Sections

For optional or advanced content:

```markdown
<details>
  <summary>Advanced configuration</summary>

Content goes here.

</details>
```

## Writing Style

- Use present tense
- Address the user directly ("you can", "this lets you")
- Avoid jargon and implementation details
- Explain what things do, not how they work internally
- Keep sentences short and scannable

## Limitations Section

When documenting limitations:

```markdown
:::info
This sensor is active only during race and sprint sessions.
:::
```

Or inline: "Updates approximately every minute during an active session."

## File Organization

| Type | Location |
| --- | --- |
| Getting started | `docs/getting-started/` |
| Entity reference | `docs/entities/` |
| Examples | `docs/example/` |
| Help/FAQ | `docs/help/` |
| Standalone pages | `docs/` |

## Sidebar

New pages must be added to `sidebars.js`:

```javascript
{
  type: 'category',
  label: 'Category Name',
  items: ['folder/page-id'],
}
```

Or as standalone:

```javascript
{
  type: 'doc',
  label: 'Page Title',
  id: 'page-id',
}
```
