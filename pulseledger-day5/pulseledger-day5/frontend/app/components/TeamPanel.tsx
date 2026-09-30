"use client";

import { useCallback, useEffect, useState } from "react";

type Member = { user_id: string; email: string; name: string; role: string; joined_at: string };
type Invitation = {
  id: string;
  email: string;
  role: string;
  status: "pending" | "accepted" | "revoked" | "expired";
  expires_at: string;
};

const ROLES = ["member", "admin", "owner"] as const;

const statusTone: Record<string, string> = {
  pending: "text-ink",
  accepted: "text-ok",
  revoked: "text-muted",
  expired: "text-warn",
};

export default function TeamPanel({ api, slug, pollMs }: { api: string; slug: string; pollMs: number }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<(typeof ROLES)[number]>("member");
  const [link, setLink] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const headers = { "X-Tenant": slug };

  const load = useCallback(async () => {
    try {
      const [m, i] = await Promise.all([
        fetch(`${api}/api/members`, { headers: { "X-Tenant": slug }, cache: "no-store" }),
        fetch(`${api}/api/invitations`, { headers: { "X-Tenant": slug }, cache: "no-store" }),
      ]);
      if (m.ok) setMembers((await m.json()).members);
      if (i.ok) setInvitations((await i.json()).invitations);
    } catch {
      /* the page header already reports an unreachable API */
    }
  }, [api, slug]);

  useEffect(() => {
    setLink(null);
    setMessage(null);
    load();
    const id = setInterval(load, pollMs);
    return () => clearInterval(id);
  }, [load, pollMs]);

  async function sendInvite(e: React.FormEvent) {
    e.preventDefault();
    const r = await fetch(`${api}/api/invitations`, {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ email, role }),
    });
    const body = await r.json();
    if (r.ok) {
      setLink(`${window.location.origin}${body.accept_path}`);
      setMessage(`Invitation for ${body.email} created. The link is shown once; copy it now.`);
      setEmail("");
    } else {
      setLink(null);
      setMessage(`Not sent: ${typeof body.detail === "string" ? body.detail : "check the email address."}`);
    }
    load();
  }

  async function revoke(id: string) {
    await fetch(`${api}/api/invitations/${id}/revoke`, { method: "POST", headers });
    load();
  }

  return (
    <section className="mt-12" aria-labelledby="team-heading">
      <h2 id="team-heading" className="text-xl font-semibold">Team</h2>

      <ul className="mt-4" data-testid="members">
        {members.map((m) => (
          <li key={m.user_id} className="flex items-baseline justify-between gap-4 border-t border-rule py-3 text-sm">
            <span>
              <span className="font-medium">{m.name}</span>
              <span className="ml-2 text-muted">{m.email}</span>
            </span>
            <span className={`font-semibold ${m.role === "owner" ? "text-ink" : "text-muted"}`}>{m.role}</span>
          </li>
        ))}
        {members.length === 0 && (
          <li className="border-t border-rule py-3 text-sm text-muted">
            No members yet. Organizations from Day 3 and 4 have no owner until one is claimed.
          </li>
        )}
      </ul>

      <form onSubmit={sendInvite} className="mt-6 flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="invite-email">Email to invite</label>
        <input
          id="invite-email"
          required
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email to invite"
          className="min-w-52 flex-1 rounded-md border border-rule bg-white px-3 py-2 text-sm"
        />
        <label className="sr-only" htmlFor="invite-role">Role</label>
        <select
          id="invite-role"
          value={role}
          onChange={(e) => setRole(e.target.value as (typeof ROLES)[number])}
          className="rounded-md border border-rule bg-white px-3 py-2 text-sm"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <button
          type="submit"
          className="rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
        >
          Invite
        </button>
      </form>
      {message && <p className="mt-2 text-sm text-muted">{message}</p>}
      {link && (
        <p className="mt-1 break-all font-figures text-sm" data-testid="invite-link">
          <a className="underline" href={link}>{link}</a>
        </p>
      )}

      <h3 className="mt-8 text-base font-semibold">Invitations</h3>
      <ul className="mt-2" data-testid="invitations">
        {invitations.map((i) => (
          <li key={i.id} className="flex items-baseline justify-between gap-4 border-t border-rule py-2 text-sm">
            <span>
              {i.email} <span className="text-muted">as {i.role}</span>
            </span>
            <span className="flex items-baseline gap-3">
              <span className={statusTone[i.status]}>{i.status}</span>
              {i.status === "pending" && (
                <button onClick={() => revoke(i.id)} className="text-muted underline hover:text-ink">
                  Revoke
                </button>
              )}
            </span>
          </li>
        ))}
        {invitations.length === 0 && (
          <li className="border-t border-rule py-2 text-sm text-muted">No invitations sent from this organization.</li>
        )}
      </ul>
    </section>
  );
}
