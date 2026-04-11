const instanceCounter = {
  value: 0,
};

export function mergeConfig(userConfig = {}) {
  instanceCounter.value += 1;

  return {
    apiUrl:
      userConfig.apiUrl ||
      import.meta.env.VITE_CHAT_API_URL ||
      'http://localhost:8001/consulta-webchat',
    position: userConfig.position === 'bottom-right' ? 'bottom-right' : 'bottom-left',
    title: userConfig.title || 'Asistente de remesas',
    subtitle: userConfig.subtitle || 'Cotización y requisitos en una conversación',
    welcomeMessage: userConfig.welcomeMessage || 'Hola, ¿en qué puedo ayudarte?',
    primaryColor: userConfig.primaryColor || '#0b8a68',
    accentColor: userConfig.accentColor || '#e3fff4',
    textColor: userConfig.textColor || '#17342c',
    /** Tipografía solo del widget (no hereda la de la página). */
    fontFamily:
      userConfig.fontFamily ||
      '"DM Sans", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    /** URL del CSS de Google Fonts u otro host (se inyecta dentro del Shadow DOM). Ej: https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600&display=swap */
    fontImportUrl: userConfig.fontImportUrl || '',
    /** GIF, PNG o WebP para el botón flotante (sustituye el icono SVG por defecto). */
    launcherImageUrl: userConfig.launcherImageUrl || '',
    /** Fondo del header del panel: color sólido o gradiente CSS. Tiene prioridad sobre headerColor. */
    headerBackground: userConfig.headerBackground || '',
    /** Color base del header (gradiente oscuro). Si está vacío, el header sigue a primaryColor. */
    headerColor: userConfig.headerColor || '',
    headerTextColor: userConfig.headerTextColor || '',
    headerSubtitleColor: userConfig.headerSubtitleColor || '',
    /** Fondo del panel del chat (color o gradiente). Vacío = tema por defecto. */
    panelBackground: userConfig.panelBackground || '',
    zIndex: Number(userConfig.zIndex || 9999),
    width: userConfig.width || 360,
    height: userConfig.height || 560,
    placeholder: userConfig.placeholder || 'Escribe tu consulta...',
    avatarUrl: userConfig.avatarUrl || '',
    launcherIcon: userConfig.launcherIcon || '',
    containerId: userConfig.containerId || `embedding-gemma-chat-${instanceCounter.value}`,
    errorMessage:
      userConfig.errorMessage ||
      'No pude conectarme con el servicio. Verifica que el backend esté disponible.',
    callbacks: {
      onOpen: userConfig.onOpen,
      onClose: userConfig.onClose,
      onMessageSent: userConfig.onMessageSent,
      onMessageReceived: userConfig.onMessageReceived,
      onError: userConfig.onError,
    },
  };
}
