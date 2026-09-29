from __future__ import annotations

import hashlib
import re

# Thu tu quan trong: the (16 so) truoc CCCD (12 so) va SDT de chuoi so dai khong bi cat do.
PII_PATTERNS: dict[str, str] = {
    "email": r"[\w\.+-]+@[\w\.-]+\.\w+",
    "credit_card": r"(?<!\d)\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}(?!\d)",
    "cccd": r"(?<!\d)\d{12}(?!\d)",
    "phone_vn": r"(?<!\d)(?:\+84|0)(?:[ .-]?\d){9}(?!\d)",
    # Ho chieu VN: 1 chu cai in hoa + 7 chu so (vd C1234567).
    "passport": r"\b[A-Z]\d{7}\b",
    # Dia chi: so nha + tu khoa duong/pho/phuong/quan (co dau hoac khong dau).
    "address_vn": r"(?i)\b(?:so\s+)?\d{1,4}[A-Za-z]?(?:/\d{1,4})?\s+(?:đường|duong|phố|pho|ngõ|ngo|hẻm|hem)\s+[^\d,.;\n]{2,40}",
}
_COMPILED = {name: re.compile(pattern) for name, pattern in PII_PATTERNS.items()}


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in _COMPILED.items():
        safe = pattern.sub(f"[REDACTED_{name.upper()}]", safe)
    return safe


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
