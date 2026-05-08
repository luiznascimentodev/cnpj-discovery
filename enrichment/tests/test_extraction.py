from extraction import extract_contacts_from_html, normalize_email, normalize_phone


class TestExtraction:
    def test_normalize_email_rejects_assets_and_invalid_values(self):
        assert normalize_email("Contato@Example.com.br") == "contato@example.com.br"
        assert normalize_email("logo@example.com.br.png") is None
        assert normalize_email("invalid") is None

    def test_normalize_phone_accepts_br_numbers_and_rejects_noise(self):
        assert normalize_phone("+55 (11) 98765-4321") == "11987654321"
        assert normalize_phone("0011 8765-4321") == "1187654321"
        assert normalize_phone("1111111111") is None
        assert normalize_phone("123") is None

    def test_extract_contacts_from_html_collects_common_contact_channels(self):
        html = """
        <html>
          <body>
            <a href="mailto:Comercial@Example.com.br">Email</a>
            <a href="tel:+5511987654321">Telefone</a>
            <a href="https://api.whatsapp.com/send?phone=5511912345678">WhatsApp</a>
            <a href="/contato">Contato</a>
            <a href="https://www.instagram.com/example/">Instagram</a>
            Fale com suporte@example.com.br ou (11) 3456-7890.
            <script>ignored@example.com.br</script>
          </body>
        </html>
        """

        contacts = extract_contacts_from_html(html, source_url="https://example.com.br/contato")
        by_key = {(contact.contact_type, contact.normalized_value): contact for contact in contacts}

        assert ("email", "comercial@example.com.br") in by_key
        assert by_key[("email", "comercial@example.com.br")].extractor == "mailto"
        assert ("email", "suporte@example.com.br") in by_key
        assert ("phone", "11987654321") in by_key
        assert ("whatsapp", "11912345678") in by_key
        assert ("social", "https://www.instagram.com/example") in by_key
        assert "ignored@example.com.br" not in {contact.normalized_value for contact in contacts}

    def test_extract_contacts_prefers_highest_confidence_duplicate(self):
        html = """
        <a href="mailto:vendas@example.com.br">Vendas</a>
        vendas@example.com.br
        """

        contacts = extract_contacts_from_html(html, source_url="https://example.com.br")
        contact = [item for item in contacts if item.normalized_value == "vendas@example.com.br"][0]

        assert contact.extractor == "mailto"
        assert contact.confidence == 88

    def test_extract_contacts_ignores_invalid_tel_links(self):
        contacts = extract_contacts_from_html(
            '<a href="tel:123">Telefone</a>',
            source_url="https://example.com.br",
        )

        assert contacts == []
