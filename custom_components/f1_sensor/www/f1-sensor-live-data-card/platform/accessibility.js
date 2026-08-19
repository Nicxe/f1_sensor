import { LitElement } from '../f1-lit-3.3.2.js';
import { handleF1CardActionKeydown } from './actions.js';
import { f1Translate } from './i18n.js';

export const installF1EditorTabAccessibility = (EditorClass) => {
  if (!EditorClass || EditorClass.prototype.__f1TabAccessibilityInstalled) return;
  EditorClass.prototype.__f1TabAccessibilityInstalled = true;
  const originalUpdated = EditorClass.prototype.updated;
  const originalDisconnected = EditorClass.prototype.disconnectedCallback;

  EditorClass.prototype.updated = function (...args) {
    originalUpdated?.apply(this, args);
    const tabList = this.renderRoot?.querySelector('.tabs');
    if (!tabList) return;
    if (this.__f1TabList !== tabList) {
      this.__f1TabList?.removeEventListener('keydown', this.__f1TabKeydown);
      this.__f1TabKeydown = (event) => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        const tabs = [...tabList.querySelectorAll('button[role="tab"]')];
        const current = tabs.indexOf(event.target);
        if (current < 0 || tabs.length === 0) return;
        event.preventDefault();
        let next = current;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = tabs.length - 1;
        if (event.key === 'ArrowLeft') next = (current - 1 + tabs.length) % tabs.length;
        if (event.key === 'ArrowRight') next = (current + 1) % tabs.length;
        tabs[next].focus();
        tabs[next].click();
      };
      tabList.addEventListener('keydown', this.__f1TabKeydown);
      this.__f1TabList = tabList;
    }
    tabList.setAttribute('role', 'tablist');
    tabList.querySelectorAll('button').forEach((tab) => {
      const selected = tab.classList.contains('active');
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', selected ? 'true' : 'false');
      tab.tabIndex = selected ? 0 : -1;
    });
  };

  EditorClass.prototype.disconnectedCallback = function (...args) {
    this.__f1TabList?.removeEventListener('keydown', this.__f1TabKeydown);
    this.__f1TabList = null;
    if (originalDisconnected) originalDisconnected.apply(this, args);
    else LitElement.prototype.disconnectedCallback.call(this);
  };
};

export const installF1CardActionAccessibility = (CardClass) => {
  if (!CardClass || CardClass.prototype.__f1CardActionAccessibilityInstalled) return;
  CardClass.prototype.__f1CardActionAccessibilityInstalled = true;
  const originalUpdated = CardClass.prototype.updated;
  const originalDisconnected = CardClass.prototype.disconnectedCallback;

  CardClass.prototype.updated = function (...args) {
    originalUpdated?.apply(this, args);
    const activeCards = new Set(this.renderRoot?.querySelectorAll('ha-card') || []);
    for (const card of this.__f1ActionCards || []) {
      if (!activeCards.has(card)) card.removeEventListener('keydown', card.__f1ActionKeydown);
    }
    for (const card of activeCards) {
      const enabled = this.config?.tap_action?.action !== 'none';
      if (!enabled) {
        card.removeEventListener('keydown', card.__f1ActionKeydown);
        card.__f1ActionKeydown = null;
        card.removeAttribute('role');
        card.removeAttribute('tabindex');
        card.removeAttribute('aria-label');
        continue;
      }
      const declarative = card.getAttribute('role') === 'button' && card.hasAttribute('tabindex');
      if (!card.__f1ActionKeydown && !declarative) {
        card.__f1ActionKeydown = (event) => handleF1CardActionKeydown(this, event);
        card.addEventListener('keydown', card.__f1ActionKeydown);
      }
      card.setAttribute('role', 'button');
      card.setAttribute('tabindex', '0');
      card.setAttribute('aria-label', f1Translate(this.hass, 'a11y.open_details', '', {
        title: this.config?.title || 'Formula 1 card',
      }));
    }
    this.__f1ActionCards = activeCards;
  };

  CardClass.prototype.disconnectedCallback = function (...args) {
    for (const card of this.__f1ActionCards || []) {
      card.removeEventListener('keydown', card.__f1ActionKeydown);
    }
    this.__f1ActionCards = null;
    if (originalDisconnected) originalDisconnected.apply(this, args);
    else LitElement.prototype.disconnectedCallback.call(this);
  };
};

export const installF1GridTableAccessibility = (CardClass, prefix, label) => {
  if (!CardClass || CardClass.prototype.__f1GridTableAccessibilityInstalled) return;
  CardClass.prototype.__f1GridTableAccessibilityInstalled = true;
  const originalUpdated = CardClass.prototype.updated;
  CardClass.prototype.updated = function (...args) {
    originalUpdated?.apply(this, args);
    this.renderRoot?.querySelectorAll(`.${prefix}-table`).forEach((table) => {
      table.setAttribute('role', 'table');
      table.setAttribute('aria-label', label);
      table.querySelectorAll(`.${prefix}-row`).forEach((row) => {
        row.setAttribute('role', 'row');
        row.querySelectorAll(`.${prefix}-cell`).forEach((cell) => {
          cell.setAttribute('role', row.classList.contains('header') ? 'columnheader' : 'cell');
        });
      });
    });
  };
};
