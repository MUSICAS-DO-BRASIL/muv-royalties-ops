"""Explicit account configuration; no operational defaults or import-time reads."""
from dataclasses import dataclass, field
import os
import re


class BankAccountConfigurationError(ValueError):
    """Account configuration is missing or invalid; never includes its value."""


@dataclass(frozen=True)
class BankAccountConfig:
    account_id: str = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.account_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", self.account_id):
            raise BankAccountConfigurationError("MUV_BANK_ACCOUNT_ID must be a nonempty account identifier")

    @classmethod
    def from_environment(cls):
        return cls(account_id=os.environ.get("MUV_BANK_ACCOUNT_ID", ""))
