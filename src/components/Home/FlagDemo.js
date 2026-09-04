import React from 'react';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './styles.module.css';

// Original user-provided demo: https://github.com/user-attachments/assets/18a74679-76e2-4d10-8a0d-d3f111c42593
export default function FlagDemo() {
  const original = useBaseUrl('/img/flag-light-demo.gif');

  return (
    <section className={styles.flagDemo} aria-labelledby="flags-at-home">
      <div>
        <p className={styles.eyebrow}>From the track to your room</p>
        <h2 id="flags-at-home">Yellow flag.<br />Yellow light.</h2>
        <p>When the flags change, your room follows. Turn track status into lighting with Home Assistant, and use Live Delay to match the moment on your TV.</p>
        <Link className={styles.primary} to="/blueprints/track-status-light">Set up flag lighting <span aria-hidden="true">→</span></Link>
      </div>
      <figure className={styles.flagDemoMedia}>
        <img src={original} alt="Yellow flag on TV with a lamp glowing yellow" aria-describedby="flag-demo-caption" width="480" height="270" />
        <figcaption id="flag-demo-caption">A yellow flag on TV, a yellow light at home.</figcaption>
      </figure>
    </section>
  );
}
