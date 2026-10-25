#!/usr/bin/env python3
"""Generate ADMIN_PASSWORD_HASH locally; the plaintext password is never printed."""
import getpass
import hashlib
import secrets

def main():
    password = getpass.getpass("Choose admin password (minimum 12 characters): ")
    confirm = getpass.getpass("Confirm admin password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    if len(password) < 12:
        raise SystemExit("Use at least 12 characters.")
    salt = secrets.token_bytes(16)
    rounds = 600_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds).hex()
    print("ADMIN_PASSWORD_HASH=pbkdf2_sha256$%d$%s$%s" % (rounds, salt.hex(), digest))

if __name__ == "__main__":
    main()
