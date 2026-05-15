import pytest
from modules.cnaes.service import build_cnae_catalog, classify_cnae, group_cnaes


class TestClassifyCnae:
    def test_tecnologia(self):
        assert classify_cnae(6201500) == "Tecnologia, Software e Dados"

    def test_tecnologia_63(self):
        assert classify_cnae(6311900) == "Tecnologia, Software e Dados"

    def test_alimentacao_56(self):
        assert classify_cnae(5611201) == "Alimentos e Bebidas"

    def test_alimentacao_10(self):
        assert classify_cnae(1091100) == "Alimentos e Bebidas"

    def test_comercio_varejista(self):
        assert classify_cnae(4711302) == "Comércio Varejista"

    def test_comercio_atacadista(self):
        assert classify_cnae(4611700) == "Comércio Atacadista"

    def test_construcao(self):
        assert classify_cnae(4120400) == "Construção Civil"

    def test_saude(self):
        assert classify_cnae(8630502) == "Saúde, Bem-estar e Assistência Social"

    def test_educacao(self):
        assert classify_cnae(8511200) == "Educação"

    def test_financeiro(self):
        assert classify_cnae(6422100) == "Serviços Financeiros e Seguros"

    def test_transporte(self):
        assert classify_cnae(4921301) == "Transporte, Correios e Logística"

    def test_industria(self):
        assert classify_cnae(2511000) == "Metalurgia, Máquinas e Equipamentos"

    def test_agropecuaria(self):
        assert classify_cnae(115600) == "Agropecuária, Pesca e Meio Rural"

    def test_servicos_profissionais(self):
        assert classify_cnae(6911701) == "Jurídico, Contábil e Gestão Empresarial"

    def test_imoveis(self):
        assert classify_cnae(6810201) == "Imóveis e Administração Patrimonial"

    def test_unknown_goes_to_outros(self):
        assert classify_cnae(9800000) == "Outros"

    def test_zero_goes_to_outros(self):
        assert classify_cnae(100) == "Outros"


class TestGroupCnaes:
    def _cnaes(self):
        return [
            {"codigo": 6201500, "descricao": "Dev de software"},
            {"codigo": 5611201, "descricao": "Restaurante"},
            {"codigo": 9800000, "descricao": "Desconhecido"},
        ]

    def test_returns_list(self):
        result = group_cnaes(self._cnaes())
        assert isinstance(result, list)

    def test_each_segment_has_label_and_cnaes(self):
        result = group_cnaes(self._cnaes())
        for seg in result:
            assert "label" in seg
            assert "cnaes" in seg
            assert isinstance(seg["cnaes"], list)

    def test_tecnologia_segment_present(self):
        result = group_cnaes(self._cnaes())
        labels = [s["label"] for s in result]
        assert "Tecnologia, Software e Dados" in labels

    def test_outros_segment_last(self):
        result = group_cnaes(self._cnaes())
        assert result[-1]["label"] == "Outros"

    def test_outros_contains_unknown_cnae(self):
        result = group_cnaes(self._cnaes())
        outros = next(s for s in result if s["label"] == "Outros")
        codes = [c["codigo"] for c in outros["cnaes"]]
        assert 9800000 in codes

    def test_empty_input(self):
        assert group_cnaes([]) == []

    def test_segments_without_matching_cnaes_omitted(self):
        result = group_cnaes([{"codigo": 6201500, "descricao": "Dev"}])
        labels = [s["label"] for s in result]
        assert "Alimentos e Bebidas" not in labels


class TestBuildCnaeCatalog:
    def test_returns_all_and_segments(self):
        cnaes = [
            {"codigo": 6201500, "descricao": "Dev"},
            {"codigo": 5611201, "descricao": "Restaurante"},
        ]

        result = build_cnae_catalog(cnaes)

        assert result["all"] == cnaes
        assert result["segments"][0]["label"] == "Alimentos e Bebidas"
