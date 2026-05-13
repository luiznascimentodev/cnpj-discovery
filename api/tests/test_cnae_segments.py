import pytest
from services.cnae_segments import classify_cnae, group_cnaes


class TestClassifyCnae:
    def test_tecnologia(self):
        assert classify_cnae(6201500) == "Tecnologia e TI"

    def test_tecnologia_63(self):
        assert classify_cnae(6311900) == "Tecnologia e TI"

    def test_alimentacao_56(self):
        assert classify_cnae(5611201) == "Alimentação e Bebidas"

    def test_alimentacao_10(self):
        assert classify_cnae(1091100) == "Alimentação e Bebidas"

    def test_comercio_varejista(self):
        assert classify_cnae(4711302) == "Comércio Varejista"

    def test_comercio_atacadista(self):
        assert classify_cnae(4611700) == "Comércio Atacadista"

    def test_construcao(self):
        assert classify_cnae(4120400) == "Construção Civil"

    def test_saude(self):
        assert classify_cnae(8630502) == "Saúde e Bem-estar"

    def test_educacao(self):
        assert classify_cnae(8511200) == "Educação"

    def test_financeiro(self):
        assert classify_cnae(6422100) == "Serviços Financeiros"

    def test_transporte(self):
        assert classify_cnae(4921301) == "Transporte e Logística"

    def test_industria(self):
        assert classify_cnae(2511000) == "Indústria"

    def test_agropecuaria(self):
        assert classify_cnae(115600) == "Agropecuária"

    def test_servicos_profissionais(self):
        assert classify_cnae(6911701) == "Serviços Profissionais"

    def test_imoveis(self):
        assert classify_cnae(6810201) == "Imóveis"

    def test_unknown_goes_to_outros(self):
        assert classify_cnae(9999999) == "Outros"

    def test_zero_goes_to_outros(self):
        assert classify_cnae(100) == "Outros"


class TestGroupCnaes:
    def _cnaes(self):
        return [
            {"codigo": 6201500, "descricao": "Dev de software"},
            {"codigo": 5611201, "descricao": "Restaurante"},
            {"codigo": 9999999, "descricao": "Desconhecido"},
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
        assert "Tecnologia e TI" in labels

    def test_outros_segment_last(self):
        result = group_cnaes(self._cnaes())
        assert result[-1]["label"] == "Outros"

    def test_outros_contains_unknown_cnae(self):
        result = group_cnaes(self._cnaes())
        outros = next(s for s in result if s["label"] == "Outros")
        codes = [c["codigo"] for c in outros["cnaes"]]
        assert 9999999 in codes

    def test_empty_input(self):
        assert group_cnaes([]) == []

    def test_segments_without_matching_cnaes_omitted(self):
        result = group_cnaes([{"codigo": 6201500, "descricao": "Dev"}])
        labels = [s["label"] for s in result]
        assert "Alimentação e Bebidas" not in labels
