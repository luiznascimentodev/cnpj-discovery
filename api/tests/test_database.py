"""Testes para database.py — foca na lógica testável sem conexão real."""
from core.db import InstrumentedConnection, query_count


class TestInstrumentedConnectionInc:
    def _make_conn(self):
        conn = object.__new__(InstrumentedConnection)
        conn._aborted = True
        conn._protocol = None
        return conn

    def test_inc_increments_context_var(self):
        query_count.set(0)
        conn = self._make_conn()
        conn._inc()
        assert query_count.get() == 1

    def test_inc_accumulates(self):
        query_count.set(3)
        conn = self._make_conn()
        conn._inc()
        conn._inc()
        assert query_count.get() == 5
