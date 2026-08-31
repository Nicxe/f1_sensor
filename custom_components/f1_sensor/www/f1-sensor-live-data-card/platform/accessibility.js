import { LitElement } from '../f1-lit-3.3.2.js';
import {
  dispatchF1CardAction,
  handleF1CardActionKeydown,
  hasF1Action,
  isF1InteractiveTarget,
} from './actions.js';
import { f1Translate, f1TranslateText } from './i18n.js';

export const installF1EditorTabAccessibility = (EditorClass) => {
  if (!EditorClass || EditorClass.prototype.__f1TabAccessibilityInstalled) return;
  EditorClass.prototype.__f1TabAccessibilityInstalled = true;
  const originalUpdated = EditorClass.prototype.updated;
  const originalDisconnected = EditorClass.prototype.disconnectedCallback;

  EditorClass.prototype.updated = function (...args) {
    originalUpdated?.apply(this, args);
    if (this.renderRoot && !this.renderRoot.querySelector('style[data-f1-a11y-contrast]')) {
      const contrastStyle = document.createElement('style');
      contrastStyle.dataset.f1A11yContrast = '';
      contrastStyle.textContent = `
        button[role="tab"][aria-selected="true"] {
          color: #ff6b63 !important;
        }
      `;
      this.renderRoot.append(contrastStyle);
    }
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
  const originalCardAction = CardClass.prototype._handleCardAction;
  const originalUpdated = CardClass.prototype.updated;
  const originalDisconnected = CardClass.prototype.disconnectedCallback;

  CardClass.prototype._handleCardAction = function (eventOrAction = 'tap') {
    const actionName = typeof eventOrAction === 'string' ? eventOrAction : 'tap';
    if (actionName === 'tap' && this.__f1SuppressTap) {
      this.__f1SuppressTap = false;
      return;
    }
    if (actionName === 'tap' && hasF1Action(this, 'double_tap')) {
      clearTimeout(this.__f1TapTimer);
      this.__f1TapTimer = setTimeout(() => {
        this.__f1TapTimer = null;
        dispatchF1CardAction(this, 'tap');
      }, 250);
      return;
    }
    if (dispatchF1CardAction(this, actionName)) return;
    if (actionName === 'tap') originalCardAction?.call(this, eventOrAction);
  };

  CardClass.prototype.updated = function (...args) {
    originalUpdated?.apply(this, args);
    if (this.renderRoot && !this.renderRoot.querySelector('style[data-f1-action-a11y]')) {
      const actionStyle = document.createElement('style');
      actionStyle.dataset.f1ActionA11y = '';
      actionStyle.textContent = `
        .f1-card-action-target {
          position: absolute;
          inline-size: 1px;
          block-size: 1px;
          padding: 0;
          margin: -1px;
          overflow: hidden;
          clip-path: inset(50%);
          white-space: nowrap;
          border: 0;
        }
        .f1-card-action-target:focus-visible {
          position: static;
          inline-size: auto;
          block-size: auto;
          margin: 0.5rem;
          padding: 0.5rem 0.75rem;
          overflow: visible;
          clip-path: none;
          white-space: normal;
        }
      `;
      this.renderRoot.append(actionStyle);
    }
    const activeCards = new Set(this.renderRoot?.querySelectorAll('ha-card') || []);
    const activeTargets = new Set();
    for (const card of activeCards) {
      const enabled = hasF1Action(this, 'tap')
        || hasF1Action(this, 'hold')
        || hasF1Action(this, 'double_tap')
        || Boolean(originalCardAction);
      const existingActionButton = card.querySelector('[data-f1-card-action]');
      const hasInteractiveContent = Boolean(card.querySelector(
        'a, button:not([data-f1-card-action]), ha-button, ha-control-button, ha-icon-button, '
        + 'ha-select, ha-switch, input, select, textarea, [role="button"], [role="link"], '
        + '[role="menuitem"], [role="option"], [tabindex]:not([tabindex="-1"])',
      ));
      let target = card;
      if (hasInteractiveContent) {
        card.removeAttribute('role');
        card.removeAttribute('tabindex');
        card.removeAttribute('aria-label');
        target = existingActionButton || document.createElement('button');
        if (!existingActionButton) {
          target.type = 'button';
          target.dataset.f1CardAction = '';
          target.className = 'f1-card-action-target';
          card.append(target);
        }
      } else {
        existingActionButton?.remove();
      }

      if (!enabled) {
        if (target === card) {
          card.removeAttribute('role');
          card.removeAttribute('tabindex');
          card.removeAttribute('aria-label');
        } else {
          target.remove();
        }
        continue;
      }
      const actionLabel = f1Translate(this.hass, 'a11y.open_details', '', {
        title: f1TranslateText(this.hass, this.config?.title || 'Formula 1 card'),
      });
      if (target === card) {
        card.setAttribute('role', 'button');
        card.setAttribute('tabindex', '0');
        card.setAttribute('aria-label', actionLabel);
      } else {
        target.textContent = actionLabel;
        target.setAttribute('aria-label', actionLabel);
      }
      if (!target.__f1ActionKeydown && target === card) {
        target.__f1ActionKeydown = (event) => handleF1CardActionKeydown(this, event);
        target.addEventListener('keydown', target.__f1ActionKeydown);
      }
      if ((!originalCardAction || target !== card) && !target.__f1ActionClick) {
        target.__f1ActionClick = (event) => {
          if (target !== card) event.stopPropagation();
          if (!isF1InteractiveTarget(event)) this._handleCardAction(event);
          else if (target !== card) this._handleCardAction(event);
        };
        target.addEventListener('click', target.__f1ActionClick);
      }
      if (!target.__f1ActionDoubleClick) {
        target.__f1ActionDoubleClick = (event) => {
          if (!hasF1Action(this, 'double_tap') || (target === card && isF1InteractiveTarget(event))) return;
          if (target !== card) event.stopPropagation();
          event.preventDefault();
          clearTimeout(this.__f1TapTimer);
          this.__f1TapTimer = null;
          dispatchF1CardAction(this, 'double_tap');
        };
        target.addEventListener('dblclick', target.__f1ActionDoubleClick);
      }
      if (!target.__f1ActionPointerDown) {
        target.__f1ActionPointerDown = (event) => {
          if (!hasF1Action(this, 'hold') || (target === card && isF1InteractiveTarget(event))) return;
          if (target !== card) event.stopPropagation();
          clearTimeout(this.__f1HoldTimer);
          this.__f1HoldTimer = setTimeout(() => {
            this.__f1HoldTimer = null;
            this.__f1SuppressTap = true;
            dispatchF1CardAction(this, 'hold');
          }, 500);
        };
        target.__f1ActionPointerEnd = () => {
          clearTimeout(this.__f1HoldTimer);
          this.__f1HoldTimer = null;
        };
        target.addEventListener('pointerdown', target.__f1ActionPointerDown);
        target.addEventListener('pointerup', target.__f1ActionPointerEnd);
        target.addEventListener('pointercancel', target.__f1ActionPointerEnd);
        target.addEventListener('pointerleave', target.__f1ActionPointerEnd);
      }
      activeTargets.add(target);
    }
    for (const target of this.__f1ActionTargets || []) {
      if (activeTargets.has(target)) continue;
      target.removeEventListener('keydown', target.__f1ActionKeydown);
      target.removeEventListener('click', target.__f1ActionClick);
      target.removeEventListener('dblclick', target.__f1ActionDoubleClick);
      target.removeEventListener('pointerdown', target.__f1ActionPointerDown);
      target.removeEventListener('pointerup', target.__f1ActionPointerEnd);
      target.removeEventListener('pointercancel', target.__f1ActionPointerEnd);
      target.removeEventListener('pointerleave', target.__f1ActionPointerEnd);
    }
    this.__f1ActionTargets = activeTargets;
  };

  CardClass.prototype.disconnectedCallback = function (...args) {
    clearTimeout(this.__f1TapTimer);
    clearTimeout(this.__f1HoldTimer);
    this.__f1TapTimer = null;
    this.__f1HoldTimer = null;
    for (const target of this.__f1ActionTargets || []) {
      target.removeEventListener('keydown', target.__f1ActionKeydown);
      target.removeEventListener('click', target.__f1ActionClick);
      target.removeEventListener('dblclick', target.__f1ActionDoubleClick);
      target.removeEventListener('pointerdown', target.__f1ActionPointerDown);
      target.removeEventListener('pointerup', target.__f1ActionPointerEnd);
      target.removeEventListener('pointercancel', target.__f1ActionPointerEnd);
      target.removeEventListener('pointerleave', target.__f1ActionPointerEnd);
    }
    this.__f1ActionTargets = null;
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
