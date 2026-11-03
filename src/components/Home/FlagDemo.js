import React, {useId, useRef, useState} from 'react';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './styles.module.css';
import PlayIcon from '@site/static/img/home/player-play.svg';
import PauseIcon from '@site/static/img/home/player-pause.svg';
import ArrowIcon from '@site/static/img/home/arrow-right.svg';

// Original user-provided demo: https://github.com/user-attachments/assets/18a74679-76e2-4d10-8a0d-d3f111c42593
export default function FlagDemo() {
  const videoUrl = useBaseUrl('/img/home/flag-light-demo.mp4');
  const posterUrl = useBaseUrl('/img/home/flag-light-demo-poster.jpg');
  const original = useBaseUrl('/img/flag-light-demo.gif');
  const video = useRef(null);
  const videoId = useId();
  const [playing, setPlaying] = useState(false);
  const [playbackError, setPlaybackError] = useState(false);

  async function togglePlayback() {
    if (!video.current) return;
    if (!video.current.paused) {
      video.current.pause();
      return;
    }
    setPlaybackError(false);
    try {
      await video.current.play();
    } catch {
      setPlaybackError(true);
    }
  }

  return (
    <section className={styles.flagDemo} aria-labelledby="flags-at-home">
      <div>
        <p className={styles.eyebrow}>From the track to your room</p>
        <h2 id="flags-at-home">Yellow flag.<br />Yellow light.</h2>
        <p>When the flags change, your room follows. Turn track status into lighting with Home Assistant, and use Live Delay to match the moment on your TV.</p>
        <Link className={styles.textAction} to="/blueprints/track-status-light">Set up flag lighting <ArrowIcon aria-hidden="true" /></Link>
      </div>
      <figure className={styles.flagDemoMedia}>
        <video ref={video} id={videoId} poster={posterUrl} preload="none" controls muted playsInline width="480" height="270" aria-label="Flag lighting demonstration" aria-describedby="flag-demo-caption" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onError={() => setPlaybackError(true)}>
          <source src={videoUrl} type="video/mp4" />
          <img src={posterUrl} alt="Yellow flag on TV with a lamp glowing yellow" width="480" height="270" />
        </video>
        <div className={styles.demoControls}>
          <button type="button" onClick={togglePlayback} aria-controls={videoId}>{playing ? <PauseIcon aria-hidden="true" /> : <PlayIcon aria-hidden="true" />}{playing ? 'Pause demonstration' : 'Play demonstration'}</button>
          <span>3 seconds · no sound</span>
        </div>
        <figcaption id="flag-demo-caption">A yellow flag on TV, a yellow light at home. The demonstration starts only when you play it.</figcaption>
        {playbackError && <p role="status">Playback is unavailable. <a href={original}>Open the original animated demonstration</a>.</p>}
      </figure>
    </section>
  );
}
