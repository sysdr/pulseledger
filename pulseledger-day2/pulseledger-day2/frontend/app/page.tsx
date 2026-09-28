"use client";

import { useEffect, useState } from "react";

type Probe = {
  ok: boolean;
  latency_ms: number;
  version: string | null;
  details: Record<string, string | number | null>;
  error: string | null;
};

type Readiness = {
  state: "starting" | "ready" | "degraded" | "stopping";
  day?: number;
  state_changed_at?: string;
  transitions?: number;
  stripe_mode?: string;
  dependencies?: { postgres: Probe; redis: Probe };
};

type Boot = {
  id: string;
  initial_state: string;
  postgres_version: string;
  pgvector_version: string;
  redis_version: string;
  booted_at: string;
};

// NEXT_PUBLIC_* values are inlined at build time, and this code runs in the
// browser, so the address must be one the reader's browser can reach — the
// host port, never a Docker Compose service name.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8002";
const POLL_MS = 3000;

const stateStyle: Record<string, { dot: string; text: string; label: string }> = {
  ready: { dot: "bg-ok", text: "text-ok", label: "Ready" },
  degraded: { dot: "bg-warn", text: "text-warn", label: "Degraded" },
  starting: { dot: "bg-idle", text: "text-muted", label: "Starting" },
  stopping: { dot: "bg-idle", text: "text-muted", label: "Stopping" },
  unreachable: { dot: "bg-idle", text: "text-muted", label: "API unreachable" },
};

function DependencyRow({ name, probe }: { name: string; probe?: Probe }) {
  const ok = probe?.ok ?? false;
  const facts: string[] = [];
  if (probe?.version) facts.push(`v${probe.version}`);
  if (probe?.details?.pgvector) facts.push(`pgvector ${probe.details.pgvector}`);
  if (probe?.details?.round_trip) facts.push(`round trip ${probe.details.round_trip}`);

  return (
    <li className="flex items-baseline justify-between gap-4 border-t border-rule py-4">
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-base font-semibold">
          <span className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-ok" : "bg-warn"}`} />
          {name}
        </p>
        <p className="mt-1 truncate text-sm text-muted" data-testid={`${name.toLowerCase()}-facts`}>
          {ok ? facts.join(", ") : (probe?.error ?? "no answer")}
        </p>
      </div>
      <p className="shrink-0 font-figures text-sm tabular-nums text-muted">
        {probe ? `${probe.latency_ms.toFixed(1)} ms` : ""}
      </p>
    </li>
  );
}

export default function Home() {
  const [ready, setReady] = useState<Readiness | null>(null);
  const [boots, setBoots] = useState<Boot[]>([]);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        // 503 still carries a JSON body describing what's wrong.
        const r = await fetch(`${API_BASE}/api/ready`, { cache: "no-store" });
        const body: Readiness = await r.json();
        const b = await fetch(`${API_BASE}/api/boots?limit=5`, { cache: "no-store" });
        const bootBody = b.ok ? await b.json() : { boots: [] };
        if (!cancelled) {
          setReady(body);
          setBoots(bootBody.boots);
          setUnreachable(false);
        }
      } catch {
        if (!cancelled) setUnreachable(true);
      }
    }

    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const key = unreachable ? "unreachable" : (ready?.state ?? "starting");
  const style = stateStyle[key];

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">PulseLedger</h1>
        <p className="mt-1 text-muted">Day 2: Dev environment</p>
      </header>

      <section className="mt-12" aria-live="polite">
        <p className={`flex items-center gap-3 text-4xl font-semibold ${style.text}`} data-testid="service-state">
          <span className={`inline-block h-4 w-4 rounded-full ${style.dot}`} />
          {style.label}
        </p>
        <p className="mt-2 text-sm text-muted">
          {ready?.state_changed_at
            ? `In this state since ${new Date(ready.state_changed_at).toLocaleTimeString()}. Stripe: ${ready.stripe_mode}.`
            : `Waiting for ${API_BASE}/api/ready`}
        </p>
      </section>

      <ul className="mt-10">
        <DependencyRow name="Postgres" probe={ready?.dependencies?.postgres} />
        <DependencyRow name="Redis" probe={ready?.dependencies?.redis} />
      </ul>

      <section className="mt-12">
        <h2 className="text-base font-semibold">Recent boots</h2>
        <p className="mt-1 text-sm text-muted">Each process start writes one row to Postgres.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-muted">
              <tr>
                <th className="py-2 pr-4 font-medium">Started</th>
                <th className="py-2 pr-4 font-medium">First state</th>
                <th className="py-2 pr-4 font-medium">Postgres</th>
                <th className="py-2 font-medium">Redis</th>
              </tr>
            </thead>
            <tbody className="font-figures tabular-nums">
              {boots.map((b) => (
                <tr key={b.id} className="border-t border-rule">
                  <td className="py-2 pr-4">{new Date(b.booted_at).toLocaleString()}</td>
                  <td className="py-2 pr-4">{b.initial_state}</td>
                  <td className="py-2 pr-4">{b.postgres_version}</td>
                  <td className="py-2">{b.redis_version}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {boots.length === 0 && <p className="py-3 text-sm text-muted">No boots recorded yet.</p>}
        </div>
      </section>
    </main>
  );
}
