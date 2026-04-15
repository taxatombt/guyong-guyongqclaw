"""Secret Redactor - API Key and Credential Redaction

Based on Hermes redact.py (193 lines).
Provides pattern-based redaction for 31 API key prefix types.
Import-time snapshot: ENV var only checked at import time.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

_REDACT_ENABLED = os.getenv("HERMES_REDACT_SECRETS", "").lower() not in ("0", "false", "no", "off")

_PREFIX_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{10,}",
    r"ghp_[A-Za-z0-9]{10,}",
    r"github_pat_[A-Za-z0-9_]{10,}",
    r"gho_[A-Za-z0-9]{10,}",
    r"ghu_[A-Za-z0-9]{10,}",
    r"ghs_[A-Za-z0-9]{10,}",
    r"ghr_[A-Za-z0-9]{10,}",
    r"xox[baprs]-[A-Za-z0-9-]{10,}",
    r"AIza[A-Za-z0-9_-]{30,}",
    r"pplx-[A-Za-z0-9]{10,}",
    r"fal_[A-Za-z0-9_-]{10,}",
    r"fc-[A-Za-z0-9]{10,}",
    r"bb_live_[A-Za-z0-9_-]{10,}",
    r"gAAAA[A-Za-z0-9_=-]{20,}",
    r"AKIA[A-Z0-9]{16}",
    r"sk_live_[A-Za-z0-9]{10,}",
    r"sk_test_[A-Za-z0-9]{10,}",
    r"rk_live_[A-Za-z0-9]{10,}",
    r"SG\.[A-Za-z0-9_-]{10,}",
    r"hf_[A-Za-z0-9]{10,}",
    r"r8_[A-Za-z0-9]{10,}",
    r"npm_[A-Za-z0-9]{10,}",
    r"pypi-[A-Za-z0-9_-]{10,}",
    r"dop_v1_[A-Za-z0-9]{10,}",
    r"doo_v1_[A-Za-z0-9]{10,}",
    r"am_[A-Za-z0-9_-]{10,}",
    r"sk_[A-Za-z0-9_]{10,}",
    r"tvly-[A-Za-z0-9]{10,}",
    r"exa_[A-Za-z0-9]{10,}",
    r"gsk_[A-Za-z0-9]{10,}",
    r"syt_[A-Za-z0-9]{10,}",
    r"retaindb_[A-Za-z0-9]{10,}",
    r"hsk-[A-Za-z0-9]{10,}",
    r"mem0_[A-Za-z0-9]{10,}",
    r"brv_[A-Za-z0-9]{10,}",
]

_SECRET_ENV_RE = re.compile(
    r"([A-Z0-9_]{0,50}(?:API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)[A-Z0-9_]{0,50})"
    r"\s*=\s*(['\"]?)(\S+)\2"
)
_JSON_FIELD_RE = re.compile(
    r'"((?:api_?[Kk]ey|token|secret|password|access_token|refresh_token|auth_token|bearer|secret_value|raw_secret|secret_input|key_material))"'
    r'\s*:\s*"([^"]+)"',
    re.IGNORECASE
)
_AUTH_HEADER_RE = re.compile(r"(Authorization:\s*Bearer\s+)(\S+)", re.IGNORECASE)
_DB_CONNSTR_RE = re.compile(
    r"((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:]+:)([^@]+)(@)",
    re.IGNORECASE
)
_TELEGRAM_RE = re.compile(r"(bot)?(\d{8,}):([-A-Za-z0-9_]{30,})")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----[\s\S]*?-----END[A-Z ]*PRIVATE KEY-----")
_SIGNAL_PHONE_RE = re.compile(r"(\+[1-9]\d{6,14})(?![A-Za-z0-9])")

_PREFIX_RE = re.compile(r"(?<![A-Za-z0-9_-])(" + "|".join(_PREFIX_PATTERNS) + r")(?![A-Za-z0-9_-])")


def _mask_token(token: str) -> str:
    if len(token) < 18:
        return "***"
    return f"{token[:6]}...{token[-4:]}"


def redact_sensitive_text(text: str) -> str:
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return text
    if not _REDACT_ENABLED:
        return text

    text = _PREFIX_RE.sub(lambda m: _mask_token(m.group(1)), text)

    def _redact_env(m):
        return f"{m.group(1)}={m.group(2)}{_mask_token(m.group(3))}{m.group(2)}"
    text = _SECRET_ENV_RE.sub(_redact_env, text)

    def _redact_json(m):
        return f'{m.group(1)}: "{_mask_token(m.group(2))}"'
    text = _JSON_FIELD_RE.sub(_redact_json, text)

    text = _AUTH_HEADER_RE.sub(
        lambda m: m.group(1) + _mask_token(m.group(2)), text
    )

    def _redact_tg(m):
        return f"{m.group(1) or ''}{m.group(2)}:***"
    text = _TELEGRAM_RE.sub(_redact_tg, text)

    text = _PRIVATE_KEY_RE.sub("[REDACTED PRIVATE KEY]", text)
    text = _DB_CONNSTR_RE.sub(lambda m: f"{m.group(1)}***{m.group(3)}", text)

    def _redact_phone(m):
        p = m.group(1)
        if len(p) <= 8:
            return p[:2] + "****" + p[-2:]
        return p[:4] + "****" + p[-4:]
    text = _SIGNAL_PHONE_RE.sub(_redact_phone, text)

    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact_sensitive_text(super().format(record))


if __name__ == "__main__":
    tests = [
        "OPENAI_API_KEY=sk-1234567890abcdefghijklmnop",
        "GitHub: ghp_abcdefghijklmnopqrstuvwxyz123456",
        'Auth: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9',
    ]
    for t in tests:
        print(f"IN:  {t}")
        print(f"OUT: {redact_sensitive_text(t)}")
        print()
