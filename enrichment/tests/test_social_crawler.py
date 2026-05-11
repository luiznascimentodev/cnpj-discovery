import pytest

from crawler.social_crawler import (
    SocialExtractResult,
    extract_contacts_from_facebook_html,
    extract_contacts_from_instagram_html,
)


class TestExtractFromInstagramHtml:
    def test_extracts_phone_from_meta_description(self):
        html = """<html><head>
        <meta name="description" content="Empresa XYZ | Tel: (11) 98765-4321 | contato@empresa.com.br">
        </head><body></body></html>"""
        result = extract_contacts_from_instagram_html(
            html, profile_url="https://instagram.com/empresa"
        )
        phones = [c for c in result.contacts if c.contact_type == "phone"]
        assert any("11987654321" == c.normalized_value for c in phones)

    def test_extracts_email_from_meta(self):
        html = """<html><head>
        <meta name="description" content="Empresa | contato@empresa.com.br | São Paulo">
        </head><body></body></html>"""
        result = extract_contacts_from_instagram_html(
            html, profile_url="https://instagram.com/empresa"
        )
        emails = [c for c in result.contacts if c.contact_type == "email"]
        assert any("contato@empresa.com.br" == c.normalized_value for c in emails)

    def test_extracts_website_from_json_ld(self):
        html = """<html><head></head><body>
        <script type="application/ld+json">
        {"@type": "Organization", "url": "https://empresa.com.br", "name": "Empresa XYZ"}
        </script></body></html>"""
        result = extract_contacts_from_instagram_html(
            html, profile_url="https://instagram.com/empresa"
        )
        websites = [c for c in result.contacts if c.contact_type == "website"]
        assert any("empresa.com.br" in c.normalized_value for c in websites)

    def test_returns_empty_on_blank_html(self):
        result = extract_contacts_from_instagram_html(
            "", profile_url="https://instagram.com/empresa"
        )
        assert result.contacts == []

    def test_confidence_is_high_for_tel_link_contacts(self):
        html = """<html><head></head><body>
        <a href="tel:+5511987654321">Ligar</a>
        </body></html>"""
        result = extract_contacts_from_instagram_html(
            html, profile_url="https://instagram.com/empresa"
        )
        phones = [c for c in result.contacts if c.contact_type == "phone"]
        if phones:
            assert phones[0].confidence >= 80

    def test_deduplicates_contacts(self):
        html = """<html><head>
        <meta name="description" content="Tel: (11) 98765-4321">
        </head><body>
        <a href="tel:+5511987654321">Ligar</a>
        </body></html>"""
        result = extract_contacts_from_instagram_html(
            html, profile_url="https://instagram.com/empresa"
        )
        phones = [c for c in result.contacts if c.contact_type == "phone"]
        values = [c.normalized_value for c in phones]
        assert len(values) == len(set(values))

    def test_social_links_filtered_out(self):
        html = """<html><head></head><body>
        <script type="application/ld+json">
        {"@type": "Organization", "url": "https://instagram.com/outroperil"}
        </script></body></html>"""
        result = extract_contacts_from_instagram_html(
            html, profile_url="https://instagram.com/empresa"
        )
        websites = [c for c in result.contacts if c.contact_type == "website"]
        assert not any("instagram.com" in c.normalized_value for c in websites)


class TestExtractFromFacebookHtml:
    def test_extracts_phone_from_visible_text(self):
        html = """<html><body>
        <div class="about">
          <span>Telefone: (21) 3333-4444</span>
        </div>
        </body></html>"""
        result = extract_contacts_from_facebook_html(
            html, profile_url="https://facebook.com/empresa"
        )
        phones = [c for c in result.contacts if c.contact_type == "phone"]
        assert any("2133334444" == c.normalized_value for c in phones)

    def test_returns_empty_on_blank_html(self):
        result = extract_contacts_from_facebook_html(
            "", profile_url="https://facebook.com/empresa"
        )
        assert result.contacts == []

    def test_extracts_website_from_json_ld(self):
        html = """<html><head></head><body>
        <script type="application/ld+json">
        {"@type": "LocalBusiness", "url": "https://empresa.com.br", "name": "Empresa"}
        </script></body></html>"""
        result = extract_contacts_from_facebook_html(
            html, profile_url="https://facebook.com/empresa"
        )
        websites = [c for c in result.contacts if c.contact_type == "website"]
        assert any("empresa.com.br" in c.normalized_value for c in websites)

    def test_profile_url_stored_in_result(self):
        result = extract_contacts_from_facebook_html(
            "<html><body></body></html>",
            profile_url="https://facebook.com/minha-empresa"
        )
        assert result.profile_url == "https://facebook.com/minha-empresa"

    def test_ignores_invalid_json_ld(self):
        html = """<html><head></head><body>
        <script type="application/ld+json">{ this is not valid json }</script>
        </body></html>"""
        result = extract_contacts_from_facebook_html(
            html, profile_url="https://facebook.com/empresa"
        )
        assert result.contacts == []

    def test_handles_json_ld_array(self):
        html = """<html><head></head><body>
        <script type="application/ld+json">
        [{"@type": "LocalBusiness", "url": "https://empresa.com.br"}]
        </script></body></html>"""
        result = extract_contacts_from_facebook_html(
            html, profile_url="https://facebook.com/empresa"
        )
        websites = [c for c in result.contacts if c.contact_type == "website"]
        assert any("empresa.com.br" in c.normalized_value for c in websites)

    def test_ignores_json_ld_non_dict_items_in_array(self):
        html = """<html><head></head><body>
        <script type="application/ld+json">
        ["just a string", {"@type": "LocalBusiness", "url": "https://empresa.com.br"}]
        </script></body></html>"""
        result = extract_contacts_from_facebook_html(
            html, profile_url="https://facebook.com/empresa"
        )
        websites = [c for c in result.contacts if c.contact_type == "website"]
        assert any("empresa.com.br" in c.normalized_value for c in websites)

    def test_ignores_unknown_schema_type(self):
        html = """<html><head></head><body>
        <script type="application/ld+json">
        {"@type": "Person", "url": "https://empresa.com.br"}
        </script></body></html>"""
        result = extract_contacts_from_facebook_html(
            html, profile_url="https://facebook.com/empresa"
        )
        websites = [c for c in result.contacts if c.contact_type == "website"]
        assert not any("empresa.com.br" in c.normalized_value for c in websites)

    def test_extracts_telephone_from_json_ld(self):
        html = """<html><head></head><body>
        <script type="application/ld+json">
        {"@type": "LocalBusiness", "telephone": "+55 21 3333-4444"}
        </script></body></html>"""
        result = extract_contacts_from_facebook_html(
            html, profile_url="https://facebook.com/empresa"
        )
        phones = [c for c in result.contacts if c.contact_type == "phone"]
        assert any("2133334444" == c.normalized_value for c in phones)

    def test_ignores_json_ld_non_list_non_dict(self):
        html = """<html><head></head><body>
        <script type="application/ld+json">42</script>
        </body></html>"""
        result = extract_contacts_from_facebook_html(
            html, profile_url="https://facebook.com/empresa"
        )
        assert result.contacts == []
