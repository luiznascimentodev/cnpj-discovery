from rf_baseline import normalize_rf_email, normalize_rf_phone, public_normalized_values


class TestRfBaseline:
    def test_normalize_rf_email_classifies_public_provider(self):
        contact = normalize_rf_email("  Comercial@GMAIL.COM ")

        assert contact is not None
        assert contact.normalized_value == "comercial@gmail.com"
        assert contact.classification == "public_provider"

    def test_normalize_rf_email_classifies_corporate_domain(self):
        contact = normalize_rf_email("contato@empresa.com.br")

        assert contact is not None
        assert contact.classification == "corporate_domain"

    def test_normalize_rf_email_rejects_empty_and_invalid_values(self):
        assert normalize_rf_email(None) is None
        assert normalize_rf_email("not an email") is None

    def test_normalize_rf_phone_formats_valid_number(self):
        contact = normalize_rf_phone("(11)", " 9 8765-4321 ")

        assert contact is not None
        assert contact.value == "(11) 987654321"
        assert contact.normalized_value == "11987654321"
        assert contact.classification == "rf_public"

    def test_normalize_rf_phone_rejects_missing_or_invalid_values(self):
        assert normalize_rf_phone(None, "9876-5432") is None
        assert normalize_rf_phone("11", "") is None
        assert normalize_rf_phone("11", "123") is None

    def test_public_normalized_values_ignores_none(self):
        email = normalize_rf_email("contato@empresa.com.br")

        assert public_normalized_values(email, None) == {"contato@empresa.com.br"}
