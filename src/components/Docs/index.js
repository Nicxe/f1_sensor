import React, {useId, useState} from 'react';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import {entityCatalog, getEntityReference} from '@site/src/data/docsCatalog';
import styles from './styles.module.css';

export function NativeDetails({summary, children}) {
  return <details className={styles.nativeDetails}><summary>{summary}</summary>{children}</details>;
}

export function EntityMeta({id}) {
  const entry = getEntityReference(id);
  if (!entry) return null;
  return (
    <div className={styles.entityMeta}>
      <p><strong>Standard {entry.entityIds.length === 1 ? 'entity ID' : 'entity IDs'}</strong>{' '}{entry.entityIds.map(entityId => <code key={entityId}>{entityId}</code>)}</p>
      <p><Link to={entry.scope === 'live' ? '/entities/live-data#availability-model' : '/entities/static-data'}>{entry.availability}</Link><span aria-hidden="true"> · </span><Link to="/reference/overview#entity-ids">Your IDs may differ</Link></p>
    </div>
  );
}

export function RelatedReferences({id}) {
  const entry = getEntityReference(id);
  if (!entry?.related?.length) return null;
  return <ul className={styles.relatedReferences}>{entry.related.map(link => <li key={link.href}><Link to={link.href}>{link.label}</Link></li>)}</ul>;
}

export function EntityCatalog({scope, children}) {
  const id = useId();
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All topics');
  const [availability, setAvailability] = useState('All data sources');
  const topicOrder = ['Schedule and weather', 'Session and track', 'Drivers and timing', 'Results and championship', 'Officials and incidents'];
  const entries = entityCatalog.filter(entry => !scope || entry.scope === scope).sort((first, second) => (
    topicOrder.indexOf(first.category) - topicOrder.indexOf(second.category)
    || first.title.localeCompare(second.title, 'en')
  ));
  // Literal MDX anchors stay discoverable by Docusaurus; place them at their matching result.
  const anchorIds = React.Children.toArray(children).filter(React.isValidElement).map(child => child.props.id).filter(Boolean);
  const slug = value => value.toLowerCase().replace(/[^a-z0-9 _-]/g, '').replace(/ /g, '-');
  const anchorsFor = entry => anchorIds.filter(anchor => anchor === entry.id
    || (entry.id === 'starting-grid' && ['grid-context-and-source', 'weekend-flow'].includes(anchor))
    || (anchor === slug(entry.category) && entries.find(item => item.category === entry.category)?.id === entry.id));
  const categories = [...new Set(entries.map(entry => entry.category))];
  const sources = [...new Set(entries.map(entry => entry.availability))];
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const visible = entries.filter(entry => (
    (category === 'All topics' || entry.category === category)
    && (availability === 'All data sources' || entry.availability === availability)
    && terms.every(term => [entry.title, entry.description, entry.category, entry.availability, entry.keywords, ...entry.entityIds].join(' ').toLowerCase().includes(term))
  ));
  const filtered = query || category !== 'All topics' || availability !== 'All data sources';
  return (
    <section className={styles.entityCatalogue} aria-label="Entity reference catalogue">
      <div className={styles.catalogControls}>
        <div className={styles.catalogSearch}><label htmlFor={`${id}-search`}>Find an entity or attribute</label><input id={`${id}-search`} type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Try yellow, weather, f1_pitstops…" /></div>
        <div><label htmlFor={`${id}-topic`}>Topic</label><select id={`${id}-topic`} value={category} onChange={event => setCategory(event.target.value)}><option>All topics</option>{categories.map(item => <option key={item}>{item}</option>)}</select></div>
        <div><label htmlFor={`${id}-source`}>Data source</label><select id={`${id}-source`} value={availability} onChange={event => setAvailability(event.target.value)}><option>All data sources</option>{sources.map(item => <option key={item}>{item}</option>)}</select></div>
      </div>
      <div className={styles.catalogSummary}><p className={styles.count} role="status">{visible.length} of {entries.length} entity references</p>{filtered && <button type="button" onClick={() => {setQuery(''); setCategory('All topics'); setAvailability('All data sources');}}>Clear filters</button>}</div>
      {visible.length === 0 ? <p>No matching entities. Try a shorter term or clear the filters. For event payloads and playback helpers, use the reference links above.</p> : <ul className={styles.entityList}>{visible.map(entry => <li key={entry.id}><article>{anchorsFor(entry).map(anchor => <Link key={anchor} id={anchor} aria-hidden="true" className={styles.catalogAnchor} />)}<div className={styles.entityCardHeader}><span className={styles.eyebrow}>{entry.category}</span><span className={styles.sourceLabel}>{entry.availability}</span></div><h3><Link to={entry.href}>{entry.title}</Link></h3><p>{entry.description}</p><div className={styles.entityIds}>{entry.entityIds.map(entityId => <code key={entityId}>{entityId}</code>)}</div></article></li>)}</ul>}
      <p className={styles.catalogNote}>Data-source labels are a starting point. Each reference keeps its exact session requirements, unavailable states and exceptions.</p>
    </section>
  );
}

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

