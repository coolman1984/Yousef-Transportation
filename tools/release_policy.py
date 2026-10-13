"""Generate the customer-build trust anchor from PUBLIC Ed25519 keys.

The private signing key is never needed to build or run Trip Orders.
Commercial installers MUST have a pinned, non-empty list of trusted public
keys. Development runs without this generated module retain their historical
contract-mode behavior for tests.

Entries may be bare public keys or labelled `kid:publicKey`. The trial-hub
kid marks keys that may sign trial editions only (at most 14 days).
"""
import base64
import os
import re

_PUBLIC_KEY = re.compile(r"^[A-Za-z0-9_-]{43}$")
_TRIAL_HUB_KIDS = frozenset({"trial-hub", "trial_hub", "hub-trial"})


def _parse_one_key(key):
    if not _PUBLIC_KEY.fullmatch(key):
        raise ValueError("Expected a 43-character unpadded base64url Ed25519 PUBLIC key")
    try:
        raw = base64.b64decode(key + "=", altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("Invalid public key encoding") from exc
    if len(raw) != 32 or raw == b"\x00" * 32 or base64.urlsafe_b64encode(raw).rstrip(b"=").decode() != key:
        raise ValueError("Invalid Ed25519 public key")
    return key


def parse_public_keys(text):
    """Require canonical, unpadded base64url encodings of 32-byte public keys."""
    entries, _trial = parse_key_entries(text)
    return tuple(key for _, key in entries)


def parse_key_entries(text):
    """Return ((kid, key), ...) and frozenset of trial-only public keys."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("TO_RELEASE_PUBLIC_KEYS is required for every customer installer")
    found = []
    entries = []
    trial_only = []
    for entry in text.split(","):
        entry = entry.strip()
        if not entry:
            continue
        kid = ""
        key_part = entry
        if ":" in entry and len(entry.split(":", 1)[0]) <= 40:
            kid, key_part = entry.split(":", 1)
            kid = kid.strip()
            key_part = key_part.strip()
        key = _parse_one_key(key_part)
        if key in found:
            raise ValueError("Duplicate release public key")
        found.append(key)
        entries.append((kid, key))
        if kid and kid.lower() in _TRIAL_HUB_KIDS:
            trial_only.append(key)
    if not entries:
        raise ValueError("TO_RELEASE_PUBLIC_KEYS is required for every customer installer")
    return tuple(entries), frozenset(trial_only)


def create_release_policy(output, raw_keys, channel="commercial"):
    """Write a temporary Python module compiled into TripOrders.exe."""
    entries, trial_only = parse_key_entries(raw_keys)
    keys = tuple(key for _, key in entries)
    if channel == "commercial" and not trial_only:
        raise ValueError("Commercial build must pin a trial-hub public key (kid trial-hub:...)")
    if channel not in ("commercial", "ci-test"):
        raise ValueError("Invalid release channel")
    if os.path.exists(output):
        raise ValueError("A release policy already exists: refusing an ambiguous build")
    with open(output, "x", encoding="ascii") as f:
        f.write('"""Generated for a commercial installer. PUBLIC keys only. Do not edit."""\n')
        f.write("COMMERCIAL_BUILD = True\n")
        f.write("BUILD_CHANNEL = " + repr(channel) + "\n")
        f.write("TRUSTED_KEYS = " + repr(keys) + "\n")
        f.write("TRUSTED_KEY_ENTRIES = " + repr(entries) + "\n")
        f.write("TRIAL_ONLY_PUBLIC_KEYS = " + repr(trial_only) + "\n")
        f.write("MAX_TRIAL_DAYS = 14\n")
    return len(keys)
