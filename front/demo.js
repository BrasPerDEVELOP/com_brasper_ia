import './src/demo.css';
import { init } from './src/index.js';

init({
  title: 'Asistente de remesas',
  subtitle: 'Cotización y requisitos en una conversación',
  welcomeMessage: 'Hola, soy tu asistente de remesas. Puedo ayudarte con cotización, requisitos y datos básicos de tu operación.',
  primaryColor: '#0b8a68',
  accentColor: '#dff7ec',
  textColor: '#16332a',
  position: 'bottom-left',
  width: 380,
  height: 580,
  placeholder: 'Escribe tu consulta...',
  /** Tipografía propia del widget (no usa la de la página) */
  fontFamily: '"DM Sans", ui-sans-serif, system-ui, sans-serif',
  /** Carga DM Sans dentro del Shadow DOM (Google Fonts) */
  fontImportUrl:
    'https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,600;1,9..40,400&display=swap',
  /** GIF o imagen en el botón flotante (también puedes usar avatarUrl para el header) */
  launcherImageUrl: 'https://media.giphy.com/media/3o7abKhOhc0F9HpMQM/giphy.gif',
  /** Opcional: cabecera y panel */
  // headerColor: '#2563eb', // solo cabecera; o cambia primaryColor para todo el tema
  // headerBackground: 'linear-gradient(180deg, #1a1a2e, #16213e)',
  // headerTextColor: '#ffffff',
  // headerSubtitleColor: 'rgba(255,255,255,0.75)',
  // panelBackground: '#f0f4f8',
});
