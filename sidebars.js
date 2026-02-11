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
      items: ['getting-started/installation', 'getting-started/add-integration'],
    },
    {
      type: 'category',
      label: 'Features',
      items: ['features/live-delay', 'features/replay-mode'],
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
      label: 'Examples',
      items: ['example/e-ink', 'example/season-progression-charts', 'example/custom-card', 'example/custom-card-by'],
    },


      {
      type: 'category',
      label: 'Need Help?',
      items: ['help/faq', 'help/Issues', 'help/contact', 'help/beta-tester'],
    },


    {
      type: 'doc',
      label: 'Support the project',
      id: 'support',
    },



  ],
};

export default sidebars;
