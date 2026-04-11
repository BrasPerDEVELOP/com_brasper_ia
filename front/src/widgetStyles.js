export const styles = `
/* La fuente del widget es independiente de la página: se define en :host y hereda al árbol del shadow */
:host {
  all: initial;
  font-family: var(
    --eg-font-family,
    "DM Sans",
    ui-sans-serif,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    sans-serif
  );
}

:host *,
:host *::before,
:host *::after {
  box-sizing: border-box;
  font-family: inherit;
}

.eg-chat-shell {
  position: fixed;
  z-index: var(--eg-z-index, 9999);
  bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.eg-chat-shell--bottom-left {
  left: 20px;
}

.eg-chat-shell--bottom-right {
  right: 20px;
}

.eg-chat-launcher {
  width: 76px;
  height: 76px;
  border: 0;
  border-radius: 999px;
  background: linear-gradient(145deg, var(--eg-primary, #0b8a68), #0b624d);
  color: #fff;
  box-shadow: 0 18px 40px rgba(5, 33, 28, 0.35);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: transform 180ms ease, opacity 180ms ease;
  overflow: hidden;
  padding: 0;
}

.eg-chat-launcher:hover {
  transform: translateY(-2px);
}

.eg-chat-launcher svg {
  width: 34px;
  height: 34px;
  fill: currentColor;
}

.eg-chat-launcher-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  pointer-events: none;
}

.eg-chat-launcher--hidden {
  opacity: 0;
  pointer-events: none;
  transform: translateY(6px);
}

/** Botón con GIF/imagen: sin relleno degradado, borde con color primario */
.eg-chat-launcher--media {
  background: var(--eg-launcher-media-bg, transparent);
  border: 3px solid var(--eg-primary, #0b8a68);
  box-shadow: 0 18px 40px rgba(5, 33, 28, 0.28);
}

.eg-chat-panel {
  display: none;
  flex-direction: column;
  overflow: hidden;
  border-radius: 28px;
  background: var(--eg-panel-bg, #f5efe5);
  color: var(--eg-text, #17342c);
  box-shadow: 0 30px 70px rgba(13, 27, 23, 0.28);
  border: 1px solid rgba(7, 32, 26, 0.08);
}

.eg-chat-panel--open {
  display: flex;
}

.eg-chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px;
  /* Por defecto el header sigue a --eg-primary (config.primaryColor). Sobrescribe con headerBackground. */
  background: var(
    --eg-header-bg,
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--eg-primary, #0b8a68) 72%, #000),
      color-mix(in srgb, var(--eg-primary, #0b8a68) 48%, #000)
    )
  );
  color: var(--eg-header-text, #fff);
}

.eg-chat-avatar {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.08);
  display: grid;
  place-items: center;
  flex-shrink: 0;
  overflow: hidden;
}

.eg-chat-avatar svg,
.eg-chat-close svg,
.eg-chat-submit svg {
  width: 20px;
  height: 20px;
  fill: currentColor;
}

.eg-chat-avatar-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.eg-chat-title-wrap {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}

.eg-chat-title {
  font-size: 16px;
}

.eg-chat-subtitle {
  font-size: 12px;
  color: var(--eg-header-subtitle, rgba(255, 255, 255, 0.82));
}

.eg-chat-close {
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.eg-chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 14px;
  background:
    radial-gradient(circle at top right, rgba(169, 222, 191, 0.34), transparent 38%),
    linear-gradient(180deg, #f6f0e5 0%, #efe8dc 100%);
}

.eg-chat-row {
  display: flex;
  margin-bottom: 10px;
}

.eg-chat-row--assistant {
  justify-content: flex-start;
}

.eg-chat-row--user {
  justify-content: flex-end;
}

.eg-chat-bubble {
  max-width: 78%;
  padding: 12px 14px;
  border-radius: 18px;
  line-height: 1.4;
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-word;
}

.eg-chat-bubble > :first-child {
  margin-top: 0;
}

.eg-chat-bubble > :last-child {
  margin-bottom: 0;
}

.eg-chat-bubble--assistant {
  background: #fff;
  color: #21342e;
  border-top-left-radius: 8px;
}

/* Indicador "escribiendo…" (estilo WhatsApp) */
.eg-chat-bubble--typing {
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  min-height: 0;
  box-shadow: 0 1px 0.5px rgba(11, 20, 26, 0.13);
}

.eg-chat-typing {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 10px;
}

.eg-chat-typing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #8696a0;
  animation: eg-chat-typing-bounce 1.35s ease-in-out infinite both;
}

.eg-chat-typing-dot:nth-child(2) {
  animation-delay: 0.22s;
}

.eg-chat-typing-dot:nth-child(3) {
  animation-delay: 0.44s;
}

@keyframes eg-chat-typing-bounce {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.45;
  }
  30% {
    transform: translateY(-5px);
    opacity: 1;
  }
}

.eg-chat-bubble--user {
  background: var(--eg-primary, #0b8a68);
  color: #fff;
  border-top-right-radius: 8px;
}

.eg-chat-paragraph {
  margin: 0 0 8px;
  white-space: pre-wrap;
}

.eg-chat-link-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  margin-top: 6px;
  padding: 10px 14px;
  border: 0;
  border-radius: 12px;
  background: #1fb97a;
  color: #fff;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
}

.eg-chat-link-button:hover {
  background: #169864;
}

.eg-chat-status {
  min-height: 0;
  padding: 0 16px;
  color: #7a3f30;
  font-size: 12px;
  opacity: 0;
  transition: opacity 150ms ease, padding 150ms ease;
}

.eg-chat-status--visible {
  min-height: 18px;
  padding: 8px 16px 0;
  opacity: 1;
}

.eg-chat-form {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  background: #fff;
}

.eg-chat-input {
  flex: 1;
  border: 0;
  border-radius: 16px;
  background: #eff3f1;
  color: #1e2e29;
  padding: 14px 16px;
  font-size: 14px;
  outline: none;
}

.eg-chat-input::placeholder {
  color: #6f7c77;
}

.eg-chat-submit {
  width: 52px;
  height: 52px;
  border: 0;
  border-radius: 18px;
  background: linear-gradient(145deg, var(--eg-primary, #0b8a68), #0a6f57);
  color: #fff;
  display: grid;
  place-items: center;
  cursor: pointer;
}

.eg-chat-submit[disabled],
.eg-chat-input[disabled] {
  opacity: 0.7;
  cursor: not-allowed;
}

@media (max-width: 640px) {
  .eg-chat-shell--bottom-left,
  .eg-chat-shell--bottom-right {
    left: 12px;
    right: 12px;
    bottom: 12px;
  }

  .eg-chat-panel {
    width: auto !important;
    height: min(78vh, 580px) !important;
  }
}
`;
