---
id: context7
title: Use the documentation with an AI assistant
description: Ground automation suggestions in F1 Sensor documentation and verify the result against your own setup.
---

The F1 Sensor documentation is available on [Context7](https://context7.com/websites/nicxe_github_io_f1_sensor), a platform that serves up-to-date library documentation directly to AI coding assistants.

This means AI tools like **Claude Code**, **Cursor**, **GitHub Copilot**, and others can fetch the current F1 Sensor docs on demand and use them as grounding context to help it use documented entity names, attribute keys and examples. Always check the proposed configuration against your installed version and actual entities.

---

## Why this matters

AI assistants trained on general data often get integration-specific details wrong. They may invent entity names, use outdated attribute keys, or produce YAML that doesn't match the actual integration.

A connected documentation tool can retrieve relevant F1 Sensor pages. Retrieval improves the available context, but does not guarantee a correct automation or that the indexed documentation matches your installed release.

---

## How to use it

### With Claude Code or any MCP-compatible agent

If your assistant has Context7 configured, ask it to look up F1 Sensor before drafting an automation. The words `use context7` alone do not install or connect the tool.

**Example prompt:**
```text
use context7

Create a Home Assistant automation that sends a notification when the race starts and
another one when a safety car is deployed.
```

### With Cursor or other AI editors

Install the [Context7 MCP server](https://context7.com/docs/getting-started) in your editor, then use `use context7` the same way.

### Direct library ID

If your tool requires a library ID, use:

```text
/websites/nicxe_github_io_f1_sensor
```

---

## What the AI gets access to

Depending on the query and the current index, the assistant can retrieve relevant sections covering:

- All sensor entities with their states and attributes
- Live data entities (track status, race control, timing)
- Configuration options
- Automation and blueprint examples
- Service calls and helper entities

---
:::tip
Context7 is most useful when writing automations or scripts that reference specific F1 Sensor entities. For general questions about Home Assistant, Context7 is not needed.
:::
