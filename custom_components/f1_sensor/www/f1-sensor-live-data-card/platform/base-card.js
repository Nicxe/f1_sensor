const cacheKey = new URL(import.meta.url).searchParams.get('v');
const cacheSuffix = cacheKey ? `?v=${encodeURIComponent(cacheKey)}` : '';
const { LitElement } = await import(`../f1-lit-3.3.2.js${cacheSuffix}`);

export class F1BaseElement extends LitElement {
  disconnectedCallback() {
    super.disconnectedCallback();
  }
}
