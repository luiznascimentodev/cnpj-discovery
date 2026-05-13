import pytest
from fastapi import HTTPException

from dependencies import _parse_int_list, export_filters_dependency, prospecting_filters_dependency


class TestParseIntList:
    def test_parse_int_list_returns_none_for_empty_values(self):
        assert _parse_int_list(None, []) is None

    def test_parse_int_list_parses_comma_values(self):
        assert _parse_int_list(["1,2"], ["3"]) == [1, 2, 3]

    def test_parse_int_list_rejects_invalid_values(self):
        with pytest.raises(HTTPException) as exc:
            _parse_int_list(["abc"])
        assert exc.value.status_code == 422


class TestFilterDependencies:
    @pytest.mark.asyncio
    async def test_prospecting_dependency_builds_filters(self):
        filters = await prospecting_filters_dependency(
            uf="SP",
            cnaes=["6201500,6311900"],
            porte=["3"],
            limit=50,
        )
        assert filters.uf == "SP"
        assert filters.cnaes == [6201500, 6311900]
        assert filters.porte == [3]
        assert filters.limit == 50

    @pytest.mark.asyncio
    async def test_export_dependency_ignores_limit_and_cursor_contract(self):
        filters = await export_filters_dependency(uf="RJ")
        assert filters.uf == "RJ"
        assert filters.limit == 100
        assert filters.cursor_cnpj_basico is None
        assert filters.cursor_cnpj_ordem is None
