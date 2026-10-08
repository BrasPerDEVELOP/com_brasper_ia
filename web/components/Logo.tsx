// Isotipo provisional Brasper: "B" con flecha de remesa (azul) y detalle amarillo.
// Reemplazar por el SVG oficial cuando el equipo lo entregue (public/brand/).
export default function Logo({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 4h7.5a4 4 0 0 1 2.6 7 4.5 4.5 0 0 1-2.6 9H6z" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M9.5 8.5h3.5M9.5 15.5h3.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <path d="M16.5 12h4.5m0 0-2-2m2 2-2 2" stroke="#F2C230" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
