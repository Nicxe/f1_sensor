import React from 'react';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './styles.module.css';
import FlagDemo from './FlagDemo';
import DownloadIcon from '@site/static/img/home/download.svg';
import PuzzleIcon from '@site/static/img/home/puzzle.svg';
import DesktopIcon from '@site/static/img/home/device-desktop.svg';
import ArrowIcon from '@site/static/img/home/arrow-right.svg';
import ExternalIcon from '@site/static/img/home/arrow-up-right.svg';
import PlayIcon from '@site/static/img/home/player-play.svg';
import FlagIcon from '@site/static/img/home/flag.svg';
import MessageIcon from '@site/static/img/home/message.svg';
import BellIcon from '@site/static/img/home/bell.svg';
import ReplayIcon from '@site/static/img/home/player-track-next.svg';

const paths = [
  {title: 'Follow a live session', href: '/entities/live-data'},
  {title: 'Match my TV delay', href: '/features/live-delay'},
  {title: 'Automate my lights', href: '/blueprints/track-status-light'},
  {title: 'Find a sensor or setting', href: '/reference/overview'},
  {title: 'Build and customize my dashboard', href: '/cards/cards-overview'},
  {title: 'Find help with missing data', href: '/help/faq'},
];
const setupSteps = [
  {title: 'Install', href: '/getting-started/installation', Icon: DownloadIcon},
  {title: 'Add F1 Sensor', href: '/getting-started/add-integration', Icon: PuzzleIcon},
  {title: 'Build your first dashboard', href: '/getting-started/first-dashboard', Icon: DesktopIcon},
];
const blueprints = [
  {title: 'Track Status lights', text: 'Bring the flags into your room', href: '/blueprints/track-status-light', Icon: FlagIcon},
  {title: 'Race Control notifications', text: 'Choose which messages reach you', href: '/blueprints/race-control-notifications', Icon: MessageIcon},
  {title: 'Incident Notifications', text: 'Set up neutral on-track alerts', href: '/blueprints/incident-notifications', Icon: BellIcon},
  {title: 'Replay Sync', text: 'Coordinate your replay controls', href: '/blueprints/replay-sync', Icon: ReplayIcon},
];

