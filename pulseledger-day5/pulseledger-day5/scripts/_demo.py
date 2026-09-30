"""
Day 5 demo driver. Every step is a real HTTP call to the running backend,
which writes to and reads from the real database. Uses only the Python
standard library.

Safe to re-run. On a second run, people who already joined show up as
"already a member", and step 7 reissues a fresh browser link.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8005"
FRONTEND = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:4005"

NORTH, BRIGHT = "northwind-traders", "brightpath-labs"
ORGS = [
    (NORTH, "Northwind Traders", "ana@northwind.example", "Ana Ruiz"),
    (BRIGHT, "Brightpath Labs", "sam@brightpath.example", "Sam Okafor"),
]


def call(method: str, path: str, body: dict | None = None, tenant: str | None = None):
    headers = {"Content-Type": "application/json"}
    if tenant:
        headers["X-Tenant"] = tenant
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def step(n: int, title: str) -> None:
    print(f"\n{n}. {title}")


def members(slug: str) -> list[dict]:
    return call("GET", "/api/members", tenant=slug)[1]["members"]


def invite_and_accept(slug: str, email: str, role: str, name: str) -> None:
    code, inv = call("POST", "/api/invitations", {"email": email, "role": role}, tenant=slug)
    if code == 409:
        print(f"   invite {email:<24} HTTP 409  {inv['detail']}")
        return
    print(f"   invite {email:<24} HTTP {code}  token {inv['token'][:10]}… (shown once)")
    code, dup = call("POST", "/api/invitations", {"email": email, "role": role}, tenant=slug)
    print(f"   invite {email:<24} HTTP {code}  {dup.get('detail', '')}")
    code, joined = call("POST", "/api/invitations/accept", {"token": inv["token"], "name": name})
    print(f"   accept {'':<24} HTTP {code}  {joined['user']['name']} is now {joined['role']}")
    code, again = call("POST", "/api/invitations/accept", {"token": inv["token"], "name": name})
    print(f"   accept again {'':<18} HTTP {code}  {again['detail']}")


step(1, "Organizations, each created with its first owner (control plane)")
for slug, name, owner_email, owner_name in ORGS:
    code, _ = call("POST", "/api/tenants", {"slug": slug, "name": name,
                                            "owner": {"email": owner_email, "name": owner_name}})
    if code == 409:  # org exists from Day 3/4: give it an owner if it has none
        code, body = call("POST", f"/api/tenants/{slug}/owner", {"email": owner_email, "name": owner_name})
        note = "existing org, owner claimed" if code == 201 else body["detail"]
    else:
        note = "created"
    print(f"   {slug:<20} owner {owner_email:<24} HTTP {code}  {note}")
call("PATCH", f"/api/tenants/{BRIGHT}/status", {"status": "active"})

step(2, "Ana invites Li to Northwind as admin")
invite_and_accept(NORTH, "li@northwind.example", "admin", "Li Wei")

step(3, "One person, two organizations: Sam (Brightpath's owner) joins Northwind")
invite_and_accept(NORTH, "sam@brightpath.example", "member", "Sam Okafor")
for slug in (NORTH, BRIGHT):
    people = ", ".join(f"{m['name']} ({m['role']})" for m in members(slug))
    print(f"   {slug:<20} {people}")

step(4, "Brightpath looks at invitations (RLS)")
_, own = call("GET", "/api/invitations", tenant=BRIGHT)
_, north = call("GET", "/api/invitations", tenant=NORTH)
print(f"   Northwind has sent {len(north['invitations'])}. Brightpath sees "
      f"{len(own['invitations'])}: only its own, none of Northwind's.")

step(5, "Revoked and expired invitations can't be used")
code, inv = call("POST", "/api/invitations", {"email": "contractor@northwind.example"}, tenant=NORTH)
if code == 201:
    call("POST", f"/api/invitations/{inv['id']}/revoke", tenant=NORTH)
    code, r = call("POST", "/api/invitations/accept", {"token": inv["token"], "name": "C"})
    print(f"   revoked, then accepted           HTTP {code}  {r['detail']}")
code, inv = call("POST", "/api/invitations", {"email": "temp@northwind.example", "ttl_seconds": 2}, tenant=NORTH)
if code == 201:
    time.sleep(3)
    code, r = call("POST", "/api/invitations/accept", {"token": inv["token"], "name": "T"})
    print(f"   2-second invite, accepted at 3 s HTTP {code}  {r['detail']}")

step(6, "Nobody can remove Northwind's last owner")
ana = next(m for m in members(NORTH) if m["email"] == "ana@northwind.example")
code, r = call("PATCH", f"/api/members/{ana['user_id']}", {"role": "admin"}, tenant=NORTH)
print(f"   demote Ana to admin              HTTP {code}  {r['detail']}")
code, r = call("DELETE", f"/api/members/{ana['user_id']}", tenant=NORTH)
print(f"   remove Ana                       HTTP {code}  {r['detail']}")

step(7, "An invitation for you to accept in the browser")
_, listed = call("GET", "/api/invitations", tenant=NORTH)
for old in listed["invitations"]:
    if old["email"] == "guest@northwind.example" and old["status"] == "pending":
        call("POST", f"/api/invitations/{old['id']}/revoke", tenant=NORTH)  # resend = revoke + reissue
        print("   revoked the previous run's guest invitation (its token can't be shown again)")
code, inv = call("POST", "/api/invitations", {"email": "guest@northwind.example"}, tenant=NORTH)
if code == 201:
    print(f"   open: {FRONTEND}{inv['accept_path']}")
else:
    print(f"   HTTP {code}  {inv['detail']}")
