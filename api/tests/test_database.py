"""Testes para database.py — foca na lógica testável sem conexão real."""
from database import InstrumentedConnection, query_count


class TestInstrumentedConnectionInc:
    def test_inc_increments_context_var(self):
        query_count.set(0)
        conn = object.__new__(InstrumentedConnection)
        conn._inc()
        assert query_count.get() == 1

    def test_inc_accumulates(self):
        query_count.set(3)
        conn = object.__new__(InstrumentedConnection)
        conn._inc()
        conn._inc()
        assert query_count.get() == 5
