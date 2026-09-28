"use client";

import { useCallback, useEffect, useState } from "react";

type Tenant = {
  id: string;
  slug: string;
  name: string;
  status: "active" | "suspended" | "closed";
  customer_count: number;
  allowed_next: string[];
};

type Customer = { id: string; tenant_id: string; email: string; name: string; created_at: string };

type AppRole = {
  ok: boolean;
  details: { role?: string; superuser?: boolean; can_update_tenants?: boolean };
  error: string | null;
};

// NEXT_PUBLIC_* values are inlined at build time and run in the browser,
// so this must be the host address, never a Compose service name.
const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8003";
const POLL_MS = 3000;

const statusTone: Record<string, string> = {
  active: "text-ok",
  suspended: "text-warn",
  closed: "text-muted",
};

export default function Home() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [appRole, setAppRole] = useState<AppRole | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [formMessage, setFormMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const t = await fetch(`${API}/api/tenants`, { cache: "no-store" }).then((r) => r.json());
      setTenants(t.tenants);
      const ready = await fetch(`${API}/api/ready`, { cache: "no-store" }).then((r) => r.json());
      setAppRole(ready.dependencies?.app_role ?? null);

      const slug = selected ?? t.tenants.find((x: Tenant) => x.status !== "closed")?.slug ?? null;
      if (slug && slug !== selected) setSelected(slug);
      if (slug) {
        const r = await fetch(`${API}/api/customers`, {
          headers: { "X-Tenant": slug },
          cache: "no-store",
        });
        const body = await r.json();
        if (r.ok) {
          setCustomers(body.customers);
          setListError(null);
        } else {
          setCustomers([]);
          setListError(body.detail);
        }
      }
    } catch {
      setListError(`Can't reach the API at ${API}`);
    }
  }, [selected]);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  async function addCustomer(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    const r = await fetch(`${API}/api/customers`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Tenant": selected },
      body: JSON.stringify({ email, name }),
    });
    const body = await r.json();
    if (r.ok) {
      setEmail("");
      setName("");
      setFormMessage(`Added ${body.email} to ${selected}.`);
    } else {
      const detail = typeof body.detail === "string" ? body.detail : "Check the email and name.";
      setFormMessage(`Not added: ${detail}`);
    }
    load();
  }

  const current = tenants.find((t) => t.slug === selected);

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <header className="flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">PulseLedger</h1>
          <p className="mt-1 text-muted">Day 3: Multi-tenant data model</p>
        </div>
        <p className={`text-sm ${appRole?.ok ? "text-ok" : "text-warn"}`} data-testid="app-role">
          {appRole
            ? appRole.ok
              ? `Tenant queries run as ${appRole.details.role}, which can't edit the tenant list`
              : `Data-plane role check failing: ${appRole.error}`
            : "Checking the data-plane role…"}
        </p>
      </header>

      <nav className="mt-10 flex flex-wrap gap-2" aria-label="Tenants">
        {tenants.length === 0 && (
          <p className="text-sm text-muted">No tenants yet. Run ./scripts/demo.sh to create two.</p>
        )}
        {tenants.map((t) => (
          <button
            key={t.id}
            onClick={() => setSelected(t.slug)}
            disabled={t.status === "closed"}
            aria-pressed={t.slug === selected}
            className={`rounded-md border px-4 py-2 text-left text-sm focus-visible:outline-2 focus-visible:outline-ink disabled:opacity-40 ${
              t.slug === selected ? "border-ink bg-white" : "border-rule"
            }`}
          >
            <span className="block font-semibold">{t.name}</span>
            <span className={`block ${statusTone[t.status]}`}>
              {t.status}, {t.customer_count} {t.customer_count === 1 ? "customer" : "customers"}
            </span>
          </button>
        ))}
      </nav>

      {current && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold">
            {current.name}
            <span className="ml-2 font-figures text-sm font-normal text-muted">X-Tenant: {current.slug}</span>
          </h2>

          {listError && <p className="mt-3 text-sm text-warn">{listError}</p>}

          <ul className="mt-4" data-testid="customers">
            {customers.map((c) => (
              <li key={c.id} className="flex justify-between gap-4 border-t border-rule py-3 text-sm">
                <span>
                  <span className="font-medium">{c.name}</span>
                  <span className="ml-2 text-muted">{c.email}</span>
                </span>
                <span className="font-figures text-muted">{c.id.slice(0, 8)}</span>
              </li>
            ))}
            {customers.length === 0 && !listError && (
              <li className="border-t border-rule py-3 text-sm text-muted">No customers in this tenant yet.</li>
            )}
          </ul>

          <form onSubmit={addCustomer} className="mt-6 flex flex-wrap gap-2">
            <label className="sr-only" htmlFor="name">Name</label>
            <input
              id="name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Name"
              className="min-w-40 flex-1 rounded-md border border-rule bg-white px-3 py-2 text-sm"
            />
            <label className="sr-only" htmlFor="email">Email</label>
            <input
              id="email"
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email"
              className="min-w-52 flex-1 rounded-md border border-rule bg-white px-3 py-2 text-sm"
            />
            <button
              type="submit"
              className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
            >
              Add customer
            </button>
          </form>
          {formMessage && <p className="mt-2 text-sm text-muted">{formMessage}</p>}
        </section>
      )}
    </main>
  );
}
