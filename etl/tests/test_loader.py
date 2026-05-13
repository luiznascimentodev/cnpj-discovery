"""
Testes para etl/loader.py.

Requerem PostgreSQL rodando (docker compose up postgres -d).
Usam uma tabela temporária para não sujar o schema principal.
"""
import pytest
import psycopg2
import polars as pl

from config import Settings
from loader import (
    get_connection,
    disable_triggers,
    enable_triggers,
    bulk_copy,
    upsert,
)


@pytest.fixture(scope="module")
def test_settings():
    return Settings(postgres_password="changeme")


@pytest.fixture(scope="module")
def db_conn(test_settings):
    """Conexão direta ao PostgreSQL para setup/teardown de fixtures."""
    conn = psycopg2.connect(test_settings.dsn)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="module", autouse=True)
def test_table(db_conn):
    """Cria tabela temporária para os testes e remove no final."""
    with db_conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _test_loader (
                id      TEXT PRIMARY KEY,
                name    TEXT,
                value   NUMERIC
            )
        """)
    yield
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS _test_loader")


@pytest.fixture(autouse=True)
def clean_table(db_conn):
    """Limpa a tabela antes de cada teste."""
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM _test_loader")
    yield


def make_df(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema={"id": pl.Utf8, "name": pl.Utf8, "value": pl.Utf8})


# ─── get_connection ───────────────────────────────────────────────────────────

class TestGetConnection:
    def test_yields_connection(self):
        with get_connection() as conn:
            assert conn is not None
            assert not conn.closed

    def test_connection_closed_after_context(self):
        with get_connection() as conn:
            c = conn
        assert c.closed


# ─── disable/enable_triggers ─────────────────────────────────────────────────

class TestTriggers:
    def test_disable_and_enable_triggers(self, db_conn):
        # Deve executar sem erro
        with get_connection() as conn:
            disable_triggers(conn, "_test_loader")
            enable_triggers(conn, "_test_loader")


# ─── bulk_copy ────────────────────────────────────────────────────────────────

class TestBulkCopy:
    def test_inserts_rows(self, db_conn):
        df = make_df([
            {"id": "001", "name": "Empresa A", "value": "1000"},
            {"id": "002", "name": "Empresa B", "value": "2000"},
        ])
        with get_connection() as conn:
            n = bulk_copy(conn, df, "_test_loader", ["id", "name", "value"], commit=True)
        assert n == 2

        with db_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM _test_loader")
            assert cur.fetchone()[0] == 2

    def test_returns_row_count(self, db_conn):
        df = make_df([{"id": "003", "name": "C", "value": "300"}])
        with get_connection() as conn:
            n = bulk_copy(conn, df, "_test_loader", ["id", "name", "value"], commit=True)
        assert n == 1

    def test_handles_null_values(self, db_conn):
        df = pl.DataFrame(
            [{"id": "004", "name": None, "value": None}],
            schema={"id": pl.Utf8, "name": pl.Utf8, "value": pl.Utf8}
        )
        with get_connection() as conn:
            n = bulk_copy(conn, df, "_test_loader", ["id", "name", "value"], commit=True)
        assert n == 1

        with db_conn.cursor() as cur:
            cur.execute("SELECT name, value FROM _test_loader WHERE id = '004'")
            row = cur.fetchone()
            assert row[0] is None
            assert row[1] is None

    def test_ignores_extra_columns_not_in_schema(self, db_conn):
        # DataFrame tem coluna 'extra' que não existe na tabela
        df = pl.DataFrame(
            [{"id": "005", "name": "E", "value": "500", "extra": "ignored"}],
            schema={"id": pl.Utf8, "name": pl.Utf8, "value": pl.Utf8, "extra": pl.Utf8}
        )
        with get_connection() as conn:
            # Passa apenas colunas válidas
            n = bulk_copy(conn, df, "_test_loader", ["id", "name", "value"], commit=True)
        assert n == 1

    def test_empty_string_stored_as_empty_not_quoted_pair(self, db_conn):
        df = pl.DataFrame(
            [{"id": "007", "name": "", "value": "1"}],
            schema={"id": pl.Utf8, "name": pl.Utf8, "value": pl.Utf8}
        )
        with get_connection() as conn:
            n = bulk_copy(conn, df, "_test_loader", ["id", "name", "value"], commit=True)
        assert n == 1

        with db_conn.cursor() as cur:
            cur.execute("SELECT name FROM _test_loader WHERE id = '007'")
            row = cur.fetchone()
            assert row[0] == ""  # deve ser string vazia, não '""'

    def test_handles_trailing_backslash_before_column_separator(self, db_conn):
        df = make_df([
            {"id": "006", "name": "RONALD RIBEIRO CARDOSO\\", "value": "0.0"},
        ])
        with get_connection() as conn:
            n = bulk_copy(conn, df, "_test_loader", ["id", "name", "value"], commit=True)
        assert n == 1

        with db_conn.cursor() as cur:
            cur.execute("SELECT name, value FROM _test_loader WHERE id = '006'")
            row = cur.fetchone()
            assert row[0] == "RONALD RIBEIRO CARDOSO\\"
            assert row[1] == 0


# ─── upsert ───────────────────────────────────────────────────────────────────

class TestUpsert:
    def test_inserts_new_rows(self, db_conn):
        df = make_df([{"id": "010", "name": "New A", "value": "100"}])
        with get_connection() as conn:
            n = upsert(conn, df, "_test_loader", ["id", "name", "value"], ["id"])
        assert n == 1

        with db_conn.cursor() as cur:
            cur.execute("SELECT name FROM _test_loader WHERE id = '010'")
            assert cur.fetchone()[0] == "New A"

    def test_updates_existing_rows(self, db_conn):
        # Inserir primeiro
        with db_conn.cursor() as cur:
            cur.execute("INSERT INTO _test_loader VALUES ('020', 'Old Name', 999)")

        df = make_df([{"id": "020", "name": "Updated Name", "value": "999"}])
        with get_connection() as conn:
            upsert(conn, df, "_test_loader", ["id", "name", "value"], ["id"])

        with db_conn.cursor() as cur:
            cur.execute("SELECT name FROM _test_loader WHERE id = '020'")
            assert cur.fetchone()[0] == "Updated Name"

    def test_empty_conflict_columns_falls_back_to_bulk_copy(self, db_conn):
        """Tabelas append-only (socios) não têm conflict_columns."""
        df = make_df([{"id": "030", "name": "Append", "value": "300"}])
        with get_connection() as conn:
            n = upsert(conn, df, "_test_loader", ["id", "name", "value"], [])
        assert n == 1

    def test_all_pk_columns_uses_do_nothing(self, db_conn):
        """Quando todas as colunas são PK, usa ON CONFLICT DO NOTHING."""
        # Neste caso, conflict_columns == available_cols (sem update_cols)
        df = make_df([{"id": "040", "name": "Solo PK", "value": "400"}])
        with get_connection() as conn:
            upsert(conn, df, "_test_loader", ["id"], ["id"])
        # Segunda inserção não deve falhar
        with get_connection() as conn:
            n = upsert(conn, df, "_test_loader", ["id"], ["id"])
        assert n == 1
