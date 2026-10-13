"""Prepare an ephemeral Ed25519 keypair for Windows CI TEST builds only.

No production key is created or stored here. The test private key is transient,
kept only in the runner's private temp directory, and never uploaded or printed.
These installers MUST NOT be shipped to customers.
"""
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    env = os.environ.get("GITHUB_ENV")
    temp = os.environ.get("RUNNER_TEMP")
    if not env or not temp:
        raise SystemExit("CI-only script; requires GitHub runner")
    private = Ed25519PrivateKey.generate()
    key_path = Path(temp) / "trip-orders-ci-only-signing-key.pem"
    if key_path.exists():
        raise SystemExit("Refusing to overwrite CI signing material")
    key_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode().rstrip("=")
    # studio: matches commercial kid policy; bare keys remain accepted by release_policy.py
    with open(env, "a", encoding="utf-8") as f:
        f.write("TO_RELEASE_PUBLIC_KEYS=studio:" + public + "\n")
        f.write("TO_TEST_SIGNING_KEY_FILE=" + str(key_path) + "\n")
        f.write("TO_BUILD_CHANNEL=ci-test\n")
    print("Created ephemeral public verification key for CI test-build; NO customer release")


if __name__ == "__main__":
    main()
