/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  "startedSidebar": [
    "getting-started/installation",
    "getting-started/add-integration",
    "getting-started/first-dashboard",
    {
      "type": "category",
      "label": "Updates and upgrades",
      "items": [
        "getting-started/release-channels",
        "getting-started/required-data-choice",
        "features/whats-new",
        {
          "type": "ref",
          "id": "help/beta-tester"
        }
      ]
    },
    {
      "type": "ref",
      "id": "features/card-data-and-sensors"
    },
    {
      "type": "ref",
      "id": "documentation",
      "label": "Browse all documentation"
    }
  ],
  "dashboardsSidebar": [
    "cards/cards-overview",
    "cards/modular",
    {
      "type": "category",
      "label": "Modules",
      "items": [
        "cards/timing",
        "cards/minisectors",
        "cards/pit-stops",
        "cards/team-radio",
        {
          "type": "ref",
          "id": "features/track-map"
        },
        {
          "type": "ref",
          "id": "features/weekend-analysis"
        },
        {
          "type": "ref",
          "id": "features/historical-results"
        }
      ]
    },
    "cards/layout",
    "cards/shared-options",
    "cards/modular-accessibility",
    "cards/modular-styling",
    "cards/modular-migration",
    "cards/installation",
    {
      "type": "ref",
      "id": "documentation",
      "label": "Browse all documentation"
    }
  ],
  "guidesSidebar": [
    "features/overview",
    {
      "type": "category",
      "label": "Watch live or later",
      "items": [
        "features/live-delay",
        "features/no-spoiler-mode",
        "features/replay-mode",
        "features/replay-seeking"
      ]
    },
    {
      "type": "category",
      "label": "Data and account access",
      "items": [
        "features/card-data-and-sensors",
        "features/f1tv-auth",
        "help/f1tv-auth-setup"
      ]
    },
    {
      "type": "category",
      "label": "Explore the session",
      "items": [
        "features/track-map",
        "features/favorite-driver",
        "features/weekend-analysis",
        "features/historical-results",
        "features/incident-detection",
        "features/team-radio-transcription"
      ]
    },
    {
      "type": "category",
      "label": "Automations",
      "link": {
        "type": "doc",
        "id": "automation"
      },
      "items": [
        "blueprints/track-status-light",
        "blueprints/race-control-notifications",
        "blueprints/incident-notifications",
        "blueprints/replay-sync"
      ]
    },
    {
      "type": "ref",
      "id": "documentation",
      "label": "Browse all documentation"
    }
  ],
  "referenceSidebar": [
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
    },
    {
      "type": "ref",
      "id": "reference/card-data-api"
    },
    {
      "type": "ref",
      "id": "documentation",
      "label": "Browse all documentation"
    }
  ],
  "helpSidebar": [
    "help/overview",
    "help/faq",
    "help/issues",
    "help/debug-logging",
    "help/contact",
    {
      "type": "category",
      "label": "Account pairing",
      "items": [
        "help/f1tv-token-helper",
        "help/f1tv-token-helper-privacy"
      ]
    },
    {
      "type": "ref",
      "id": "documentation",
      "label": "Browse all documentation"
    }
  ],
  "communitySidebar": [
    "example/overview",
    "example/e-ink",
    "example/custom-card",
    "example/custom-card-by",
    "help/translations",
    "support",
    {
      "type": "ref",
      "id": "documentation",
      "label": "Browse all documentation"
    }
  ],
  "advancedSidebar": [
    "features/f1tv-access-evidence",
    "features/track-map-markings",
    "reference/card-data-api",
    "help/developer-mode",
    "help/beta-tester",
    "features/context7",
    "maintainers/dependency-and-source-policy",
    {
      "type": "ref",
      "id": "documentation",
      "label": "Browse all documentation"
    }
  ],
  "directorySidebar": [
    "documentation",
    {
      "type": "ref",
      "id": "example/overview",
      "label": "Community examples"
    },
    {
      "type": "ref",
      "id": "features/f1tv-access-evidence",
      "label": "Sources and advanced topics"
    }
  ]
};

export default sidebars;
