export const handleF1CardActionKeydown = (host, event) => {
  if (event.target !== event.currentTarget || !['Enter', ' '].includes(event.key)) return;
  event.preventDefault();
  host?._handleCardAction?.();
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
