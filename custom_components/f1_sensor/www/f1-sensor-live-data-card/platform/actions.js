const ACTION_CONFIG_KEYS = {
  tap: 'tap_action',
  hold: 'hold_action',
  double_tap: 'double_tap_action',
};

const INTERACTIVE_SELECTOR = [
  'a',
  'button',
  'ha-button',
  'ha-control-button',
  'ha-icon-button',
  'ha-select',
  'ha-switch',
  'input',
  'select',
  'textarea',
  '[role="button"]',
  '[role="link"]',
  '[role="menuitem"]',
  '[role="option"]',
  '[role="slider"]',
  '[role="switch"]',
  '[role="tab"]',
].join(',');

export const isF1InteractiveTarget = (event) => {
  const target = event?.composedPath?.()[0] || event?.target;
  return target !== event?.currentTarget && Boolean(target?.closest?.(INTERACTIVE_SELECTOR));
};

export const resolveF1ActionEntity = (host) => {
  const config = host?.config || {};
  return config.entity
    || config.current_entity
    || config.session_entity
    || config.positions_entity
    || config.drivers_entity
    || config.weather_entity
    || config.calendar_entity
    || config.results_entity
    || null;
};

export const normalizeF1Action = (action = {}) => {
  if (action?.action !== 'call-service') return action;
  return {
    ...action,
    action: 'perform-action',
    perform_action: action.perform_action || action.service,
    data: action.data || action.service_data,
  };
};

export const getF1Action = (host, actionName) => {
  const key = ACTION_CONFIG_KEYS[actionName];
  if (!key) return { action: 'none' };
  const configured = host?.config?.[key];
  if (configured) return normalizeF1Action(configured);
  if (actionName !== 'tap') return { action: 'none' };
  return resolveF1ActionEntity(host) ? { action: 'more-info' } : { action: 'none' };
};

export const hasF1Action = (host, actionName) => getF1Action(host, actionName).action !== 'none';

export const dispatchF1CardAction = (host, actionName = 'tap') => {
  const action = getF1Action(host, actionName);
  if (!host || action.action === 'none') return false;
  const configKey = ACTION_CONFIG_KEYS[actionName];
  const entity = resolveF1ActionEntity(host);
  host.dispatchEvent(new CustomEvent('hass-action', {
    bubbles: true,
    composed: true,
    detail: {
      action: actionName,
      config: {
        ...(host.config || {}),
        ...(entity ? { entity } : {}),
        [configKey]: action,
      },
    },
  }));
  return true;
};

export const handleF1CardActionKeydown = (host, event) => {
  if (event.target !== event.currentTarget || !['Enter', ' '].includes(event.key)) return;
  event.preventDefault();
  host?._handleCardAction?.('tap');
};
