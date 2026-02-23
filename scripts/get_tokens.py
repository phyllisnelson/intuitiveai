#!/usr/bin/env python3
"""scripts/get_token.py — Fetch Keycloak Bearer tokens for read and write access.

Runs inside the local API container where KEYCLOAK_URL already points to the
Keycloak service on the Docker network (http://keycloak:8080).

Outputs tokens for both read-only (alice, vm-reader) and write access
(bob, vm-operator) users.

Usage:
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec api python scripts/get_token.py

    # Or via make:
    make get-token

Required environment variables (all set automatically in docker-compose.local.yml):
    KEYCLOAK_URL           e.g. http://keycloak:8080
    KEYCLOAK_REALM         default: vm-api
    KEYCLOAK_CLIENT_ID     default: vm-api
    KEYCLOAK_CLIENT_SECRET

Optional (override at call site or in .env):
    KEYCLOAK_PASSWORD      Keycloak password (default: changeme)
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def get_token(
    username: str,
    url: str,
    realm: str,
    client_id: str,
    client_secret: str,
    password: str,
) -> str:
    """Fetch a token for the given username."""
    token_url = f"{url}/realms/{realm}/protocol/openid-connect/token"
    data = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "password",
            "username": username,
            "password": password,
        },
    ).encode()

    try:
        req = urllib.request.Request(token_url, data=data, method="POST")
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read())
        print(f"ERROR: Keycloak returned HTTP {exc.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    token = body.get("access_token", "")
    if not token:
        print(f"ERROR: No access_token in response: {body}", file=sys.stderr)
        sys.exit(1)

    return token


def main() -> None:
    url = os.environ.get("KEYCLOAK_URL", "")
    realm = os.environ.get("KEYCLOAK_REALM", "vm-api")
    client_id = os.environ.get("KEYCLOAK_CLIENT_ID", "vm-api")
    client_secret = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")
    password = os.environ.get("KEYCLOAK_PASSWORD", "changeme")

    if not url:
        print("ERROR: KEYCLOAK_URL is not set.", file=sys.stderr)
        sys.exit(1)

    # Fetch read, write, and read/write tokens
    read_token = get_token("alice", url, realm, client_id, client_secret, password)
    write_token = get_token("bob", url, realm, client_id, client_secret, password)
    readwrite_token = get_token(
        "charlie",
        url,
        realm,
        client_id,
        client_secret,
        password,
    )

    # Output tokens with labels
    print("READ TOKEN (alice, vm-reader role):")
    print(read_token)
    print()
    print("WRITE TOKEN (bob, vm-operator role):")
    print(write_token)
    print()
    print("READ/WRITE TOKEN (charlie, vm-reader + vm-operator roles):")
    print(readwrite_token)
    print()
    print("API_KEY (fallback, has both roles):")
    api_key = os.environ.get("API_KEY", "changeme")
    print(api_key)


if __name__ == "__main__":
    main()
