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
      label: 'Entities',
      items: ['entities/static-data', 'entities/live-data', 'entities/events'],
    },


    {
      type: 'category',
      label: 'Examples',
      items: ['example/e-ink', 'example/season-progression-charts', 'example/custom-card'],
    },


      {
      type: 'category',
      label: 'Need Help?',
      items: ['help/faq', 'help/contact'],
    },



    {
      type: 'doc',
      label: 'Support the project',
      id: 'support',
    },
  ],
};

export default sidebars;