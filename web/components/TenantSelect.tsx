"use client";
import { useEffect, useState } from "react";
import { api, Tenant } from "@/lib/api";

export default function TenantSelect({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  useEffect(() => {
    api<{ tenants: Tenant[] }>("/api/tenants").then(d => {
      setTenants(d.tenants);
      if (!value && d.tenants[0]) onChange(d.tenants[0].id);
    }).catch(() => {});
  }, []);
  return (
    <select value={value} onChange={e => onChange(e.target.value)}>
      {tenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
    </select>
  );
}
