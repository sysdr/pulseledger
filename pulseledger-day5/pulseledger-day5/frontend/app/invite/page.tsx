"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8005";

type Preview = {
  organization: string;
  email: string;
  role: string;
  status: "pending" | "accepted" | "revoked" | "expired";
  expires_at: string;
};

function AcceptInvitation() {
  const token = useSearchParams().get("token") ?? "";
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setError("This link has no invitation token.");
      return;
    }
    fetch(`${API}/api/invitations/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then(async (r) => {
        const body = await r.json();
        if (r.ok) setPreview(body);
        else setError(body.detail ?? "This invitation can't be found.");
      })
      .catch(() => setError(`Can't reach the API at ${API}`));
  }, [token]);

  async function accept(e: React.FormEvent) {
    e.preventDefault();
    const r = await fetch(`${API}/api/invitations/accept`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, name }),
    });
    const body = await r.json();
    if (r.ok) setDone(`You're now ${body.role === "admin" ? "an" : "a"} ${body.role} of ${body.organization}.`);
    else setError(body.detail);
  }

  return (
    <main className="mx-auto max-w-md px-6 py-20">
      <p className="text-sm font-semibold text-muted">PulseLedger</p>

      {error && (
        <>
          <h1 className="mt-2 text-2xl font-bold tracking-tight">This invitation can't be used</h1>
          <p className="mt-3 text-warn" data-testid="invite-error">{error}</p>
        </>
      )}

      {!error && !preview && <p className="mt-2 text-muted">Checking your invitation…</p>}

      {!error && preview && !done && (
        <>
          <h1 className="mt-2 text-2xl font-bold tracking-tight">Join {preview.organization}</h1>
          <p className="mt-3 text-muted">
            {preview.email} is invited as <span className="font-semibold text-ink">{preview.role}</span>.
          </p>
          {preview.status === "pending" ? (
            <form onSubmit={accept} className="mt-8 flex flex-col gap-3">
              <label htmlFor="name" className="text-sm font-medium">Your name</label>
              <input
                id="name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="rounded-md border border-rule bg-white px-3 py-2"
              />
              <button
                type="submit"
                className="rounded-md bg-ink px-4 py-2 font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                Accept invitation
              </button>
            </form>
          ) : (
            <p className="mt-6 text-warn">This invitation is {preview.status}.</p>
          )}
        </>
      )}

      {done && (
        <>
          <h1 className="mt-2 text-2xl font-bold tracking-tight">Welcome aboard</h1>
          <p className="mt-3 text-ok" data-testid="invite-done">{done}</p>
          <Link href="/" className="mt-6 inline-block underline">Back to the dashboard</Link>
        </>
      )}
    </main>
  );
}

export default function InvitePage() {
  return (
    <Suspense fallback={<main className="mx-auto max-w-md px-6 py-20 text-muted">Loading…</main>}>
      <AcceptInvitation />
    </Suspense>
  );
}
