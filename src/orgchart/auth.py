from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from typing import Any

PASSWORD_ITERATIONS = 310_000
ROLES = {"admin", "manager", "readonly"}


@dataclass(frozen=True)
class User:
    username: str
    role: str
    company_ids: tuple[str, ...] = ()


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iteration_text, salt_hex, digest_hex = encoded_hash.split("$", 3)
        iterations = int(iteration_text)
        if algorithm != "pbkdf2_sha256" or iterations < 100_000 or iterations > 2_000_000:
            return False
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


def parse_users(raw: str | None) -> dict[str, dict[str, Any]]:
    if not raw:
        return {}
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("ORGCHART_USERS_JSON must contain a JSON array of account objects.") from exc
    if not isinstance(entries, list):
        raise ValueError("ORGCHART_USERS_JSON must contain a JSON array.")
    users = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each account must be a JSON object.")
        username = str(entry.get("username", "")).strip()
        role = str(entry.get("role", "")).lower()
        password_hash = str(entry.get("password_hash", ""))
        if not username or role not in ROLES or not password_hash.startswith("pbkdf2_sha256$"):
            raise ValueError("Each account needs a username, valid role, and PBKDF2 password_hash.")
        key = username.casefold()
        if key in users:
            raise ValueError(f"Duplicate username: {username}")
        scope = entry.get("company_ids", [])
        if not isinstance(scope, list) or any(not isinstance(company_id, str) for company_id in scope):
            raise ValueError(f"company_ids for {username} must be a list of company IDs.")
        users[key] = {"username": username, "role": role, "password_hash": password_hash, "company_ids": tuple(scope)}
    return users


def configured_users() -> dict[str, dict[str, Any]]:
    raw = os.getenv("ORGCHART_USERS_JSON")
    if not raw:
        try:
            import streamlit as st

            raw = st.secrets.get("ORGCHART_USERS_JSON")
        except Exception:
            raw = None
    return parse_users(raw)


def authenticate(username: str, password: str, users: dict[str, dict[str, Any]]) -> User | None:
    record = users.get(username.strip().casefold())
    if not record or not verify_password(password, record["password_hash"]):
        return None
    return User(record["username"], record["role"], record["company_ids"])


def can_manage_employees(user: User, company_id: str) -> bool:
    if user.role == "admin":
        return True
    return user.role == "manager" and ("*" in user.company_ids or company_id in user.company_ids)
