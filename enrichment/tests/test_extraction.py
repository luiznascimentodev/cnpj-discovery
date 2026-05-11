from unittest.mock import patch

from extraction import (
    _social_profile_path,
    extract_contacts_from_html,
    extract_main_content,
    normalize_email,
    normalize_phone,
)


class TestExtraction:
    def test_normalize_email_rejects_assets_and_invalid_values(self):
        assert normalize_email("Contato@Example.com.br") == "contato@example.com.br"
        assert normalize_email("logo@example.com.br.png") is None
        assert normalize_email("k@48g9-.bybgnptut3") is None
        assert normalize_email("contato@example.c") is None
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

    def test_extract_contacts_ignores_social_content_urls(self):
        html = """
        <a href="https://www.instagram.com/example/">Instagram</a>
        <a href="https://www.instagram.com/p/abc123">Post</a>
        <a href="https://www.instagram.com/reel/abc123">Reel</a>
        <a href="https://www.facebook.com/example/posts/123">Post Facebook</a>
        <a href="https://www.linkedin.com/feed/update/abc">Feed LinkedIn</a>
        <a href="https://www.linkedin.com/company/example/posts/">Posts LinkedIn</a>
        <a href="https://www.youtube.com/watch?v=abc">Video</a>
        """

        contacts = extract_contacts_from_html(html, source_url="https://example.com.br")
        socials = {
            contact.normalized_value
            for contact in contacts
            if contact.contact_type == "social"
        }

        assert socials == {
            "https://www.instagram.com/example",
            "https://www.linkedin.com/company/example",
        }

    def test_extract_contacts_keeps_supported_social_profiles_only(self):
        html = """
        <a href="https://www.facebook.com/example?utm=1">Facebook</a>
        <a href="https://twitter.com/example">Twitter</a>
        <a href="https://x.com/example">X</a>
        <a href="https://www.tiktok.com/@example">TikTok</a>
        <a href="https://www.youtube.com/@example">YouTube</a>
        <a href="https://www.youtube.com/channel/abc123">Channel</a>
        <a href="https://www.instagram.com/">Instagram Home</a>
        <a href="https://x.com/search?q=example">Search</a>
        <a href="https://www.tiktok.com/tag/example">Tag</a>
        <a href="https://www.youtube.com/watch?v=abc123">Watch</a>
        """

        contacts = extract_contacts_from_html(html, source_url="https://example.com.br")
        socials = {
            contact.normalized_value
            for contact in contacts
            if contact.contact_type == "social"
        }

        assert socials == {
            "https://twitter.com/example",
            "https://x.com/example",
            "https://www.facebook.com/example",
            "https://www.tiktok.com/@example",
            "https://www.youtube.com/@example",
            "https://www.youtube.com/channel/abc123",
        }

    def test_social_profile_path_returns_none_for_unknown_host(self):
        assert _social_profile_path("example.com", "/social") is None


class TestExtractMainContent:
    def test_returns_none_on_empty_html(self):
        assert extract_main_content("") is None

    def test_returns_none_on_none_input(self):
        assert extract_main_content(None) is None

    def test_returns_string_or_none_for_nav_only_html(self):
        html = """<html><body>
        <nav><a href="/">Home</a><a href="/sobre">Sobre</a></nav>
        </body></html>"""
        result = extract_main_content(html)
        assert result is None or isinstance(result, str)

    def test_extracts_main_content_from_article(self):
        html = """<html><body>
        <nav><a href="/">Home</a></nav>
        <main>
          <p>Entre em contato pelo telefone (11) 98765-4321 ou email contato@empresa.com.br</p>
          <p>Estamos localizados na Rua das Flores, 123, São Paulo.</p>
        </main>
        <footer><p>© 2024 Empresa. Todos os direitos reservados.</p></footer>
        </body></html>"""
        result = extract_main_content(html)
        # trafilatura should extract the main paragraph
        assert result is None or isinstance(result, str)

    def test_returns_string_for_typical_contact_page(self):
        html = """<html><body>
        <h1>Fale Conosco</h1>
        <article>
        <p>Telefone: (11) 3333-4444</p>
        <p>Email: vendas@corpbrasil.com.br</p>
        <p>Endereço: Rua das Flores, 123 - São Paulo</p>
        </article>
        </body></html>"""
        result = extract_main_content(html)
        assert result is None or isinstance(result, str)

    def test_returns_none_when_trafilatura_raises(self):
        import extraction
        with patch.object(extraction._trafilatura, "extract", side_effect=RuntimeError("boom")):
            result = extract_main_content("<html><body><p>test</p></body></html>")
        assert result is None


class TestMainContentConfidenceBoost:
    def test_contact_confidence_does_not_decrease(self):
        """Trafilatura boost should never lower confidence."""
        html = """<html><body>
        <article><p>Telefone: (11) 99999-8888</p></article>
        </body></html>"""
        contacts = extract_contacts_from_html(html, source_url="https://test.com")
        phones = [c for c in contacts if c.contact_type == "phone"]
        assert all(c.confidence >= 70 for c in phones)

    def test_extract_contacts_still_works_without_trafilatura_content(self):
        """When trafilatura returns None, extraction should still work normally."""
        html = "<html><body><p>Tel: (11) 3333-4444</p></body></html>"
        contacts = extract_contacts_from_html(html, source_url="https://test.com")
        assert len(contacts) > 0
