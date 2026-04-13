import { mergeConfig } from './widgetConfig.js';
import {
  createElement,
  createIconMarkup,
  headerGradientFromBaseColor,
  sanitizeDimension,
  toCssColor,
} from './widgetDom.js';
import { sendSessionMessage, startSession } from './widgetClient.js';
import { styles } from './widgetStyles.js';

export function createWidget(userConfig = {}) {
  const config = mergeConfig(userConfig);
  const sessionStorageKey = `embedding-gemma-chat-session:${config.containerId}`;
  const state = {
    isOpen: false,
    isLoading: false,
    messages: [],
    error: null,
    sessionId: null,
    initialized: false,
    inputMode: 'text',
    options: [],
  };

  let host = null;
  let shadowRoot = null;
  let styleNode = null;
  let launcherButton = null;
  let panel = null;
  let messagesNode = null;
  let formNode = null;
  let inputNode = null;
  let statusNode = null;
  let optionsNode = null;

  function setState(nextState) {
    Object.assign(state, nextState);
    render();
  }

  function emit(callbackName, payload) {
    const callback = config.callbacks?.[callbackName];
    if (typeof callback === 'function') {
      callback(payload);
    }
  }

  function appendMessage(message) {
    state.messages.push(message);
    renderMessages();
  }

  function mount() {
    host = createElement('div', {
      className: 'eg-chat-host',
      attributes: { id: config.containerId },
    });
    document.body.appendChild(host);

    shadowRoot = host.attachShadow({ mode: 'open' });

    if (config.fontImportUrl) {
      const fontLink = createElement('link', {
        attributes: {
          rel: 'stylesheet',
          href: config.fontImportUrl,
        },
      });
      shadowRoot.appendChild(fontLink);
    }

    styleNode = createElement('style');
    styleNode.textContent = styles;
    shadowRoot.appendChild(styleNode);

    const shell = createElement('div', {
      className: `eg-chat-shell eg-chat-shell--${config.position}`,
    });

    launcherButton = createElement('button', {
      className: 'eg-chat-launcher',
      type: 'button',
      text: '',
      attributes: {
        'aria-label': 'Abrir chat',
      },
    });
    if (config.launcherImageUrl) {
      const launcherImg = createElement('img', {
        className: 'eg-chat-launcher-img',
        attributes: {
          src: config.launcherImageUrl,
          alt: '',
          decoding: 'async',
        },
      });
      launcherButton.appendChild(launcherImg);
      launcherButton.classList.add('eg-chat-launcher--media');
    } else {
      launcherButton.innerHTML = config.launcherIcon || createIconMarkup('launcher');
    }
    launcherButton.addEventListener('click', toggleOpen);

    panel = createElement('section', {
      className: 'eg-chat-panel',
      attributes: {
        'aria-hidden': 'true',
      },
    });

    const header = createElement('header', { className: 'eg-chat-header' });
    const titleWrap = createElement('div', { className: 'eg-chat-title-wrap' });
    const avatar = createElement('div', { className: 'eg-chat-avatar' });

    if (config.avatarUrl) {
      const img = createElement('img', {
        className: 'eg-chat-avatar-image',
        attributes: {
          src: config.avatarUrl,
          alt: config.title,
        },
      });
      avatar.appendChild(img);
    } else {
      avatar.innerHTML = createIconMarkup('avatar');
    }

    const title = createElement('strong', {
      className: 'eg-chat-title',
      text: config.title,
    });
    const subtitle = createElement('span', {
      className: 'eg-chat-subtitle',
      text: config.subtitle,
    });
    titleWrap.append(title, subtitle);

    const closeButton = createElement('button', {
      className: 'eg-chat-close',
      type: 'button',
      attributes: {
        'aria-label': 'Cerrar chat',
      },
    });
    closeButton.innerHTML = createIconMarkup('close');
    closeButton.addEventListener('click', close);

    header.append(avatar, titleWrap, closeButton);

    messagesNode = createElement('div', {
      className: 'eg-chat-messages',
      attributes: {
        role: 'log',
        'aria-live': 'polite',
      },
    });

    statusNode = createElement('div', {
      className: 'eg-chat-status',
    });

    formNode = createElement('form', { className: 'eg-chat-form' });
    inputNode = createElement('input', {
      className: 'eg-chat-input',
      attributes: {
        type: 'text',
        placeholder: config.placeholder,
        autocomplete: 'off',
        'aria-label': 'Mensaje',
      },
    });

    const submitButton = createElement('button', {
      className: 'eg-chat-submit',
      type: 'submit',
      attributes: {
        'aria-label': 'Enviar',
      },
    });
    submitButton.innerHTML = createIconMarkup('send');
    formNode.addEventListener('submit', handleSubmit);
    formNode.append(inputNode, submitButton);
    optionsNode = createElement('div', { className: 'eg-chat-options eg-chat-options--hidden' });

    panel.append(header, messagesNode, statusNode, optionsNode, formNode);
    shell.append(launcherButton, panel);
    shadowRoot.appendChild(shell);

    if (config.welcomeMessage) {
      state.messages = [
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          text: config.welcomeMessage,
        },
      ];
    }

    render();
  }

  function render() {
    if (!panel || !launcherButton || !messagesNode || !statusNode || !inputNode) {
      return;
    }

    host.style.setProperty('--eg-z-index', String(config.zIndex));
    host.style.setProperty('--eg-font-family', config.fontFamily);

    panel.style.width = sanitizeDimension(config.width);
    panel.style.height = sanitizeDimension(config.height);
    panel.style.setProperty('--eg-primary', toCssColor(config.primaryColor));
    panel.style.setProperty('--eg-accent', toCssColor(config.accentColor));
    panel.style.setProperty('--eg-text', toCssColor(config.textColor));

    if (config.headerBackground) {
      panel.style.setProperty('--eg-header-bg', config.headerBackground);
    } else if (typeof config.headerColor === 'string' && config.headerColor.trim()) {
      panel.style.setProperty(
        '--eg-header-bg',
        headerGradientFromBaseColor(toCssColor(config.headerColor)),
      );
    } else {
      panel.style.removeProperty('--eg-header-bg');
    }
    if (config.headerTextColor) {
      panel.style.setProperty('--eg-header-text', config.headerTextColor);
    } else {
      panel.style.removeProperty('--eg-header-text');
    }
    if (config.headerSubtitleColor) {
      panel.style.setProperty('--eg-header-subtitle', config.headerSubtitleColor);
    } else {
      panel.style.removeProperty('--eg-header-subtitle');
    }
    if (config.panelBackground) {
      panel.style.setProperty('--eg-panel-bg', config.panelBackground);
    } else {
      panel.style.removeProperty('--eg-panel-bg');
    }

    launcherButton.style.setProperty('--eg-primary', toCssColor(config.primaryColor));
    launcherButton.style.setProperty('--eg-accent', toCssColor(config.accentColor));

    panel.classList.toggle('eg-chat-panel--open', state.isOpen);
    panel.setAttribute('aria-hidden', String(!state.isOpen));
    launcherButton.classList.toggle('eg-chat-launcher--hidden', state.isOpen);

    inputNode.disabled = state.isLoading;
    formNode.querySelector('.eg-chat-submit').disabled = state.isLoading;
    statusNode.textContent = state.error || '';
    statusNode.classList.toggle('eg-chat-status--visible', Boolean(state.error));
    formNode.classList.toggle('eg-chat-form--hidden', state.inputMode !== 'text');
    optionsNode.classList.toggle('eg-chat-options--hidden', state.inputMode !== 'options');

    renderMessages();
    renderOptions();
  }

  function renderMessages() {
    if (!messagesNode) {
      return;
    }

    messagesNode.innerHTML = '';

    state.messages.forEach((message) => {
      const row = createElement('div', {
        className: `eg-chat-row eg-chat-row--${message.role}`,
      });
      const bubble = createElement('div', {
        className: `eg-chat-bubble eg-chat-bubble--${message.role}`,
      });
      renderMessageContent(bubble, message.text);
      row.appendChild(bubble);
      messagesNode.appendChild(row);
    });

    if (state.isLoading) {
      const typingRow = createElement('div', {
        className: 'eg-chat-row eg-chat-row--assistant',
      });
      const typingBubble = createElement('div', {
        className: 'eg-chat-bubble eg-chat-bubble--assistant eg-chat-bubble--typing',
        attributes: {
          'aria-label': 'El asistente está escribiendo',
          role: 'status',
        },
      });
      const typingWrap = createElement('span', { className: 'eg-chat-typing' });
      typingWrap.append(
        createElement('span', { className: 'eg-chat-typing-dot' }),
        createElement('span', { className: 'eg-chat-typing-dot' }),
        createElement('span', { className: 'eg-chat-typing-dot' }),
      );
      typingBubble.appendChild(typingWrap);
      typingRow.appendChild(typingBubble);
      messagesNode.appendChild(typingRow);
    }

    messagesNode.scrollTop = messagesNode.scrollHeight;
  }

  function renderMessageContent(container, text) {
    const content = String(text || '');
    const lines = content.split('\n').filter((line, index, array) => line.trim() || index < array.length - 1);

    lines.forEach((line) => {
      const trimmed = line.trim();
      const urlMatch = trimmed.match(/^https?:\/\/\S+$/);

      if (urlMatch) {
        const targetUrl = trimmed;
        const link = createElement('button', {
          className: 'eg-chat-link-button',
          text: targetUrl.includes('wa.me') ? 'Abrir WhatsApp' : 'Abrir enlace',
          type: 'button',
        });
        link.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          const openedWindow = window.open(targetUrl, '_blank', 'noopener,noreferrer');
          if (!openedWindow) {
            window.location.assign(targetUrl);
          }
        });
        container.appendChild(link);
        return;
      }

      const paragraph = createElement('p', {
        className: 'eg-chat-paragraph',
        text: trimmed || ' ',
      });
      container.appendChild(paragraph);
    });
  }

  function renderOptions() {
    if (!optionsNode) {
      return;
    }
    optionsNode.innerHTML = '';
    if (state.inputMode !== 'options') {
      return;
    }
    state.options.forEach((option) => {
      const button = createElement('button', {
        className: 'eg-chat-option-button',
        text: option.label,
        type: 'button',
      });
      button.disabled = state.isLoading;
      button.addEventListener('click', () => {
        void sendStructuredMessage(option.value, option.label);
      });
      optionsNode.appendChild(button);
    });
  }

  function loadStoredSessionId() {
    try {
      return window.localStorage.getItem(sessionStorageKey);
    } catch (_error) {
      return null;
    }
  }

  function persistSessionId(sessionId) {
    state.sessionId = sessionId;
    try {
      window.localStorage.setItem(sessionStorageKey, sessionId);
    } catch (_error) {
      // ignore storage failures
    }
  }

  function applyStructuredResponse(payload) {
    persistSessionId(payload.session_id);
    setState({
      initialized: true,
      messages: payload.messages || [],
      inputMode: payload.input_mode || 'text',
      options: payload.options || [],
      isLoading: false,
      error: null,
    });
  }

  async function ensureSessionLoaded() {
    if (state.initialized || state.isLoading) {
      return;
    }
    setState({ isLoading: true, error: null });
    try {
      const payload = await startSession(config.apiUrl, state.sessionId || loadStoredSessionId());
      applyStructuredResponse(payload);
    } catch (error) {
      setState({ isLoading: false, error: 'No se pudo iniciar la sesión del chat.' });
      emit('onError', error);
    }
  }

  function open() {
    if (state.isOpen) {
      return;
    }
    setState({ isOpen: true });
    emit('onOpen', { config });
    requestAnimationFrame(() => {
      inputNode?.focus();
    });
    void ensureSessionLoaded();
  }

  function close() {
    if (!state.isOpen) {
      return;
    }
    setState({ isOpen: false });
    emit('onClose', { config });
  }

  function toggleOpen() {
    if (state.isOpen) {
      close();
      return;
    }
    open();
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (state.isLoading || !inputNode) {
      return;
    }

    const text = inputNode.value.trim();
    if (!text) {
      return;
    }

    inputNode.value = '';
    await sendStructuredMessage(text, text);
  }

  async function sendStructuredMessage(value, visibleText) {
    setState({ isLoading: true, error: null });
    try {
      const payload = await sendSessionMessage(
        config.apiUrl,
        state.sessionId || loadStoredSessionId(),
        value,
      );
      applyStructuredResponse(payload);
      emit('onMessageSent', { message: visibleText });
      emit('onMessageReceived', { message: payload.messages?.[payload.messages.length - 1]?.text || '' });
    } catch (error) {
      const fallbackMessage = config.errorMessage;
      appendMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        text: fallbackMessage,
      });
      setState({
        isLoading: false,
        error: 'No se pudo completar la solicitud.',
      });
      emit('onError', error);
    }
  }

  function destroy() {
    host?.remove();
  }

  return {
    config,
    mount,
    destroy,
    publicApi: {
      open,
      close,
      toggle: toggleOpen,
      destroy,
      getState: () => ({ ...state, messages: [...state.messages] }),
    },
  };
}
