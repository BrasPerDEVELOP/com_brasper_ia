"use client";
import { useReportWebVitals } from "next/web-vitals";
import { API_BASE, getToken } from "@/lib/api";

// Reporta Core Web Vitals al backend (POST /api/ops/web-vitals) para seguir la
// velocidad real del panel. Referencia estable: Next llama al callback por métrica.
const report = (metric: { name: string; value: number; rating?: string }) => {
  const token = getToken();
  if (!token) return; // sin sesión no hay a quién atribuirlo
  const body = JSON.stringify({ name: metric.name, value: metric.value, rating: metric.rating, path: location.pathname });
  fetch(API_BASE + "/api/ops/web-vitals", {
    method: "POST", keepalive: true,
    headers: { "Content-Type": "application/json", "X-Auth-Token": token },
    body,
  }).catch(() => {});
};

export default function WebVitals() {
  useReportWebVitals(report);
  return null;
}
