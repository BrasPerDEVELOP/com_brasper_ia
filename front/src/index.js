import { createWidget } from './widget.js';

function getGlobalObject() {
  if (typeof window !== 'undefined') {
    return window;
  }
  if (typeof globalThis !== 'undefined') {
    return globalThis;
  }
  return {};
}

const widgetRegistry = new Map();

export function init(userConfig = {}) {
  const widget = createWidget(userConfig);
  widget.mount();

  if (widget.config.containerId) {
    widgetRegistry.set(widget.config.containerId, widget);
  }

  return widget.publicApi;
}

export function destroy(containerId) {
  const widget = widgetRegistry.get(containerId);
  if (!widget) {
    return false;
  }

  widget.destroy();
  widgetRegistry.delete(containerId);
  return true;
}

const api = {
  init,
  destroy,
};

const globalObject = getGlobalObject();
globalObject.EmbeddingGemmaChat = api;

export default api;
