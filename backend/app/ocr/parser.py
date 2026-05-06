import re
from dataclasses import dataclass

FIELD_PATTERNS = {
    "model": [
        re.compile(r"\bMODEL\b\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{1,40})", re.IGNORECASE),
    ],
    "vin_or_bin": [
        re.compile(
            r"\b(?:VIN|BIN)(?:\s*/\s*BIN)?(?:\s+NUMBER|\s+NO\.?|\s*#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{3,40})",
            re.IGNORECASE,
        ),
        re.compile(r"\bSKU\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{3,40})", re.IGNORECASE),
    ],
    "serial_number": [
        re.compile(
            r"\b(?:SN|S/N|SERIAL(?:\s+NUMBER)?)(?:\s+NO\.?)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{2,40})",
            re.IGNORECASE,
        ),
        re.compile(r"\bS/?N\b\s+([A-Z0-9][A-Z0-9-]{4,40})", re.IGNORECASE),
    ],
}


@dataclass(frozen=True)
class ParsedLabel:
    model: str | None
    vin_or_bin: str | None
    serial_number: str | None


def normalize_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", "", value.strip().upper())
    cleaned = cleaned.strip(".,;:")
    return cleaned or None


def parse_label_text(text: str) -> ParsedLabel:
    normalized_text = text.replace("\r", "\n")
    values: dict[str, str | None] = {}
    for field, patterns in FIELD_PATTERNS.items():
        values[field] = None
        for pattern in patterns:
            match = pattern.search(normalized_text)
            if match:
                values[field] = normalize_value(match.group(1))
                break
    return ParsedLabel(
        model=values["model"],
        vin_or_bin=values["vin_or_bin"],
        serial_number=values["serial_number"],
    )
