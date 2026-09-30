"""Formats backend JSON for verify.sh and demo.sh. Reads the JSON from stdin."""
import json
import sys

mode = sys.argv[1]
data = json.load(sys.stdin)

if mode == "summary":
    pg = data["dependencies"]["postgres"]
    rd = data["dependencies"]["redis"]
    print(f"  state     {data['state']}")
    print(f"  postgres  {pg['version']}  pgvector {pg['details'].get('pgvector')}  {pg['latency_ms']} ms")
    print(f"  redis     {rd['version']}  round trip {rd['details'].get('round_trip')}  {rd['latency_ms']} ms")
    ar = data["dependencies"].get("app_role")
    if ar:
        d = ar["details"]
        print(f"  app role  {d.get('role')}  superuser {d.get('superuser')}  "
              f"can_update_tenants {d.get('can_update_tenants')}  ok {ar['ok']}")
    iso = data["dependencies"].get("isolation")
    if iso:
        for table, t in iso["details"].get("tables", {}).items():
            print(f"  isolation {table}  rls {t['rls']}  forced {t['forced']}  "
                  f"rows without tenant {t['visible_without_tenant']}  ok {iso['ok']}")

elif mode == "state":
    code = sys.argv[2]
    rd = data["dependencies"]["redis"]
    print(f"     HTTP {code}  state={data['state']}  transitions={data['transitions']}  redis_ok={rd['ok']}")
    if rd["error"]:
        print(f"     redis error: {rd['error']}")

elif mode == "boots":
    for b in data["boots"]:
        print(f"  {b['booted_at'][:19]}  day {b['lesson_day']}  {b['initial_state']:<9}"
              f"  pg {b['postgres_version']}  redis {b['redis_version']}")
