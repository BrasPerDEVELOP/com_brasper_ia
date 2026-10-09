/** Convert an operator's wall-clock date using the selected IANA zone. */
export function wallTime(iso: string, zone: string): string {
  if (!iso) return "";
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(iso));
  const p = Object.fromEntries(parts.map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

export function toInstant(wall: string, zone: string): string {
  if (!wall) return "";
  const target = Date.parse(wall + ":00Z");
  if (!Number.isFinite(target)) throw new Error("Fecha no válida");
  let candidate = target;
  for (let i = 0; i < 4; i++) {
    const observed = Date.parse(wallTime(new Date(candidate).toISOString(), zone) + ":00Z");
    candidate += target - observed;
  }
  if (wallTime(new Date(candidate).toISOString(), zone) !== wall) throw new Error("Esa hora no existe en la zona seleccionada");
  for (const delta of [-3600000, 3600000]) {
    if (wallTime(new Date(candidate + delta).toISOString(), zone) === wall) throw new Error("Hora ambigua por cambio de horario; elige otra hora");
  }
  return new Date(candidate).toISOString();
}
