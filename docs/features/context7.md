---
id: context7
title: AI Assistant Support via Context7
---

The F1 Sensor documentation is available on [Context7](https://context7.com/websites/nicxe_github_io_f1_sensor), a platform that serves up-to-date library documentation directly to AI coding assistants.

This means AI tools like **Claude Code**, **Cursor**, **GitHub Copilot**, and others can fetch the current F1 Sensor docs on demand and use them as grounding context — giving you accurate entity names, attribute keys, and YAML examples without hallucination.

---

## Why this matters

AI assistants trained on general data often get integration-specific details wrong. They may invent entity names, use outdated attribute keys, or produce YAML that doesn't match the actual integration.

With Context7, your AI assistant fetches the real documentation at query time. The result is correct automation code based on what F1 Sensor actually exposes.

---

## How to use it

### With Claude Code or any MCP-compatible agent

Add `use context7` to your prompt. The agent will automatically resolve and fetch the F1 Sensor documentation before responding.

**Example prompt:**
```
use context7

Create a Home Assistant automation that sends a notification when the race starts and
another one when a safety car is deployed.
```

### With Cursor or other AI editors

Install the [Context7 MCP server](https://context7.com/docs/getting-started) in your editor, then use `use context7` the same way.

### Direct library ID

If your tool requires a library ID, use:

```
/websites/nicxe_github_io_f1_sensor
```

---

## What the AI gets access to

When Context7 is invoked, the AI receives the full F1 Sensor documentation including:

- All sensor entities with their states and attributes
- Live data entities (track status, race control, timing)
- Configuration options
- Automation and blueprint examples
- Service calls and helper entities

---

:::tip
Context7 is most useful when writing automations or scripts that reference specific F1 Sensor entities. For general questions about Home Assistant, Context7 is not needed.
:::
