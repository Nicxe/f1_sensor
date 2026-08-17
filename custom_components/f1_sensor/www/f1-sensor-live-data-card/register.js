import { F1_CARD_TAGS, registerF1CardMetadata } from './platform/card-registry.js';

registerF1CardMetadata();

let loadPromise = null;
const loadCards = () => {
  loadPromise ||= import('./f1-sensor-live-data-card.js');
  return loadPromise;
};

const containsF1Card = (root) => {
  if (!root?.querySelectorAll) return false;
  for (const element of root.querySelectorAll('*')) {
    if (F1_CARD_TAGS.has(element.localName)) return true;
    if (element.shadowRoot && containsF1Card(element.shadowRoot)) return true;
  }
  return false;
};

const loadIfNeeded = () => {
  if (containsF1Card(document)) loadCards();
};

const observer = new MutationObserver(loadIfNeeded);
observer.observe(document.documentElement, { childList: true, subtree: true });
window.addEventListener('location-changed', loadIfNeeded);
window.addEventListener('ll-rebuild', loadIfNeeded);

let attempts = 0;
const poll = window.setInterval(() => {
  attempts += 1;
  loadIfNeeded();
  if (loadPromise || attempts >= 120) window.clearInterval(poll);
}, 100);

loadIfNeeded();
