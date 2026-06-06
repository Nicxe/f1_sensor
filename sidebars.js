/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  tutorialSidebar: [
    {
      type: 'doc',
      label: 'Introduction',
      id: 'introduction',
    },

    {
      type: 'category',
      label: 'Getting Started',
      items: ['getting-started/installation', 'getting-started/add-integration', 'getting-started/release-channels'],
    },
    {
      type: 'category',
      label: 'Features',
      items: [
        'features/live-delay',
        'features/replay-mode',
        'features/no-spoiler-mode',
        'features/f1tv-auth',
        'features/track-map',
        'features/incident-detection',
      ],
    },
    {
      type: 'category',
      label: 'Entities',
      items: ['entities/static-data', 'entities/live-data', 'entities/diagnostics', 'entities/events'],
    },

    {
      type: 'doc',
      label: 'Automation',
      id: 'automation',
    },

    {
      type: 'category',
      label: 'Blueprints',
      items: ['blueprints/track-status-light', 'blueprints/race-control-notifications', 'blueprints/incident-notifications', 'blueprints/replay-sync'],
    },

    {
      type: 'category',
      label: 'Cards',
      items: ['cards/cards-overview'],
    },

    {
      type: 'category',
      label: 'Showcase',
      items: [
        'example/e-ink',
        {
          type: 'category',
          label: 'Community Builds',
          items: ['example/custom-card', 'example/custom-card-by'],
        },
      ],
    },
    {
      type: 'category',
      label: 'Testing and Issues',
      items: ['help/beta-tester', 'help/developer-mode', 'help/debug-logging', 'help/issues'],
    },

    {
      type: 'category',
      label: 'Need Help?',
      items: [
        'help/faq',
        'help/contact',
        'help/f1tv-auth-setup',
        'help/f1tv-token-helper',
        'help/f1tv-token-helper-privacy',
        'features/context7',
      ],
    },

    {
      type: 'doc',
      label: 'Support the project',
      id: 'support',
    },
  ],
};

export default sidebars;
