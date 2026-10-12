"""Generate the customer-build trust anchor from PUBLIC Ed25519 keys.

The private signing key is never needed to build or run Trip Orders.
Commercial installers MUST have a pinned, non-empty list of trusted public
keys. Development runs without this generated module retain their historical
contract-mode behavior for tests.
"""
import base64
import os
import re

_PUBLIC_KEY = re.compile(r"^[A-Za-z0-9_-]{43}$")


def parse_public_keys(text):
    """Require canonical, unpadded base64url encodings of 32-byte public keys."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("TO_RELEASE_PUBLIC_KEYS is required for every customer installer")
    found = []
    for entry in text.split(","):
        key = entry.strip()
        if not _PUBLIC_KEY.fullmatch(key):
            raise ValueError("Expected a 43-character unpadded base64url Ed25519 PUBLIC key")
        try:
            raw = base64.b64decode(key + "=", altchars=b"-_", validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("Invalid public key encoding") from exc
        if len(raw) != 32 or raw == b"\x00" * 32 or base64.urlsafe_b64encode(raw).rstrip(b"=").decode() != key:
            raise ValueError("Invalid Ed25519 public key")
        if key in found:
            raise ValueError("Duplicate release public key")
        found.append(key)
    return tuple(found)


def create_release_policy(output, raw_keys, channel="commercial"):
    """Write a temporary Python module compiled into TripOrders.exe."""
    keys = parse_public_keys(raw_keys)
    if channel not in ("commercial", "ci-test"):
        raise ValueError("Invalid release channel")
    if os.path.exists(output):
        raise ValueError("A release policy already exists: refusing an ambiguous build")
    with open(output, "x", encoding="ascii") as f:
        f.write('"""Generated for a commercial installer. PUBLIC keys only. Do not edit."""\n')
        f.write("COMMERCIAL_BUILD = True\n")
        f.write("TRUSTED_KEYS = " + repr(keys) + "\n")
    return len(keys)
