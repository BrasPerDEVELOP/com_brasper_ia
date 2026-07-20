import React from "react";

const PATHS: Record<string, string> = {
  gauge: '<path d="M12 14a2 2 0 0 0 2-2c0-1-2-5-2-5s-2 4-2 5a2 2 0 0 0 2 2z"/><path d="M5 18a8 8 0 1 1 14 0"/>',
  building: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 6h2M13 6h2M9 10h2M13 10h2M9 14h2M13 14h2M10 22v-3h4v3"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13l3.5 7v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  creditcard: '<rect x="2" y="5" width="20" height="14" rx="2.5"/><path d="M2 10h20M6 15h4"/>',
  puzzle: '<path d="M19.4 13c.6 0 1.1-.5 1.1-1.1V8.5A1.5 1.5 0 0 0 19 7h-2.5V5.6a2.1 2.1 0 1 0-4.2 0V7H9a1.5 1.5 0 0 0-1.5 1.5V10h-1.4a2.1 2.1 0 1 0 0 4.2H7.5V17A1.5 1.5 0 0 0 9 18.5h2.5v-1.4a2.1 2.1 0 1 1 4.2 0v1.4H19a1.5 1.5 0 0 0 1.5-1.5v-2.5"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  dollar: '<path d="M12 2v20M17 6.5C17 4.5 14.8 3.5 12 3.5S7 4.7 7 7s2.2 3 5 3.5 5 1.3 5 3.5-2.2 3.5-5 3.5-5-1-5-3"/>',
  chart: '<path d="M3 3v18h18"/><rect x="7" y="11" width="3" height="6" rx="1"/><rect x="12" y="7" width="3" height="10" rx="1"/><rect x="17" y="13" width="3" height="4" rx="1"/>',
  ai: '<path d="M12 3v3M12 18v3M5 7l2 2M17 15l2 2M3 12h3M18 12h3M7 17l-2 2M19 7l-2 2"/><circle cx="12" cy="12" r="4"/>',
  headset: '<path d="M3 14v-2a9 9 0 0 1 18 0v2"/><path d="M21 16a2 2 0 0 1-2 2h-1v-6h1a2 2 0 0 1 2 2zM3 16a2 2 0 0 0 2 2h1v-6H5a2 2 0 0 0-2 2z"/><path d="M19 18a4 4 0 0 1-4 3h-3"/>',
  send: '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  telegram: '<path d="M22 3 2 10.5l6 2.2L18.5 6 10 14v5l3-3 4.5 3.2z"/>',
  whatsapp: '<path d="M3 21l1.7-4.4A8 8 0 1 1 8 19.4z"/><path d="M9 8.5c0 3 3.3 6.5 6.5 6.5l1.3-1.6-2.2-1-.9.9c-1-.5-1.8-1.3-2.3-2.3l.9-.9-1-2.2z"/>',
  webchat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 10h.01M12 10h.01M16 10h.01"/>',
  paperclip: '<path d="M21 8.5 12.4 17a4 4 0 0 1-5.7-5.7l8-8a2.7 2.7 0 0 1 3.8 3.8l-8 8a1.3 1.3 0 0 1-1.9-1.9l7.2-7.2"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
};

export default function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"
      dangerouslySetInnerHTML={{ __html: PATHS[name] || PATHS.chart }} />
  );
}
