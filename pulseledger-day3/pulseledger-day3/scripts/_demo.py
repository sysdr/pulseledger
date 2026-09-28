"""
Day 3 demo driver. Every step is a real HTTP call to the running backend,
which writes to and reads from the real database. Safe to re-run: tenants
and customers that already exist are reused (the API answers 409).
Uses only the Python standard library.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8003"

TENANTS = [
    ("northwind-traders", "Northwind Traders"),
    ("brightpath-labs", "Brightpath Labs"),
]
CUSTOMERS = {
    "northwind-traders": [("Ana Ruiz", "ana@northwind.example"), ("Acme Corp", "billing@acme.example")],
    "brightpath-labs": [("Sam Okafor", "sam@brightpath.example"), ("Acme Corp", "billing@acme.example")],
}


def call(method: str, path: str, body: dict | None = None, tenant: str | None = None):
    headers = {"Content-Type": "application/json"}
    if tenant:
        headers["X-Tenant"] = tenant
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def step(n: int, title: str) -> None:
    print(f"\n{n}. {title}")


step(1, "Create two tenants (control plane, POST /api/tenants)")
for slug, name in TENANTS:
    code, _ = call("POST", "/api/tenants", {"slug": slug, "name": name})
    print(f"   {slug:<20} HTTP {code}  {'created' if code == 201 else 'already exists'}")
call("PATCH", "/api/tenants/brightpath-labs/status", {"status": "active"})

step(2, "Add customers (data plane, X-Tenant header)")
for slug, people in CUSTOMERS.items():
    for name, email in people:
        code, _ = call("POST", "/api/customers", {"name": name, "email": email}, tenant=slug)
        note = "  already there" if code == 409 else ""
        print(f"   {slug:<20} {email:<26} HTTP {code}{note}")

step(3, "Each tenant lists its customers through customers_of(tenant)")
ids = {}
for slug, _ in TENANTS:
    _, body = call("GET", "/api/customers", tenant=slug)
    emails = [c["email"] for c in body["customers"]]
    ids[slug] = [c["id"] for c in body["customers"]]
    print(f"   {slug:<20} sees {len(emails)}: {', '.join(emails)}")

step(4, "Brightpath asks for a Northwind customer by its exact id")
target = ids["northwind-traders"][0]
code, _ = call("GET", f"/api/customers/{target}", tenant="northwind-traders")
print(f"   as northwind-traders  GET /api/customers/{target[:8]}...  HTTP {code}")
code, body = call("GET", f"/api/customers/{target}", tenant="brightpath-labs")
print(f"   as brightpath-labs    GET /api/customers/{target[:8]}...  HTTP {code}  {body['detail']}")

step(5, "Uniqueness is per tenant: billing@acme.example exists in both")
code, body = call("POST", "/api/customers", {"name": "Acme", "email": "BILLING@acme.example"}, tenant="northwind-traders")
print(f"   northwind-traders  BILLING@acme.example  HTTP {code}  {body.get('detail', '')}")

step(6, "Tenant lifecycle: suspend Brightpath, try to read and write, reactivate")
code, t = call("PATCH", "/api/tenants/brightpath-labs/status", {"status": "suspended"})
print(f"   PATCH status=suspended   HTTP {code}  now {t['status']}")
code, _ = call("GET", "/api/customers", tenant="brightpath-labs")
print(f"   GET  /api/customers      HTTP {code}  reads still allowed")
code, body = call("POST", "/api/customers", {"name": "Jo", "email": "jo@brightpath.example"}, tenant="brightpath-labs")
print(f"   POST /api/customers      HTTP {code}  {body['detail']}")
print("   (holding 5 s so the dashboard shows Brightpath as suspended)")
time.sleep(5)
code, t = call("PATCH", "/api/tenants/brightpath-labs/status", {"status": "active"})
print(f"   PATCH status=active      HTTP {code}  now {t['status']}")
