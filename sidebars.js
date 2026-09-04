/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  "tutorialSidebar": [
    "introduction",
    {
      "type": "category",
      "label": "Get started",
      "link": {
        "type": "doc",
        "id": "getting-started/installation"
      },
      "items": [
        "getting-started/installation",
        "getting-started/add-integration",
        "getting-started/first-dashboard",
        "getting-started/release-channels"
      ]
    },
    {
      "type": "category",
      "label": "Dashboards",
      "link": {
        "type": "doc",
        "id": "cards/cards-overview"
      },
      "items": [
        "cards/cards-overview",
        "cards/installation",
        "cards/shared-options",
        {
          "type": "category",
          "label": "Race weekend",
          "items": [
            "cards/weekend-hub",
            "cards/next-race",
            "cards/race-weather",
            "cards/season-calendar",
            "cards/live-session"
          ]
        },
        {
          "type": "category",
          "label": "Live timing",
          "items": [
            "cards/qualifying-timing",
            "cards/practice-timing",
            "cards/race-lap",
            "cards/starting-grid",
            "cards/tyre-statistics",
            "cards/pit-stops",
            "cards/driver-lap-times",
            "cards/track-map"
          ]
        },
        {
          "type": "category",
          "label": "Officials",
          "items": [
            "cards/race-control",
            "cards/fia-documents",
            "cards/investigations",
            "cards/track-limits"
          ]
        },
        {
          "type": "category",
          "label": "Results and championship",
          "items": [
            "cards/results",
            "cards/lap-position-progression",
            "cards/championship-drivers",
            "cards/championship-teams",
            "cards/season-progression"
          ]
        },
        {
          "type": "category",
          "label": "Replay",
          "items": [
            "cards/replay-control"
          ]
        }
      ]
    },
    {
      "type": "category",
      "label": "Guides",
      "link": {
        "type": "doc",
        "id": "features/overview"
      },
      "items": [
        "features/overview",
        "features/live-delay",
        "features/replay-mode",
        "features/no-spoiler-mode",
        "features/f1tv-auth",
        "help/f1tv-auth-setup",
        "features/track-map",
        "features/favorite-driver",
        "features/weekend-analysis",
        "features/incident-detection",
        {
          "type": "category",
          "label": "Automations",
          "link": {
            "type": "doc",
            "id": "automation"
          },
          "items": [
            "automation",
            "blueprints/track-status-light",
            "blueprints/race-control-notifications",
            "blueprints/incident-notifications",
            "blueprints/replay-sync"
          ]
        }
      ]
    },
    {
      "type": "category",
      "label": "Reference",
      "link": {
        "type": "doc",
        "id": "reference/overview"
      },
      "items": [
        "reference/overview",
        {
          "type": "doc",
          "id": "entities/static-data"
        },
        {
          "type": "doc",
          "id": "entities/live-data"
        },
        {
          "type": "category",
          "label": "Schedule and weather",
          "items": [
            "entities/next-race",
            "entities/track-time",
            "entities/current-season",
            "entities/season-calendar",
            "entities/race-week",
            "entities/next-race-weather",
            "entities/weather-summary",
            "entities/track-weather"
          ]
        },
        {
          "type": "category",
          "label": "Session and track",
          "items": [
            "entities/session-status",
            "entities/current-session",
            "entities/session-time-elapsed",
            "entities/session-time-remaining",
            "entities/race-three-hour-limit",
            "entities/track-status",
            "entities/safety-car",
            "entities/race-lap",
            "entities/formation-start",
            "entities/overtake-mode",
            "entities/straight-mode"
          ]
        },
        {
          "type": "category",
          "label": "Drivers and timing",
          "items": [
            "entities/driver-list",
            "entities/favorite-driver",
            "entities/driver-positions",
            "entities/starting-grid",
            "entities/top-three",
            "entities/current-tyres",
            "entities/tyre-statistics",
            "entities/pit-stops",
            "entities/team-radio"
          ]
        },
        {
          "type": "category",
          "label": "Results and championship",
          "items": [
            "entities/last-race-results",
            "entities/sprint-results",
            "entities/season-results",
            "entities/lap-position-progression",
            "entities/driver-standings",
            "entities/constructor-standings",
            "entities/driver-points-progression",
            "entities/constructor-points-progression",
            "entities/championship-prediction-drivers",
            "entities/championship-prediction-teams"
          ]
        },
        {
          "type": "category",
          "label": "Officials and incidents",
          "items": [
            "entities/race-control",
            "entities/track-limits",
            "entities/investigations",
            "entities/fia-decision-documents",
            "entities/on-track-incident",
            "entities/possible-on-track-incident"
          ]
        },
        "reference/values",
        "reference/device-triggers",
        "entities/events",
        "entities/diagnostics",
        {
          "type": "category",
          "label": "Playback and delay controls",
          "items": [
            "reference/live-delay-controls",
            "reference/replay-controls"
          ]
        }
      ]
    },
    {
      "type": "category",
      "label": "Help",
      "link": {
        "type": "doc",
        "id": "help/overview"
      },
      "items": [
        "help/overview",
        "help/faq",
        "help/issues",
        "help/debug-logging",
        "help/contact",
        "help/f1tv-token-helper"
      ]
    },
    {
      "type": "category",
      "label": "Community",
      "link": {
        "type": "doc",
        "id": "example/overview"
      },
      "items": [
        "example/overview",
        "example/e-ink",
        "example/custom-card",
        "example/custom-card-by",
        "support"
      ]
    },
    {
      "type": "category",
      "label": "Advanced and contributing",
      "items": [
        "help/beta-tester",
        "help/developer-mode",
        "features/context7",
        "maintainers/dependency-and-source-policy"
      ]
    }
  ]
};

export default sidebars;
