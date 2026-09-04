import React, {useId, useState} from 'react';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './styles.module.css';

export function Figure({src, alt, caption, enlarge = true}) {
  const imageUrl = useBaseUrl(src);
  const picture = <img src={imageUrl} alt={alt} loading="lazy" decoding="async" />;
  return (
    <figure className={styles.figure}>
      {enlarge ? <a href={imageUrl} target="_blank" rel="noreferrer" aria-label={`Open full-size image: ${alt} (new tab)`}>{picture}</a> : picture}
      {(caption || enlarge) && <figcaption>{caption}{enlarge && <span className={styles.imageHint}>Select the image to open it full size.</span>}</figcaption>}
    </figure>
  );
}

function GalleryCard({card}) {
  const imageUrl = useBaseUrl(card.image || '/img/logo.svg');
  const labels = Array.isArray(card.availability) ? card.availability : [card.availability].filter(Boolean);
  return (
    <article className={styles.galleryCard}>
      <Link to={card.href || card.to} className={styles.preview} tabIndex={-1} aria-hidden="true">
        {card.image ? <img src={imageUrl} alt="" loading="lazy" decoding="async" /> : <span className={styles.previewLabel}>{card.title}<span>View setup and configuration</span></span>}
      </Link>
      <div className={styles.galleryBody}>
        <span className={styles.eyebrow}>{card.category}</span>
        <h3><Link to={card.href || card.to}>{card.title}<span aria-hidden="true"> ↗</span></Link></h3>
        <p>{card.description}</p>
        {labels.length > 0 && <ul className={styles.badges} aria-label="Data availability">{labels.map(label => <li key={label}>{label}</li>)}</ul>}
      </div>
    </article>
  );
}

export function CardGallery({cards}) {
  const [category, setCategory] = useState('All cards');
  const categories = ['All cards', ...new Set(cards.map(card => card.category).filter(Boolean))];
  const visible = category === 'All cards' ? cards : cards.filter(card => card.category === category);
  return (
    <div className={styles.catalogue}>
      {categories.length > 2 && <div className={styles.filters} role="group" aria-label="Filter dashboard cards">{categories.map(item => <button key={item} type="button" aria-pressed={category === item} onClick={() => setCategory(item)}>{item}</button>)}</div>}
      <p className={styles.count} role="status">{visible.length} {visible.length === 1 ? 'card' : 'cards'}{category !== 'All cards' && ` · ${category}`}</p>
      <div className={styles.gallery}>{visible.map(card => <GalleryCard key={card.href || card.to} card={card} />)}</div>
    </div>
  );
}

export function DelayDemo() {
  const id = useId();
  const [delay, setDelay] = useState(30);
  return (
    <section className={styles.delay} aria-labelledby={`${id}-title`}>
      <div className={styles.eyebrow}>Try an example</div>
      <h3 id={`${id}-title`}>Same moment. Same reaction.</h3>
      <p>A flag changes at the circuit. Your broadcast shows it later. Live Delay holds the Home Assistant update for the number of seconds you choose.</p>
      <label className={styles.sliderLabel} htmlFor={id}>Example broadcast delay <output htmlFor={id}>{delay} seconds</output></label>
      <input id={id} className={styles.slider} type="range" min="0" max="90" step="5" value={delay} onChange={event => setDelay(Number(event.target.value))} />
      <div className={styles.timeline} aria-hidden="true">
        <div className={styles.timelineRow}><span>At the circuit</span><div className={styles.track}><i className={styles.event} style={{left: '0%'}} /></div><b>0 s</b></div>
        <div className={styles.timelineRow}><span>On your TV</span><div className={styles.track}><i className={styles.event} style={{left: `${delay}%`}} /></div><b>+{delay} s</b></div>
        <div className={styles.timelineRow}><span>In your home</span><div className={styles.track}><i className={styles.homeEvent} style={{left: `${delay}%`}} /></div><b>+{delay} s</b></div>
      </div>
      <p className={styles.delayResult} role="status">With a {delay}-second delay, the TV picture and Home Assistant update both arrive {delay === 0 ? 'at the circuit event time' : `${delay} seconds after the circuit event`}.</p>
      <p className={styles.note}>Illustration only. This does not measure your broadcast or change Home Assistant. Replay uses its own playback controls.</p>
    </section>
  );
}

export function FlowSteps({steps, label = 'Steps at a glance'}) {
  return (
    <ol className={styles.flowSteps} aria-label={label}>
      {steps.map((step, index) => <li key={step.title}><span className={styles.stepNumber} aria-hidden="true">{String(index + 1).padStart(2, '0')}</span><div><strong>{step.title}</strong><p>{step.description}</p></div></li>)}
    </ol>
  );
}

const blueprintFlags = [
  {code: 'CLEAR', title: 'Track clear', description: 'Normal racing conditions', color: 'green'},
  {code: 'YELLOW', title: 'Yellow flag', description: 'Caution or a hazard on track', color: 'yellow'},
  {code: 'RED', title: 'Red flag', description: 'Session stopped', color: 'red'},
  {code: 'VSC', title: 'Virtual Safety Car', description: 'Virtual Safety Car deployed', color: 'yellow'},
  {code: 'SC', title: 'Safety Car', description: 'Safety Car deployed', color: 'red'},
];

export function FlagLegend() {
  return (
    <figure className={styles.flagLegend}>
      <figcaption>Track status → default blueprint light color</figcaption>
      <dl>{blueprintFlags.map(flag => <div key={flag.code}><dt><span className={`${styles.flagSwatch} ${styles[flag.color]}`}>{flag.code}</span><strong>{flag.title}</strong></dt><dd>{flag.description}<small>Default light: {flag.color}</small></dd></div>)}</dl>
      <p>These are the blueprint’s default light colors. You can change them and choose steady light, timed flashing or restoration behavior in the automation settings.</p>
    </figure>
  );
}
