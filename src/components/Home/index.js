import React from 'react';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './styles.module.css';
import FlagDemo from './FlagDemo';

const paths = [
  {number: '01', title: 'Get started', text: 'Install the integration and make your first dashboard.', href: '/getting-started/installation'},
  {number: '02', title: 'Choose your cards', text: 'Find the right view for a weekend, session or result.', href: '/cards/cards-overview'},
  {number: '03', title: 'Watch in sync', text: 'Match live updates or a replay to your broadcast.', href: '/features/live-delay'},
  {number: '04', title: 'Automate your home', text: 'Bring flags, session starts and notifications into your home.', href: '/automation'},
  {number: '05', title: 'Find an answer', text: 'Understand missing data, settings and common problems.', href: '/help/faq'},
];

export default function Home() {
  const dashboard = useBaseUrl('/img/placeholder_cards_overview.png');
  return (
    <div className={`f1-home ${styles.home}`}>
      <section className={styles.hero} aria-labelledby="your-home-in-sync-with-formula-1">
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}><span aria-hidden="true" /> Formula 1 meets Home Assistant</p>
          <h1 id="your-home-in-sync-with-formula-1">Your home.<br /><em>On race time.</em></h1>
          <p className={styles.lead}>The race weekend, brought home. Schedules, live timing, dashboard cards and automations that follow the action.</p>
          <div className={styles.actions}>
            <Link className={styles.primary} to="/getting-started/installation">Install F1 Sensor <span aria-hidden="true">↗</span></Link>
            <Link className={styles.secondary} to="/cards/cards-overview">Explore dashboard cards <span aria-hidden="true">→</span></Link>
          </div>
          <p className={styles.optional}>Start with public live timing. <Link to="/features/f1tv-auth">F1TV Auth is optional.</Link></p>
        </div>
        <figure className={styles.heroVisual}>
          <div className={styles.visualHeader}><span>Your personal pit wall</span><span>Dashboard example</span></div>
          <Link to="/cards/cards-overview" aria-label="Explore the dashboard cards shown in this example"><img src={dashboard} width="1720" height="1396" alt="Example F1 Sensor dashboard with session status, driver lap times, tyres, pit stops and championship predictions" fetchPriority="high" /></Link>
          <figcaption>A view for every part of the weekend. Available data depends on the session and your setup.</figcaption>
        </figure>
      </section>

      <FlagDemo />

      <section className={styles.section} aria-labelledby="getting-started">
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>Make it yours</p><h2 id="getting-started">Where do you want to start?</h2></div><p>A simple setup first.<br />More possibilities when you need them.</p></div>
        <div className={styles.paths}>{paths.map(item => <Link className={styles.path} key={item.number} to={item.href}><span className={styles.pathNumber}>{item.number}</span><div><h3>{item.title}<span aria-hidden="true">↗</span></h3><p>{item.text}</p></div></Link>)}</div>
        <p className={styles.smallNote}>Most users should choose the stable release. <Link to="/getting-started/release-channels">Compare release channels</Link> before trying a beta or development build.</p>
      </section>

      <section className={styles.section} aria-labelledby="features">
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>Before. During. After.</p><h2 id="features">Follow the whole weekend.</h2></div><p>Useful between races.<br />Ready when the lights go out.</p></div>
        <div className={styles.features}>
          <article><span className={styles.featureNumber}>01 / PLAN</span><h3>Know what’s next.</h3><p>Bring the race calendar, session times, standings and circuit weather into a dashboard you can check at a glance.</p><Link to="/entities/static-data">Explore schedules and standings <span aria-hidden="true">→</span></Link></article>
          <article><span className={styles.featureNumber}>02 / WATCH</span><h3>Keep up with the action.</h3><p>Follow timing, tyres, track status and Race Control. Use Live Delay to match your TV pictures and keep reactions in sync.</p><Link to="/features/live-delay">Sync with your broadcast <span aria-hidden="true">→</span></Link></article>
          <article><span className={styles.featureNumber}>03 / REVISIT</span><h3>Watch on your time.</h3><p>Use No Spoiler Mode to hold back supported updates, then follow a completed session with Replay when archive data is available.</p><Link to="/features/replay-mode">Explore Replay Mode <span aria-hidden="true">→</span></Link></article>
        </div>
        <div className={styles.relatedLinks}><span>Go further</span><Link to="/features/track-map">Track Map</Link><Link to="/features/no-spoiler-mode">No Spoiler Mode</Link><Link to="/features/incident-detection">Incident Detection</Link></div>
      </section>

      <section className={styles.automation} aria-labelledby="dashboards-and-automations">
        <div><p className={styles.eyebrow}>More than a screen</p><h2 id="dashboards-and-automations">Let your home join in.</h2><p>Turn track flags into lighting, get session notifications, or build your own ideas with Home Assistant entities, events and device triggers.</p><Link className={styles.textAction} to="/automation">Explore automations <span aria-hidden="true">→</span></Link></div>
        <div className={styles.blueprints}><h3 id="blueprints">Start with a blueprint</h3><Link to="/blueprints/track-status-light"><span className={styles.flagIcon} aria-hidden="true">⚑</span><span>Track Status lights<small>Bring the flags into your room</small></span><b aria-hidden="true">↗</b></Link><Link to="/blueprints/race-control-notifications"><span className={styles.messageIcon} aria-hidden="true">≡</span><span>Race Control notifications<small>Choose which messages reach you</small></span><b aria-hidden="true">↗</b></Link><Link to="/blueprints/incident-notifications"><span className={styles.messageIcon} aria-hidden="true">!</span><span>Incident Notifications<small>Set up neutral on-track alerts</small></span><b aria-hidden="true">↗</b></Link><Link to="/blueprints/replay-sync"><span className={styles.messageIcon} aria-hidden="true">▷</span><span>Replay Sync<small>Coordinate your replay controls</small></span><b aria-hidden="true">↗</b></Link></div>
      </section>

      <section className={styles.section} aria-labelledby="timing-modes">
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>Understand your data</p><h2 id="timing-modes">The right mode for your moment.</h2></div></div>
        <div className={styles.modes}>
          <div><h3>Public live timing</h3><span className={styles.modeTag}>Start here</span><p>Core live timing, weather, Race Control, tyres and confirmed incident alerts work without F1TV Auth during supported sessions.</p><Link to="/entities/live-data">See live entities →</Link></div>
          <div><h3>Optional F1TV Auth</h3><span className={styles.modeTag}>Extra live features</span><p>Add access for features such as live Track Map, Pit Stops, Team Radio and Championship Prediction when the source supplies the data.</p><Link to="/features/f1tv-auth">Understand optional access →</Link></div>
          <div><h3>Replay Mode</h3><span className={styles.modeTag}>Completed sessions</span><p>Follow historical sessions from the archive. Available timing, map and other data depend on what that session contains.</p><Link to="/features/replay-mode">Set up a replay →</Link></div>
        </div>
        <p className={styles.smallNote}>Developing or testing the integration? <Link to="/help/developer-mode">Developer Mode</Link> uses local replay dumps for reproducible tests. It is a separate workflow from watching a TV replay.</p>
      </section>

      <section className={styles.bottom}>
        <div><p className={styles.eyebrow}>Keep up to date</p><h2 id="version-54">What’s new?</h2><p>Find release notes, update instructions and the difference between stable, beta and development builds.</p><Link to="/getting-started/release-channels">Versions and release channels →</Link></div>
        <div><p className={styles.eyebrow}>Built for the community</p><h2 id="support">Enjoying your setup?</h2><p>Share your ideas, ask a question or help support the project’s continued development.</p><div className={styles.supportLinks}><Link to="/support">Support the project →</Link><Link href="https://community.home-assistant.io/t/formula-1-racing-sensor/880842">Join the discussion ↗</Link></div></div>
      </section>
      <p className={styles.disclaimer}>F1 Sensor is an unofficial project and is not associated with the Formula 1 companies. F1, FORMULA ONE, FORMULA 1, FIA FORMULA ONE WORLD CHAMPIONSHIP, GRAND PRIX and related marks are trade marks of Formula One Licensing B.V.</p>
    </div>
  );
}