export default function Home() {
  const homeAssistantLogoLight = useBaseUrl('/img/home-assistant-wordmark-color-on-light.svg');
  const homeAssistantLogoDark = useBaseUrl('/img/home-assistant-wordmark-color-on-dark.svg');
  const videoThumbnail = useBaseUrl('/img/home/intro-video-maxresdefault.jpg');

  return (
    <div className={`f1-home ${styles.home}`}>
      <div className={styles.platformBrand}>
        <img className={styles.platformLogo} src={homeAssistantLogoLight} alt="Home Assistant" />
        <img className={styles.platformLogoDark} src={homeAssistantLogoDark} alt="Home Assistant" />
        <span>Community integration</span>
      </div>
      <section className={styles.hero} aria-labelledby="your-home-in-sync-with-formula-1">
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>Formula 1 meets Home Assistant</p>
          <h1 id="your-home-in-sync-with-formula-1">Formula 1.<br /><em>In your home.</em></h1>
          <p className={styles.lead}>Live timing, dashboards and automations for Home Assistant.</p>
          <div className={styles.actions}>
            <Link className={styles.primary} to="/getting-started/installation">Get started <ArrowIcon aria-hidden="true" /></Link>
            <Link className={styles.textAction} to="/reference/overview">Explore the reference</Link>
          </div>
          <p className={styles.optional}>Start with public live timing. <Link to="/features/f1tv-auth">F1TV Auth is optional.</Link></p>
        </div>
        <div className={styles.introductionVideo}>
          <a className={styles.videoLink} href="https://www.youtube.com/watch?v=R72LXKdiNxA" aria-label="Watch Meet F1 Sensor: Formula 1 in Home Assistant on YouTube">
            <img src={videoThumbnail} alt="F1 at home: Niklas Vilnersson beside a Formula 1 track map" width="1280" height="720" fetchPriority="high" />
            <span className={styles.videoPlay} aria-hidden="true"><PlayIcon /></span>
          </a>
          <p className={styles.videoCaption}><a href="https://www.youtube.com/watch?v=R72LXKdiNxA">Watch the introduction on YouTube <ExternalIcon aria-hidden="true" /></a></p>
          <a className={styles.channelLink} href="https://www.youtube.com/@niklasvilnersson">More videos by Niklas Vilnersson <ExternalIcon aria-hidden="true" /></a>
        </div>
      </section>

      <nav className={styles.setup} aria-label="Get started in three steps">
        <ol role="list">
          {setupSteps.map(({title, href, Icon}, index) => (
            <li key={href}>
              <Link to={href}><Icon aria-hidden="true" /><span>{index + 1}. {title}</span></Link>
            </li>
          ))}
        </ol>
      </nav>

      <section className={styles.taskSection} aria-labelledby="getting-started">
        <h2 id="getting-started">What would you like to do?</h2>
        <ul className={styles.paths} role="list">
          {paths.map(item => (
            <li key={item.href}>
              <Link to={item.href}><span>{item.title}</span><ArrowIcon aria-hidden="true" /></Link>
            </li>
          ))}
        </ul>
        <p className={styles.smallNote}>Most users should choose the stable release. <Link to="/getting-started/release-channels">Compare release channels</Link> before trying a beta or development build.</p>
      </section>

      <FlagDemo />

      <section className={styles.section} aria-labelledby="features">
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>Before. During. After.</p><h2 id="features">Follow the whole weekend.</h2></div><p>Useful between races.<br />Ready when the lights go out.</p></div>
        <div className={styles.features}>
          <article><span className={styles.featureNumber}>01 / PLAN</span><h3>Know what’s next.</h3><p>Bring the race calendar, session times, standings and circuit weather into a dashboard you can check at a glance.</p><Link to="/entities/static-data">Explore schedules and standings <ArrowIcon aria-hidden="true" /></Link></article>
          <article><span className={styles.featureNumber}>02 / WATCH</span><h3>Keep up with the action.</h3><p>Follow timing, tyres, track status and Race Control. Use Live Delay to match your TV pictures and keep reactions in sync.</p><Link to="/features/live-delay">Sync with your broadcast <ArrowIcon aria-hidden="true" /></Link></article>
          <article><span className={styles.featureNumber}>03 / REVISIT</span><h3>Watch on your time.</h3><p>Use No Spoiler Mode to hold back supported updates, then follow a completed session with Replay when archive data is available.</p><Link to="/features/replay-mode">Explore Replay Mode <ArrowIcon aria-hidden="true" /></Link></article>
        </div>
        <div className={styles.relatedLinks}><span>Go further</span><Link to="/features/track-map">Track Map</Link><Link to="/features/no-spoiler-mode">No Spoiler Mode</Link><Link to="/features/incident-detection">Incident Detection</Link></div>
      </section>

      <section className={styles.automation} aria-labelledby="dashboards-and-automations">
        <div><p className={styles.eyebrow}>More than a screen</p><h2 id="dashboards-and-automations">Let your home join in.</h2><p>Turn track flags into lighting, get session notifications, or build your own ideas with Home Assistant entities, events and device triggers.</p><Link className={styles.textAction} to="/automation">Explore automations <ArrowIcon aria-hidden="true" /></Link></div>
        <div className={styles.blueprints}><h3 id="blueprints">Start with a blueprint</h3>{blueprints.map(({title, text, href, Icon}) => <Link to={href} key={href}><Icon className={styles.blueprintIcon} aria-hidden="true" /><span>{title}<small>{text}</small></span><ArrowIcon className={styles.blueprintArrow} aria-hidden="true" /></Link>)}</div>
      </section>

      <section className={styles.section} aria-labelledby="timing-modes">
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>Understand your data</p><h2 id="timing-modes">The right mode for your moment.</h2></div></div>
        <div className={styles.modes}>
          <div><h3>Public live timing</h3><span className={styles.modeTag}>Start here</span><p>Core live timing, weather, Race Control, tyres and confirmed incident alerts work without F1TV Auth during supported sessions.</p><Link to="/entities/live-data">See live entities</Link></div>
          <div><h3>Optional F1TV Auth</h3><span className={styles.modeTag}>Extra live features</span><p>Add access for features such as live Track Map, Pit Stops, Team Radio and Championship Prediction when the source supplies the data.</p><Link to="/features/f1tv-auth">Understand optional access</Link></div>
          <div><h3>Replay Mode</h3><span className={styles.modeTag}>Completed sessions</span><p>Follow historical sessions from the archive. Available timing, map and other data depend on what that session contains.</p><Link to="/features/replay-mode">Set up a replay</Link></div>
        </div>
        <p className={styles.smallNote}>Developing or testing the integration? <Link to="/help/developer-mode">Developer Mode</Link> uses local replay dumps for reproducible tests. It is a separate workflow from watching a TV replay.</p>
      </section>

      <section className={styles.bottom}>
        <div><p className={styles.eyebrow}>Keep up to date</p><h2 id="version-54">What’s new?</h2><p>Find release notes, update instructions and the difference between stable, beta and development builds.</p><Link to="/getting-started/release-channels">Versions and release channels</Link></div>
        <div><p className={styles.eyebrow}>Built for the community</p><h2 id="support">Enjoying your setup?</h2><p>Share your ideas, ask a question or help support the project’s continued development.</p><div className={styles.supportLinks}><Link to="/support">Support the project</Link><Link href="https://community.home-assistant.io/t/formula-1-racing-sensor/880842">Join the discussion</Link></div></div>
      </section>
      <p className={styles.disclaimer}>F1 Sensor is an independent community project. It is not affiliated with or endorsed by Home Assistant or the Formula 1 companies. F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP, GRAND PRIX and related marks are trade marks of Formula One Licensing B.V.</p>
    </div>
  );
}
