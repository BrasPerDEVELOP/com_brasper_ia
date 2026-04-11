export function createElement(tagName, options = {}) {
  const element = document.createElement(tagName);

  if (options.className) {
    element.className = options.className;
  }

  if (options.text) {
    element.textContent = options.text;
  }

  if (options.type) {
    element.type = options.type;
  }

  if (options.attributes) {
    Object.entries(options.attributes).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        element.setAttribute(key, value);
      }
    });
  }

  return element;
}

export function sanitizeDimension(value) {
  return typeof value === 'number' ? `${value}px` : value;
}

export function toCssColor(value) {
  return typeof value === 'string' && value.trim() ? value : '#0b8a68';
}

/** Gradiente de cabecera alineado con el estilo por defecto del widget (mismo peso que en CSS). */
export function headerGradientFromBaseColor(cssColor) {
  return `linear-gradient(180deg, color-mix(in srgb, ${cssColor} 72%, #000), color-mix(in srgb, ${cssColor} 48%, #000))`;
}

export function createIconMarkup(type) {
  const icons = {
    launcher:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a9 9 0 1 0 6.67 15.05l2.14 2.14a1 1 0 0 0 1.41-1.41l-2.14-2.14A9 9 0 0 0 12 3Zm0 2a7 7 0 1 1-4.95 11.95A7 7 0 0 1 12 5Zm-2.5 4a1 1 0 0 0 0 2H14a1 1 0 0 0 .8-1.6l-2-2.67a1 1 0 0 0-1.6 1.2L12 9H9.5Zm5 4H10a1 1 0 1 0-.8 1.6l2 2.67a1 1 0 0 0 1.6-1.2L12 15h2.5a1 1 0 1 0 0-2Z"/></svg>',
    avatar:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm0 5a3.25 3.25 0 1 1-3.25 3.25A3.25 3.25 0 0 1 12 7Zm0 12.2a7.2 7.2 0 0 1-5.32-2.36 5.9 5.9 0 0 1 10.64 0A7.2 7.2 0 0 1 12 19.2Z"/></svg>',
    close:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.7 5.3 12 10.59l5.3-5.3a1 1 0 1 1 1.4 1.42L13.41 12l5.29 5.3a1 1 0 0 1-1.4 1.4L12 13.41l-5.3 5.29a1 1 0 0 1-1.4-1.4L10.59 12 5.3 6.7a1 1 0 0 1 1.4-1.4Z"/></svg>',
    send:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.4 20.6a1 1 0 0 1-.33-1.05l2.2-6.61a1 1 0 0 0 0-.63l-2.2-6.61a1 1 0 0 1 1.4-1.2l16.8 7.6a1 1 0 0 1 0 1.82l-16.8 7.6a1 1 0 0 1-1.07-.12Zm3.83-7.1-1.46 4.37L17.9 12.4 5.77 6.93l1.46 4.37h5.27a1 1 0 0 1 0 2Z"/></svg>',
  };

  return icons[type] || '';
}
