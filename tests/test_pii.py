from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD 079204001234 da xac minh")
    assert "079204001234" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card_formats_as_card_not_cccd_or_phone() -> None:
    for card in ("4111 1111 1111 1111", "4111-1111-1111-1111", "4111111111111111"):
        out = scrub_text(f"card {card} please")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out
        assert "REDACTED_CCCD" not in out


def test_scrub_passport_and_vietnamese_address() -> None:
    out = scrub_text("Passport C1234567, giao toi 12 duong Nguyen Trai, Ha Noi")
    assert "C1234567" not in out
    assert "Nguyen Trai" not in out
    assert "REDACTED_PASSPORT" in out
    assert "REDACTED_ADDRESS_VN" in out


def test_scrub_keeps_non_pii_text() -> None:
    text = "Refunds are available within 7 days; P95 latency is 150 ms."
    assert scrub_text(text) == text
