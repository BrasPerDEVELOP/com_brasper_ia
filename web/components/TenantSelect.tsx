"use client";
import { useEffect } from "react";

export default function TenantSelect({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  useEffect(() => {
    if (value !== "brasper") onChange("brasper");
  }, [value, onChange]);
  return <span style={{ fontWeight: 600, padding: "0 8px", color: "var(--fg)" }}>Brasper</span>;
}
