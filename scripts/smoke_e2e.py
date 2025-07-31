#!/usr/bin/env python
"""Minimaler End-to-End-Smoke-Test."""

import argparse
import sys
import time

import requests

API = "http://localhost:8000"


def main(tenant: str, purpose: str) -> int:
    # Purpose anlegen
    r = requests.post(f"{API}/api/purpose", json={"tenant_id": tenant, "name": purpose})
    r.raise_for_status()
    purp_id = r.json()["id"]
    print("✅ Purpose created:", purp_id)

    # warten bis Tasks durch sind
    while True:
        rows = requests.get(f"{API}/backlog", params={"tenant": tenant}).json()
        undone = [t for t in rows if t.get("status") in {"todo", "doing"}]
        if not undone:
            break
        print("⏳ open:", len(undone))
        time.sleep(3)

    # Artefakte abrufen
    arts = requests.get(f"{API}/api/artifacts", params={"tenant": tenant}).json()
    if not arts:
        raise SystemExit("No artefacts produced!")
    print(f"🎉 {len(arts)} artefacts produced – smoke test PASS")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="demo")
    ap.add_argument("--purpose", default="Smoke-Test Hello-World")
    ns = ap.parse_args()
    sys.exit(main(ns.tenant, ns.purpose))