function GalleryCard({card, compact = false}) {
  const imageUrl = useBaseUrl(card.image || '/img/logo.svg');
  const labels = Array.isArray(card.availability) ? card.availability : [card.availability].filter(Boolean);
  // Native fragment navigation reveals a target inside closed <details>.
  const target = card.nativeAnchor ? `pathname://${card.href || card.to}` : card.href || card.to;
  const targetProps = card.nativeAnchor ? {target: '_self'} : {};
  return (
    <article className={`${styles.galleryCard} ${compact ? styles.compactGalleryCard : ''}`}>
      {!compact && <Link to={target} {...targetProps} className={styles.preview} tabIndex={-1} aria-hidden="true">
        {card.image ? <img src={imageUrl} alt="" loading="lazy" decoding="async" /> : <span className={styles.previewLabel}>{card.title}<span>View setup and configuration</span></span>}
      </Link>}
      <div className={styles.galleryBody}>
        <span className={styles.eyebrow}>{card.category}</span>
        <h3><Link to={target} {...targetProps}>{card.title}<span aria-hidden="true"> ↗</span></Link></h3>
        <p>{card.description}</p>
        {labels.length > 0 && <ul className={styles.badges} aria-label={compact ? 'Source notes' : 'Data availability'}>{labels.map(label => <li key={label}>{label}</li>)}</ul>}
      </div>
    </article>
  );
}

export function CardGallery({cards, compact = false, itemLabel = 'card', regionLabel = 'Dashboard card catalogue', searchLabel = 'Find a card'}) {
  const id = useId();
  const allLabel = `All ${itemLabel}s`;
  const [category, setCategory] = useState(allLabel);
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState(false);
  const categories = [allLabel, ...new Set(cards.map(card => card.category).filter(Boolean))];
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const visible = cards.filter(card => (category === allLabel || card.category === category)
    && terms.every(term => [card.id, card.title, card.description, card.keywords, ...(card.sources || [])].join(' ').toLowerCase().includes(term)));
  const filtered = query || category !== allLabel;
  const results = visible.length ? <div className={styles.gallery}>{visible.map(card => <GalleryCard key={card.id || card.href || card.to} card={card} compact={compact} />)}</div>
    : <p>No matching {itemLabel}s. Try a shorter term or clear the filters.</p>;
  return (
    <section className={styles.catalogue} aria-label={regionLabel}>
      {compact && <noscript><p>Search and topic filters need JavaScript. Expand the module list below to browse every guide.</p></noscript>}
      {compact ? <div className={styles.cardFinderControls}>
        <div><label htmlFor={`${id}-search`}>{searchLabel}</label><input id={`${id}-search`} type="search" value={query} onChange={event => {setQuery(event.target.value); setExpanded(true);}} placeholder="Try minisectors, radio, strategy…" /></div>
        <div><label htmlFor={`${id}-topic`}>Module topic</label><select id={`${id}-topic`} value={category} onChange={event => {setCategory(event.target.value); setExpanded(true);}}>{categories.map(item => <option key={item}>{item}</option>)}</select></div>
      </div> : categories.length > 2 && <div className={styles.filters} role="group" aria-label="Filter dashboard cards">{categories.map(item => <button key={item} type="button" aria-pressed={category === item} onClick={() => setCategory(item)}>{item}</button>)}</div>}
      <div className={styles.catalogSummary}><p className={styles.count} role="status">{visible.length} of {cards.length} {itemLabel}s{category !== allLabel && ` · ${category}`}</p>{filtered && <button type="button" onClick={() => {setQuery(''); setCategory(allLabel); setExpanded(true);}}>Clear filters</button>}</div>
      {compact ? <details className={styles.moduleResults} open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}><summary>Browse {visible.length} {visible.length === 1 ? itemLabel : `${itemLabel}s`}</summary>{results}</details> : results}
    </section>
  );
}

export function DelayDemo({id = 'live-delay-example'}) {
  const [delay, setDelay] = useState(30);
  return (
    <section className={styles.delay} aria-labelledby={`${id}-title`}>
      <span id="_R_5a7dalbah_" aria-hidden="true" />
      <span id="_R_5a7dalbah_-title" aria-hidden="true" />
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
