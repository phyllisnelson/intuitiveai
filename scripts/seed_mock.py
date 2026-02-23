#!/usr/bin/env python3
"""scripts/seed_mock.py — Re-seed the local mock server with test fixtures.

Calls POST /dev/seed on the running local API server, which repopulates the
MockOpenStackService with factory_boy-generated VMs, flavors, and images,
then prints the resource IDs for use in Postman or manual testing.

Usage:
    python scripts/seed_mock.py                      # default: http://localhost:8000
    python scripts/seed_mock.py http://localhost:9000
    API_URL=http://localhost:9000 python scripts/seed_mock.py

    # Or via make inside the local container:
    docker compose -f docker-compose.yml -f docker-compose.local.yml \\
        exec -T api python scripts/seed_mock.py
"""

import json
import os
import sys
import urllib.error
import urllib.request


def seed(api_url: str) -> dict:
    url = f"{api_url.rstrip('/')}/dev/seed"
    req = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(f"ERROR: server returned HTTP {exc.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    api_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("API_URL", "http://localhost:8000")
    )

    data = seed(api_url)

    active = data["vms"]["active"]
    shutoff = data["vms"]["shutoff"]
    flavors = data["flavors"]
    images = data["images"]

    print("Mock seeded successfully.")
    print()
    print("VMs (ACTIVE):")
    for i, vid in enumerate(active, 1):
        print(f"  seeded_active_vm_{i}: {vid}")
    print("VMs (SHUTOFF):")
    for i, vid in enumerate(shutoff, 1):
        print(f"  seeded_shutoff_vm_{i}: {vid}")
    print()
    print(f"Flavors: {', '.join(flavors)}")
    print(f"Images:  {', '.join(images)}")


if __name__ == "__main__":
    main()
