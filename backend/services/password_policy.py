"""Local password policy shared with the browser; passwords never leave the auth flow.

This intentionally small common-password blocklist is not a breach database.
Existing credentials remain valid at login; validate only newly chosen passwords.
"""
import json
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, Field
from pydantic_core import PydanticCustomError

POLICY = json.loads((Path(__file__).resolve().parents[2] / "frontend/data/password-policy.json").read_text(encoding="utf-8"))
COMMON_PASSWORDS = frozenset(POLICY["common_passwords"])


def validate_new_password(value: str) -> str:
    if value.lower() in COMMON_PASSWORDS or len(set(value)) == 1:
        raise PydanticCustomError("password_common", "Choose a less common password or generate one.")
    if not value.strip():
        raise PydanticCustomError("password_common", "Choose a less common password or generate one.")
    return value


NewPassword = Annotated[str, Field(min_length=POLICY["min_length"], max_length=POLICY["max_length"]), AfterValidator(validate_new_password)]
