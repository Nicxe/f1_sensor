import {themes as prismThemes} from 'prism-react-renderer';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'url';
import path from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Match the documentation to the release lineage, not the npm tooling package.
let version = process.env.F1_DOCS_VERSION;
if (!version) {
  try {
    version = execFileSync('git', ['describe', '--tags', '--abbrev=0', '--match', 'v*'], {
      cwd: __dirname, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'],
    }).trim().replace(/^v/, '');
  } catch {
    version = 'development';
  }
}
// A branch awaiting release stays visibly marked even before its first beta tag.
let branch = process.env.GITHUB_BASE_REF || process.env.GITHUB_REF_NAME;
if (!branch) {
  try {
    branch = execFileSync('git', ['branch', '--show-current'], {
      cwd: __dirname, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    branch = 'unknown';
  }
}
const isPreview = version === 'development' || version.includes('-') || !['main', 'content'].includes(branch);
const editBranch = isPreview ? 'dev' : 'content';

const GITHUB_ORG_NAME = 'Nicxe';
const GITHUB_REPO_NAME = 'f1_sensor';
const GITHUB_REPO_URL = `https://github.com/${GITHUB_ORG_NAME}/${GITHUB_REPO_NAME}`;
const DOCS_FOLDER = 'docs';

const config = {
  title: 'F1 Sensor',
  tagline: 'Home Assistant F1 Sensor Integration',
  favicon: 'img/favicon.ico',

  future: { v4: true },

  url: `https://${GITHUB_ORG_NAME}.github.io`,
  baseUrl: `/${GITHUB_REPO_NAME}/`,
  organizationName: GITHUB_ORG_NAME,
  projectName: GITHUB_REPO_NAME,

  trailingSlash: false,
  onBrokenLinks: 'throw',
  onBrokenAnchors: 'throw',
  markdown: { hooks: { onBrokenMarkdownLinks: 'throw' } },

  i18n: { defaultLocale: 'en', locales: ['en'] },

  presets: [
    [
      'classic',
      ({
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.js',
          editUrl: ({docPath}) =>
            `${GITHUB_REPO_URL}/edit/${editBranch}/${DOCS_FOLDER}/${docPath}`,
        },
        blog: false,
        theme: { customCss: ['./src/css/fonts.css', './src/css/custom.css'] },
      }),
    ],
  ],

  themes: [
    [
      '@easyops-cn/docusaurus-search-local',
      { hashed: true, docsRouteBasePath: '/', indexBlog: false, highlightSearchTermsOnTargetPage: true },
    ],
  ],

  themeConfig: {
    image: 'img/social-card.png',
    announcementBar: isPreview ? {
      id: 'development-documentation',
      content: 'Preview documentation · Includes changes awaiting a stable release. <a href="https://github.com/Nicxe/f1_sensor/releases/latest">View the current stable release</a>.',
      backgroundColor: '#182129', textColor: '#ffffff', isCloseable: true,
    } : undefined,
    navbar: {
      title: 'F1 Sensor',
      logo: { alt: 'F1 Sensor', src: 'img/logo.svg' },
      items: [
        { label: 'Get started', to: '/getting-started/installation', position: 'left' },
        { label: 'Dashboards', to: '/cards/cards-overview', position: 'left' },
        { label: 'Guides', to: '/features/overview', position: 'left' },
        { label: 'Reference', to: '/reference/overview', position: 'left' },
        { label: 'Help', to: '/help/overview', position: 'left' },
        { label: version === 'development' ? 'Preview' : `v${version}`, position: 'right', className: 'navbar-version-chip', href: `${GITHUB_REPO_URL}/releases${version === 'development' ? '' : `/tag/v${version}`}` },
        { type: 'search', position: 'right' },
        { href: `${GITHUB_REPO_URL}`, label: 'GitHub', position: 'right' },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {title: 'Build your setup', items: [
          {label: 'Get started', to: '/getting-started/installation'},
          {label: 'Dashboard cards', to: '/cards/cards-overview'},
          {label: 'Automations', to: '/automation'},
        ]},
        {title: 'Find answers', items: [
          {label: 'Troubleshooting', to: '/help/overview'},
          {label: 'Community', to: '/example/overview'},
          {label: 'Support the project', to: '/support'},
        ]},
        {title: 'Project', items: [
          {label: 'Contribute', href: `${GITHUB_REPO_URL}/blob/dev/CONTRIBUTING.md`},
          {label: 'Security', href: `${GITHUB_REPO_URL}/security/policy`},
          {label: 'Token Helper privacy', to: '/help/f1tv-token-helper-privacy'},
        ]},
      ],
      copyright: `Copyright © ${new Date().getFullYear()} F1 Sensor. Built with Docusaurus.`,
    },
    colorMode: { defaultMode: 'light', disableSwitch: false, respectPrefersColorScheme: true },
    prism: { theme: prismThemes.github, darkTheme: prismThemes.dracula },
  },
};

export default config;