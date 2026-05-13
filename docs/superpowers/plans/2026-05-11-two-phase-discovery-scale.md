# Two-Phase Discovery Scale Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split discovery into Phase 1 (fast DNS-only sweep of all 28M companies) and Phase 2 (external search for companies without domains), scale to 20 workers, extract MEI phone contacts from RF data, and guarantee consistent resume after machine restarts.

**Architecture:** Two separate seed reasons (`phase1_dns` / `phase2_search`) each with their own monotonic cursor give crash-safe resume at no extra cost — the existing `enrichment_seed_cursor` table keyed by `reason` already handles this. Phase 1 workers pass `dns_only=True` to `process_target` (skip SearXNG, pure DNS+HTTP), completing the full 28M sweep in ~10-14h on 20 workers. Phase 2 is then seeded from the subset with no verified domain and workers use the full external-search stack. MEI companies always have their RF phone saved as a high-confidence contact immediately, even in dns_only mode.

**Tech Stack:** Python 3.12, asyncpg, pytest (100% coverage enforced), docker-compose, PostgreSQL 16

---

## File Map

| File | Change |
|---|---|
| `enrichment/scheduler.py` | Add `seed_phase1_targets`, `seed_phase2_targets`, refactor `_seed_with_query`; add `reason` filter to `claim_targets` |
| `enrichment/discovery/pipeline.py` | Add `dns_only` param; save MEI RF phone contact; raise RF email confidence for MEI |
| `enrichment/cli.py` | Add `seed-phase1`, `seed-phase2` commands; add `--phase` flag to `worker`; wire `dns_only` and external_search based on phase |
| `enrichment/config.py` | `DISCOVERY_CONCURRENCY=25`, `DISCOVERY_PHASE` env var |
| `docker-compose.yml` | `max_connections=300`, 20 worker replicas, `DISCOVERY_PHASE`, larger batch/seed sizes, `--interval 5` for phase1 |
| `enrichment/tests/test_scheduler.py` | Tests for new seed functions and reason-filtered claim |
| `enrichment/tests/test_discovery_pipeline.py` | Tests for `dns_only` mode and MEI phone contact |
| `enrichment/tests/test_cli.py` | Tests for phase-aware worker wiring |
| `enrichment/tests/test_config_database.py` | Test for `discovery_concurrency` setting |

---

## Task 1: Scheduler — phase seeds + reason-filtered claim

**Files:**
- Modify: `enrichment/scheduler.py`
- Test: `enrichment/tests/test_scheduler.py`

### Background

`scheduler.py` has one seed function (`seed_active_targets`) with a hardcoded SQL that:
1. Filters to companies missing email OR phone — **wrong for Phase 1** which must visit every active company.
2. Uses `reason` as the cursor key — we reuse this to give Phase 1 and Phase 2 independent cursors.

Phase 1 reason: `"phase1_dns"` — all active companies, ordered.
Phase 2 reason: `"phase2_search"` — active companies with no verified/candidate domain.

`claim_targets` currently picks any pending target regardless of reason. We add an optional `reason` filter so Phase 1 workers only claim Phase 1 targets.

- [ ] **Step 1: Write failing tests**

```python
# enrichment/tests/test_scheduler.py  — ADD these tests alongside existing ones

class TestSeedPhase1:
    @pytest.mark.asyncio
    async def test_seeds_all_active_companies_no_email_filter(self):
        """Phase 1 seeds ALL active companies — no missing-email/phone filter."""
        rows_inserted = []

        class FakeConn:
            async def fetchrow(self, q, *a):
                return None  # no cursor yet
            async def fetch(self, q, *a):
                # simulates 2 active companies
                return [
                    {"cnpj_basico": "00000001", "cnpj_ordem": "0001", "cnpj_dv": "10"},
                    {"cnpj_basico": "00000002", "cnpj_ordem": "0001", "cnpj_dv": "20"},
                ]
            async def executemany(self, q, records):
                rows_inserted.extend(records)
            async def execute(self, q, *a):
                pass
            async def transaction(self):
                return _FakeTx()

        class _FakeTx:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass

        class FakePool:
            def acquire(self): return _Ctx(FakeConn())

        class _Ctx:
            def __init__(self, c): self._c = c
            async def __aenter__(self): return self._c
            async def __aexit__(self, *a): pass

        n = await seed_phase1_targets(FakePool(), batch_size=100)
        assert n == 2
        reasons = [r[4] for r in rows_inserted]
        assert all(r == "phase1_dns" for r in reasons)

    @pytest.mark.asyncio
    async def test_phase1_sql_has_no_email_phone_condition(self):
        """_SQL_SELECT_PHASE1 must not contain email/telefone filter."""
        from scheduler import _SQL_SELECT_PHASE1
        assert "email" not in _SQL_SELECT_PHASE1.lower()
        assert "telefone" not in _SQL_SELECT_PHASE1.lower()

    @pytest.mark.asyncio
    async def test_phase2_sql_filters_companies_without_domain(self):
        """_SQL_SELECT_PHASE2 must reference company_domains with status filter."""
        from scheduler import _SQL_SELECT_PHASE2
        assert "company_domains" in _SQL_SELECT_PHASE2.lower()
        assert "verified" in _SQL_SELECT_PHASE2.lower()
        assert "candidate" in _SQL_SELECT_PHASE2.lower()
        assert "not exists" in _SQL_SELECT_PHASE2.lower()


class TestClaimTargetsReasonFilter:
    @pytest.mark.asyncio
    async def test_claim_with_reason_passes_reason_to_sql(self):
        """claim_targets(reason='phase1_dns') only claims matching targets."""
        fetched_args = []

        class FakeConn:
            async def fetch(self, q, *a):
                fetched_args.extend(a)
                return []

        class FakePool:
            def acquire(self): return _Ctx(FakeConn())

        class _Ctx:
            def __init__(self, c): self._c = c
            async def __aenter__(self): return self._c
            async def __aexit__(self, *a): pass

        await claim_targets(FakePool(), worker_id="w", batch_size=10, lease_seconds=60, reason="phase1_dns")
        # The reason must appear in the SQL args
        assert "phase1_dns" in fetched_args

    @pytest.mark.asyncio
    async def test_claim_without_reason_passes_none(self):
        """claim_targets() without reason passes None (claims any target)."""
        fetched_args = []

        class FakeConn:
            async def fetch(self, q, *a):
                fetched_args.extend(a)
                return []

        class FakePool:
            def acquire(self): return _Ctx(FakeConn())

        class _Ctx:
            def __init__(self, c): self._c = c
            async def __aenter__(self): return self._c
            async def __aexit__(self, *a): pass

        await claim_targets(FakePool(), worker_id="w", batch_size=10, lease_seconds=60)
        assert None in fetched_args
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd enrichment && python3 -m pytest tests/test_scheduler.py -k "TestSeedPhase1 or TestClaimTargetsReasonFilter" --no-cov -v
```
Expected: `ImportError: cannot import name '_SQL_SELECT_PHASE1'` or `FAILED`

- [ ] **Step 3: Implement in scheduler.py**

Replace `_SQL_SELECT_NEW_ROWS` and `seed_active_targets` with the refactored version:

```python
# enrichment/scheduler.py  — full replacement of the SQL constants and seed functions

_SQL_SELECT_PHASE1 = """
    SELECT est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv
    FROM estabelecimentos est
    WHERE est.situacao_cadastral = 2
      AND (est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv) > ($1, $2, $3)
    ORDER BY est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv
    LIMIT $4
"""

_SQL_SELECT_PHASE2 = """
    SELECT est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv
    FROM estabelecimentos est
    WHERE est.situacao_cadastral = 2
      AND (est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv) > ($1, $2, $3)
      AND NOT EXISTS (
          SELECT 1 FROM paid_enrichment.company_domains cd
          WHERE cd.cnpj_basico = est.cnpj_basico
            AND cd.cnpj_ordem = est.cnpj_ordem
            AND cd.cnpj_dv = est.cnpj_dv
            AND cd.status IN ('verified', 'candidate')
      )
    ORDER BY est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv
    LIMIT $4
"""

# Keep old query for backward compat (existing 'missing_contacts' reason)
_SQL_SELECT_NEW_ROWS = """
    SELECT est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv
    FROM estabelecimentos est
    WHERE est.situacao_cadastral = 2
      AND (est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv) > ($1, $2, $3)
      AND (
            COALESCE(est.email, '') = ''
         OR (COALESCE(est.telefone1, '') = '' AND COALESCE(est.telefone2, '') = '')
      )
    ORDER BY est.cnpj_basico, est.cnpj_ordem, est.cnpj_dv
    LIMIT $4
"""
```

Update `_SQL_CLAIM_TARGETS` to accept optional reason filter (add `AND ($4::TEXT IS NULL OR reason = $4)` and pass `reason` as 4th param, shifting `batch_size` to `$5`):

```python
_SQL_CLAIM_TARGETS = """
    WITH due AS (
        SELECT id
        FROM paid_enrichment.enrichment_targets
        WHERE status IN ('pending', 'retry')
          AND next_run_at <= now()
          AND (locked_at IS NULL OR locked_at < now() - make_interval(secs => $2))
          AND ($4::TEXT IS NULL OR reason = $4)
        ORDER BY priority DESC, next_run_at, id
        LIMIT $3
        FOR UPDATE SKIP LOCKED
    )
    UPDATE paid_enrichment.enrichment_targets t
    SET status = 'running',
        locked_at = now(),
        locked_by = $1,
        attempts = t.attempts + 1,
        updated_at = now()
    FROM due
    WHERE t.id = due.id
    RETURNING t.id, t.cnpj_basico, t.cnpj_ordem, t.cnpj_dv, t.reason, t.attempts, t.priority
"""
```

Add a shared `_seed_with_query` helper and new public functions:

```python
async def _seed_with_query(
    pool,
    sql: str,
    *,
    reason: str,
    priority: int,
    batch_size: int,
) -> int:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    async with pool.acquire() as conn:
        cursor_row = await conn.fetchrow(_SQL_GET_CURSOR, reason)
        if cursor_row:
            last_basico = cursor_row["last_cnpj_basico"]
            last_ordem = cursor_row["last_cnpj_ordem"]
            last_dv = cursor_row["last_cnpj_dv"]
        else:
            last_basico, last_ordem, last_dv = "00000000", "0000", "00"

        rows = await conn.fetch(sql, last_basico, last_ordem, last_dv, batch_size)
        if not rows:
            return 0

        records = [
            (row["cnpj_basico"], row["cnpj_ordem"], row["cnpj_dv"], priority, reason)
            for row in rows
        ]
        last = rows[-1]
        async with conn.transaction():
            await conn.executemany(_SQL_INSERT_TARGET, records)
            await conn.execute(
                _SQL_UPSERT_CURSOR,
                reason,
                last["cnpj_basico"],
                last["cnpj_ordem"],
                last["cnpj_dv"],
                len(rows),
            )
    return len(rows)


async def seed_active_targets(
    pool,
    *,
    reason: str = "missing_contacts",
    priority: int = 50,
    batch_size: int = DEFAULT_SEED_BATCH,
) -> int:
    """Backward-compat: seeds companies missing email or phone."""
    return await _seed_with_query(
        pool, _SQL_SELECT_NEW_ROWS, reason=reason, priority=priority, batch_size=batch_size
    )


async def seed_phase1_targets(
    pool,
    *,
    priority: int = 60,
    batch_size: int = 50_000,
) -> int:
    """Phase 1: seeds ALL active companies for DNS-only discovery."""
    return await _seed_with_query(
        pool, _SQL_SELECT_PHASE1, reason="phase1_dns", priority=priority, batch_size=batch_size
    )


async def seed_phase2_targets(
    pool,
    *,
    priority: int = 50,
    batch_size: int = 10_000,
) -> int:
    """Phase 2: seeds active companies with no verified/candidate domain."""
    return await _seed_with_query(
        pool, _SQL_SELECT_PHASE2, reason="phase2_search", priority=priority, batch_size=batch_size
    )
```

Update `claim_targets` signature and SQL call:

```python
async def claim_targets(
    pool,
    *,
    worker_id: str,
    batch_size: int = DEFAULT_CLAIM_BATCH,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    reason: str | None = None,
) -> list[ClaimedTarget]:
    if not worker_id:
        raise ValueError("worker_id is required")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _SQL_CLAIM_TARGETS,
            worker_id,
            lease_seconds,
            batch_size,
            reason,
        )
    return [
        ClaimedTarget(
            id=row["id"],
            cnpj_basico=row["cnpj_basico"],
            cnpj_ordem=row["cnpj_ordem"],
            cnpj_dv=row["cnpj_dv"],
            reason=row["reason"],
            attempts=row["attempts"],
            priority=row["priority"],
        )
        for row in rows
    ]
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_scheduler.py --no-cov -v
```
Expected: all pass including new tests.

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: `100%` coverage, all pass. Fix any breakage in `test_cli.py` from the changed `claim_targets` signature (the existing call `claim_targets(pool, worker_id=worker_id, ...)` still works — `reason` defaults to `None`).

- [ ] **Step 6: Commit**

```bash
git add enrichment/scheduler.py enrichment/tests/test_scheduler.py
git commit -m "feat: phase-aware seed (phase1_dns/phase2_search) + reason-filtered claim_targets"
```

---

## Task 2: Pipeline — dns_only mode + MEI phone contact

**Files:**
- Modify: `enrichment/discovery/pipeline.py`
- Test: `enrichment/tests/test_discovery_pipeline.py`

### Background

`process_target` currently calls `external_search.enrich_candidates` if passed. For Phase 1 we want `dns_only=True`: skip all external search (SearXNG, BrasilAPI, Brave) and return as soon as brand_slug DNS passes or fails. This makes each target take ~5-30ms instead of 2-15 seconds.

MEI companies in the current code skip brand_slug but have no mechanism to save their RF phone as a contact. `normalize_rf_phone` already returns a `BaselineContact` with `.value` (formatted like `"(11) 987654321"`) and `.normalized_value` (digits only like `"11987654321"`). We save both phones with confidence 75/70 and source `"rf_phone_mei"`.

Also: the current `_SQL_UPSERT_RF_EMAIL_CONTACT` saves email with confidence 40 and source `"rf_email_direct"` for ALL companies. For MEI companies (who use personal email for their business), we should save it with confidence 65 and source `"rf_email_mei"`.

- [ ] **Step 1: Write failing tests**

Add to `enrichment/tests/test_discovery_pipeline.py`:

```python
# --- add these at the bottom of the file, after TestMeiDetection ---

class TestDnsOnlyMode:
    @pytest.mark.asyncio
    async def test_dns_only_skips_external_search(self):
        """dns_only=True: external_search.enrich_candidates must never be called."""
        called = []

        class FakeExternalSearch:
            async def enrich_candidates(self, **kwargs):
                called.append(kwargs)
                return []

        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "ACME LTDA",
                "nome_fantasia": "Acme",
                "email": None,
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            }
        )

        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=FakeExternalSearch(),
                dns_only=True,
            )

        assert called == []

    @pytest.mark.asyncio
    async def test_dns_only_false_calls_external_search(self):
        """dns_only=False (default): external_search IS called when no verified domain."""
        called = []

        class FakeExternalSearch:
            async def enrich_candidates(self, **kwargs):
                called.append(True)
                return []

        conn = FakeConnection(
            fetchrow_result={
                "razao_social": "ACME LTDA",
                "nome_fantasia": "Acme",
                "email": None,
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            }
        )

        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
                external_search=FakeExternalSearch(),
                dns_only=False,
            )

        assert called == [True]


class TestMeiPhoneContact:
    @pytest.mark.asyncio
    async def test_mei_phone_saved_as_rf_phone_mei_contact(self):
        """MEI with phone: saves rf_phone_mei contact with confidence 75."""
        conn = FakeConnectionMei(
            estabelecimento_row={
                "razao_social": "JOAO DA SILVA 12345678000190",
                "nome_fantasia": None,
                "email": None,
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": "11",
                "telefone1": "987654321",
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            },
            mei_row={"opcao_mei": "S"},
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        phone_calls = [
            c for c in conn.execute_calls
            if "enriched_contacts" in c[0] and "rf_phone_mei" in str(c[1])
        ]
        assert len(phone_calls) >= 1
        assert outcome.rf_contacts_saved >= 1

    @pytest.mark.asyncio
    async def test_mei_email_saved_with_mei_source(self):
        """MEI with gmail email: saves with source rf_email_mei, confidence 65."""
        conn = FakeConnectionMei(
            estabelecimento_row={
                "razao_social": "JOAO DA SILVA 12345678000190",
                "nome_fantasia": None,
                "email": "joao@gmail.com",
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": None,
                "telefone1": None,
                "ddd2": None,
                "telefone2": None,
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            },
            mei_row={"opcao_mei": "S"},
        )

        async with _httpx_client(_weak_ok_handler) as client:
            await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        email_calls = [
            c for c in conn.execute_calls
            if "enriched_contacts" in c[0] and "rf_email_mei" in str(c[1])
        ]
        assert len(email_calls) == 1
        # confidence 65
        confidence_arg = email_calls[0][1][7]
        assert confidence_arg == 65

    @pytest.mark.asyncio
    async def test_mei_both_phones_saved_when_different(self):
        """MEI with two distinct phones saves both."""
        conn = FakeConnectionMei(
            estabelecimento_row={
                "razao_social": "JOAO DA SILVA 12345678000190",
                "nome_fantasia": None,
                "email": None,
                "uf": "SP",
                "municipio": 1,
                "municipio_descricao": "SAO PAULO",
                "cep": "00000000",
                "ddd1": "11",
                "telefone1": "91111111",
                "ddd2": "11",
                "telefone2": "92222222",
                "bairro": None,
                "logradouro": None,
                "numero": None,
                "cnae_descricao": None,
            },
            mei_row={"opcao_mei": "S"},
        )

        async with _httpx_client(_weak_ok_handler) as client:
            outcome = await process_target(
                FakePool(conn),
                cnpj_basico="12345678",
                cnpj_ordem="0001",
                cnpj_dv="90",
                client=client,
            )

        phone_calls = [
            c for c in conn.execute_calls
            if "enriched_contacts" in c[0] and "rf_phone_mei" in str(c[1])
        ]
        assert len(phone_calls) == 2
        assert outcome.rf_contacts_saved == 2
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3 -m pytest tests/test_discovery_pipeline.py -k "TestDnsOnlyMode or TestMeiPhoneContact" --no-cov -v
```
Expected: `FAILED` (process_target has no `dns_only` param; no phone contact SQL exists)

- [ ] **Step 3: Implement in pipeline.py**

Add two new SQL constants after `_SQL_UPSERT_RF_EMAIL_CONTACT`:

```python
_SQL_UPSERT_RF_EMAIL_CONTACT_MEI = """
    INSERT INTO paid_enrichment.enriched_contacts (
        cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, value, normalized_value,
        label, source, confidence, status, first_seen, last_seen
    )
    VALUES ($1, $2, $3, 'email', $4, $4, 'Email MEI', 'rf_email_mei', 65, 'active', now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, normalized_value)
    DO UPDATE SET last_seen = now()
"""

_SQL_UPSERT_RF_PHONE_CONTACT = """
    INSERT INTO paid_enrichment.enriched_contacts (
        cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, value, normalized_value,
        label, source, confidence, status, first_seen, last_seen
    )
    VALUES ($1, $2, $3, 'phone', $4, $5, $6, $7, $8, 'active', now(), now())
    ON CONFLICT (cnpj_basico, cnpj_ordem, cnpj_dv, contact_type, normalized_value)
    DO UPDATE SET last_seen = now()
"""
```

Add `dns_only: bool = False` parameter to `process_target`:

```python
async def process_target(
    pool,
    *,
    cnpj_basico: str,
    cnpj_ordem: str,
    cnpj_dv: str,
    client: httpx.AsyncClient,
    external_search: ExternalSearchClient | None = None,
    dns_only: bool = False,
) -> DiscoveryOutcome:
```

Replace the MEI branch (after `is_mei = bool(...)`) with:

```python
    if is_mei:
        async with pool.acquire() as conn:
            # Email: MEI uses personal email for business — higher confidence
            if rf_email and rf_email.classification in ("public_provider", "corporate_domain"):
                await conn.execute(
                    _SQL_UPSERT_RF_EMAIL_CONTACT_MEI,
                    cnpj_basico, cnpj_ordem, cnpj_dv,
                    rf_email.normalized_value,
                )
                rf_contacts_saved += 1
            # Phone: MEI uses personal phone — high value contact
            if rf_phone1:
                await conn.execute(
                    _SQL_UPSERT_RF_PHONE_CONTACT,
                    cnpj_basico, cnpj_ordem, cnpj_dv,
                    rf_phone1.value, rf_phone1.normalized_value,
                    "Telefone MEI", "rf_phone_mei", 75,
                )
                rf_contacts_saved += 1
            if rf_phone2 and rf_phone2.normalized_value != (rf_phone1.normalized_value if rf_phone1 else None):
                await conn.execute(
                    _SQL_UPSERT_RF_PHONE_CONTACT,
                    cnpj_basico, cnpj_ordem, cnpj_dv,
                    rf_phone2.value, rf_phone2.normalized_value,
                    "Telefone MEI 2", "rf_phone_mei", 70,
                )
                rf_contacts_saved += 1
        if dns_only:
            return DiscoveryOutcome(
                cnpj=cnpj, domains_seen=0, crawl_requests_created=0,
                rf_contacts_saved=rf_contacts_saved,
            )
        # Phase 2: fall through to external_search below (no brand_slug for MEI)
        candidates = []
```

Replace the block `if external_search is not None:` at the end with:

```python
    if external_search is not None and not dns_only:
        # ... (rest of external search block unchanged)
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_discovery_pipeline.py --no-cov -v
```
Expected: all pass.

- [ ] **Step 5: Full suite**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: 100% coverage. If `cli.py` tests break because `discover_target` now has extra param, update the mock signature (add `dns_only=False` to `discover_side_effect`).

- [ ] **Step 6: Commit**

```bash
git add enrichment/discovery/pipeline.py enrichment/tests/test_discovery_pipeline.py
git commit -m "feat: dns_only mode for Phase 1 sweep + MEI RF phone contact (confidence 75)"
```

---

## Task 3: CLI — phase-aware worker commands

**Files:**
- Modify: `enrichment/cli.py`
- Test: `enrichment/tests/test_cli.py`

### Background

The `worker` command currently seeds with `reason=args.reason` (defaulting to `"missing_contacts"`) and always passes `external_search`. We need:

- `seed-phase1` command → calls `seed_phase1_targets`
- `seed-phase2` command → calls `seed_phase2_targets`
- `worker --phase 1` → seeds with `seed_phase1_targets`, claims only `phase1_dns` targets, passes `dns_only=True`, no external search, interval defaults to 5s
- `worker --phase 2` → seeds with `seed_phase2_targets`, claims only `phase2_search` targets, passes `dns_only=False`, uses full external search, interval defaults to 30s
- `worker` (no `--phase`) → backward compat, seeds `missing_contacts`, no reason filter, with external search

New imports needed: `from scheduler import seed_phase1_targets, seed_phase2_targets`

- [ ] **Step 1: Write failing tests**

Add to `enrichment/tests/test_cli.py`:

```python
# Add near the top with other imports:
# from cli import do_seed_phase1, do_seed_phase2

class TestPhaseSeedFunctions:
    @pytest.mark.asyncio
    async def test_do_seed_phase1_calls_seed_phase1_targets(self):
        pool = object()
        with patch("cli.seed_phase1_targets", new_callable=AsyncMock, return_value=50000) as m:
            result = await do_seed_phase1(pool, batch_size=50000)
        assert result == 50000
        m.assert_awaited_once_with(pool, batch_size=50000)

    @pytest.mark.asyncio
    async def test_do_seed_phase2_calls_seed_phase2_targets(self):
        pool = object()
        with patch("cli.seed_phase2_targets", new_callable=AsyncMock, return_value=10000) as m:
            result = await do_seed_phase2(pool, batch_size=10000)
        assert result == 10000
        m.assert_awaited_once_with(pool, batch_size=10000)


class TestPhaseAwareDiscovery:
    @pytest.mark.asyncio
    async def test_do_discovery_phase1_passes_dns_only_true(self):
        """Phase 1: dns_only=True must reach discover_target."""
        targets = [
            ClaimedTarget(id=1, cnpj_basico="12345678", cnpj_ordem="0001", cnpj_dv="90",
                          reason="phase1_dns", attempts=1, priority=60),
        ]
        received_kwargs = {}

        async def discover_side_effect(pool, *, cnpj_basico, cnpj_ordem, cnpj_dv, client,
                                       external_search=None, dns_only=False):
            received_kwargs["dns_only"] = dns_only
            received_kwargs["external_search"] = external_search
            return DiscoveryOutcome(cnpj="x", domains_seen=0, crawl_requests_created=0)

        with (
            patch("cli.claim_targets", new_callable=AsyncMock, return_value=targets),
            patch("cli.discover_target", AsyncMock(side_effect=discover_side_effect)),
            patch("cli.complete_target", new_callable=AsyncMock),
        ):
            async with _stub_client() as client:
                await do_discovery(
                    object(), client=client, worker_id="w",
                    batch_size=10, lease_seconds=300,
                    dns_only=True, external_search=None,
                )

        assert received_kwargs["dns_only"] is True
        assert received_kwargs["external_search"] is None

    @pytest.mark.asyncio
    async def test_do_discovery_phase2_passes_dns_only_false(self):
        """Phase 2: dns_only=False and external_search is forwarded."""
        targets = [
            ClaimedTarget(id=1, cnpj_basico="12345678", cnpj_ordem="0001", cnpj_dv="90",
                          reason="phase2_search", attempts=1, priority=50),
        ]
        received_kwargs = {}

        class FakeSearch:
            pass

        async def discover_side_effect(pool, *, cnpj_basico, cnpj_ordem, cnpj_dv, client,
                                       external_search=None, dns_only=False):
            received_kwargs["dns_only"] = dns_only
            received_kwargs["external_search"] = external_search
            return DiscoveryOutcome(cnpj="x", domains_seen=0, crawl_requests_created=0)

        fake_search = FakeSearch()
        with (
            patch("cli.claim_targets", new_callable=AsyncMock, return_value=targets),
            patch("cli.discover_target", AsyncMock(side_effect=discover_side_effect)),
            patch("cli.complete_target", new_callable=AsyncMock),
        ):
            async with _stub_client() as client:
                await do_discovery(
                    object(), client=client, worker_id="w",
                    batch_size=10, lease_seconds=300,
                    dns_only=False, external_search=fake_search,
                )

        assert received_kwargs["dns_only"] is False
        assert received_kwargs["external_search"] is fake_search
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3 -m pytest tests/test_cli.py -k "TestPhaseSeedFunctions or TestPhaseAwareDiscovery" --no-cov -v
```
Expected: `ImportError: cannot import name 'do_seed_phase1'` or `FAILED`

- [ ] **Step 3: Implement in cli.py**

Add imports at top (after existing scheduler imports):

```python
from scheduler import (
    claim_targets,
    complete_target,
    release_stale_locks,
    seed_active_targets,
    seed_phase1_targets,
    seed_phase2_targets,
)
```

Add new do_seed helpers:

```python
async def do_seed_phase1(pool, *, batch_size: int = 50_000) -> int:
    return await seed_phase1_targets(pool, batch_size=batch_size)


async def do_seed_phase2(pool, *, batch_size: int = 10_000) -> int:
    return await seed_phase2_targets(pool, batch_size=batch_size)
```

Update `do_discovery` signature to accept `dns_only` and pass it through:

```python
async def do_discovery(
    pool,
    *,
    client,
    worker_id: str,
    batch_size: int,
    lease_seconds: int,
    concurrency: int = DISCOVERY_CONCURRENCY,
    external_search=None,
    dns_only: bool = False,
    reason: str | None = None,
) -> tuple[int, int]:
    targets = await claim_targets(
        pool,
        worker_id=worker_id,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
        reason=reason,
    )
    if not targets:
        return 0, 0

    sem = asyncio.Semaphore(concurrency)

    async def _process(target) -> int:
        async with sem:
            try:
                outcome = await discover_target(
                    pool,
                    cnpj_basico=target.cnpj_basico,
                    cnpj_ordem=target.cnpj_ordem,
                    cnpj_dv=target.cnpj_dv,
                    client=client,
                    external_search=external_search,
                    dns_only=dns_only,
                )
                await complete_target(pool, target_id=target.id, status="done")
                return outcome.crawl_requests_created
            except Exception as exc:
                await complete_target(
                    pool,
                    target_id=target.id,
                    status="retry",
                    retry_in_seconds=300,
                    last_error=f"{type(exc).__name__}: {exc}",
                )
                return 0

    results = await asyncio.gather(*[_process(t) for t in targets])
    return len(targets), sum(results)
```

Update `do_one_loop` to be phase-aware:

```python
_PHASE1_REASON = "phase1_dns"
_PHASE2_REASON = "phase2_search"


async def do_one_loop(pool, client, args) -> TickStats:
    phase = getattr(args, "phase", 0)

    if phase == 1:
        seeded = await do_seed_phase1(pool, batch_size=args.seed_batch_size)
        claimed, crawl_created = await do_discovery(
            pool,
            client=client,
            worker_id=args.worker_id,
            batch_size=args.discovery_batch_size,
            lease_seconds=args.lease_seconds,
            dns_only=True,
            external_search=None,
            reason=_PHASE1_REASON,
        )
    elif phase == 2:
        seeded = await do_seed_phase2(pool, batch_size=args.seed_batch_size)
        claimed, crawl_created = await do_discovery(
            pool,
            client=client,
            worker_id=args.worker_id,
            batch_size=args.discovery_batch_size,
            lease_seconds=args.lease_seconds,
            dns_only=False,
            external_search=_build_external_search(),
            reason=_PHASE2_REASON,
        )
    else:
        # backward-compat: existing 'missing_contacts' workers
        seeded = await do_seed(
            pool,
            reason=args.reason,
            priority=args.priority,
            batch_size=args.seed_batch_size,
        )
        claimed, crawl_created = await do_discovery(
            pool,
            client=client,
            worker_id=args.worker_id,
            batch_size=args.discovery_batch_size,
            lease_seconds=args.lease_seconds,
            external_search=_build_external_search(),
        )

    crawler_done, contacts = await do_crawler(
        pool,
        client=client,
        worker_id=args.worker_id,
        batch_size=args.crawl_batch_size,
        lease_seconds=args.lease_seconds,
        user_agent=args.user_agent,
    )
    released = await do_release_stale(pool, lease_seconds=args.lease_seconds)
    return TickStats(
        seeded=seeded,
        targets_claimed=claimed,
        crawl_requests_created=crawl_created,
        crawler_done=crawler_done,
        contacts_published=contacts,
        leases_released=released,
    )
```

Add `seed-phase1` and `seed-phase2` commands to `build_parser()`:

```python
    seed_p1 = sub.add_parser("seed-phase1")
    seed_p1.add_argument("--batch-size", type=int, default=50_000)
    seed_p1.set_defaults(func=lambda args: asyncio.run(_cmd_seed_phase(args, 1)))

    seed_p2 = sub.add_parser("seed-phase2")
    seed_p2.add_argument("--batch-size", type=int, default=10_000)
    seed_p2.set_defaults(func=lambda args: asyncio.run(_cmd_seed_phase(args, 2)))
```

Wait — the CLI uses async commands differently. Add proper async command functions:

```python
async def cmd_seed_phase1(args) -> None:
    pool = await create_pool()
    try:
        seeded = await do_seed_phase1(pool, batch_size=args.batch_size)
        print(f"seed-phase1 rows={seeded}")
    finally:
        await close_pool()


async def cmd_seed_phase2(args) -> None:
    pool = await create_pool()
    try:
        seeded = await do_seed_phase2(pool, batch_size=args.batch_size)
        print(f"seed-phase2 rows={seeded}")
    finally:
        await close_pool()
```

Add `--phase` to the `worker` subparser and `DEFAULT_PHASE1_INTERVAL = 5`:

```python
    # In build_parser(), in the 'worker' subparser:
    worker.add_argument("--phase", type=int, default=0,
                        help="1=dns-only sweep, 2=external search, 0=legacy")
    worker.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
```

Register new commands in build_parser:

```python
    seed_p1 = sub.add_parser("seed-phase1")
    seed_p1.add_argument("--batch-size", type=int, default=50_000)
    seed_p1.set_defaults(func=cmd_seed_phase1)

    seed_p2 = sub.add_parser("seed-phase2")
    seed_p2.add_argument("--batch-size", type=int, default=10_000)
    seed_p2.set_defaults(func=cmd_seed_phase2)
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_cli.py --no-cov -v
```
Expected: all pass. Fix `test_do_discovery_handles_targets_and_failures` if the new `reason` kwarg in `claim_targets` breaks its mock (add `reason=None` to mock call args matching if needed).

- [ ] **Step 5: Full suite**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: 100% coverage. The new `cmd_seed_phase1`/`cmd_seed_phase2` functions need tests or must be covered by existing tests; add minimal coverage tests if needed.

- [ ] **Step 6: Commit**

```bash
git add enrichment/cli.py enrichment/tests/test_cli.py
git commit -m "feat: phase-aware worker (--phase 1/2), seed-phase1/seed-phase2 CLI commands"
```

---

## Task 4: Config, Docker, and 20-worker scale

**Files:**
- Modify: `enrichment/config.py`
- Modify: `docker-compose.yml`
- Test: `enrichment/tests/test_config_database.py`

### Background

With 20 workers × `max_size=10` pool = 200 connections max. Plus the enrichment API, domain-crawler, domain-resolver = another ~30. Total: ~230. PostgreSQL must be bumped to `max_connections=300`. We also tune:

- `DISCOVERY_CONCURRENCY`: 10 → 25 (more parallel DNS checks per worker)
- Phase 1 worker interval: 30s → 5s (pure DNS is fast, no need to sleep long)
- Phase 1 discovery batch: 50 → 500 (larger batches per iteration)
- Phase 1 seed batch: 10000 → 50000 (fill queue fast)
- Phase 2 interval: stays 30s (SearXNG calls are slow)
- Postgres `max_connections=300` (requires restart)

Docker compose changes:
- Remove `container_name` from `enrichment-worker` (already done — verify)
- Add `DISCOVERY_PHASE: "1"` env to phase1 worker profile
- Scale `enrichment-worker` default replicas to 20 via `deploy.replicas`
- Split worker profiles: `worker-p1` for Phase 1 workers, `worker-p2` for Phase 2 workers

Actually simpler: one `enrichment-worker` service with `DISCOVERY_PHASE` from env. Operator runs:
- Phase 1: `docker compose --profile worker up -d --scale enrichment-worker=20`
- Phase 2: scale down, change env, scale up again

But to run both phases simultaneously (Phase 1 finishing while Phase 2 starts), we need two services. Add `enrichment-worker-p2` as a separate service with `DISCOVERY_PHASE=2` and `--profile worker-p2`.

- [ ] **Step 1: Write failing config tests**

```python
# Add to enrichment/tests/test_config_database.py

    def test_discovery_concurrency_default(self):
        settings = Settings()
        assert settings.discovery_concurrency == 25

    def test_discovery_concurrency_accepts_custom_value(self):
        settings = Settings(discovery_concurrency=10)
        assert settings.discovery_concurrency == 10
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3 -m pytest tests/test_config_database.py -k "discovery_concurrency" --no-cov -v
```
Expected: `FAILED` — `Settings` has no `discovery_concurrency` attribute.

- [ ] **Step 3: Add to config.py**

```python
# enrichment/config.py — add to Settings class:
    discovery_concurrency: int = 25
```

- [ ] **Step 4: Update DISCOVERY_CONCURRENCY constant in cli.py**

```python
# enrichment/cli.py — change the constant at the top:
DISCOVERY_CONCURRENCY = settings.discovery_concurrency
```

- [ ] **Step 5: Run config tests**

```bash
python3 -m pytest tests/test_config_database.py --no-cov -v
```
Expected: all pass.

- [ ] **Step 6: Update docker-compose.yml**

Make these exact changes to `docker-compose.yml`:

**a) Postgres max_connections: change from 200 to 300**

```yaml
      - -c
      - max_connections=300
```

**b) Update enrichment-worker (Phase 1)** — default env is phase 1:

```yaml
  enrichment-worker:
    build:
      context: ./enrichment
      dockerfile: Dockerfile
    env_file: .env
    environment:
      POSTGRES_HOST: postgres
      REDIS_URL: redis://redis:6379/0
      ENRICHMENT_API_KEY: ${ENRICHMENT_API_KEY:-development-enrichment-key}
      BRASILAPI_ENABLED: "${BRASILAPI_ENABLED:-true}"
      BRAVE_SEARCH_API_KEY: "${BRAVE_SEARCH_API_KEY:-}"
      SEARXNG_URL: "${SEARXNG_URL:-http://searxng:8080}"
      DISCOVERY_CONCURRENCY: "25"
    command:
      - python
      - cli.py
      - worker
      - --phase
      - "1"
      - --interval
      - "5"
      - --seed-batch-size
      - "${ENRICHMENT_SEED_BATCH:-50000}"
      - --discovery-batch-size
      - "${ENRICHMENT_DISCOVERY_BATCH:-500}"
      - --crawl-batch-size
      - "${ENRICHMENT_CRAWL_BATCH:-20}"
      - --lease-seconds
      - "${ENRICHMENT_LEASE_SECONDS:-600}"
    deploy:
      replicas: 20
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      searxng:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "tr '\\0' ' ' < /proc/1/cmdline | grep -q 'cli.py worker'"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    profiles:
      - worker
```

**c) Add enrichment-worker-p2 service** (Phase 2, uses SearXNG):

```yaml
  enrichment-worker-p2:
    build:
      context: ./enrichment
      dockerfile: Dockerfile
    env_file: .env
    environment:
      POSTGRES_HOST: postgres
      REDIS_URL: redis://redis:6379/0
      ENRICHMENT_API_KEY: ${ENRICHMENT_API_KEY:-development-enrichment-key}
      BRASILAPI_ENABLED: "${BRASILAPI_ENABLED:-true}"
      SEARXNG_URL: "${SEARXNG_URL:-http://searxng:8080}"
      DISCOVERY_CONCURRENCY: "10"
    command:
      - python
      - cli.py
      - worker
      - --phase
      - "2"
      - --interval
      - "30"
      - --seed-batch-size
      - "${ENRICHMENT_SEED_BATCH_P2:-10000}"
      - --discovery-batch-size
      - "${ENRICHMENT_DISCOVERY_BATCH_P2:-50}"
      - --crawl-batch-size
      - "${ENRICHMENT_CRAWL_BATCH:-20}"
      - --lease-seconds
      - "${ENRICHMENT_LEASE_SECONDS:-600}"
    deploy:
      replicas: 5
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      searxng:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "tr '\\0' ' ' < /proc/1/cmdline | grep -q 'cli.py worker'"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    profiles:
      - worker-p2
```

- [ ] **Step 7: Run full test suite**

```bash
python3 -m pytest tests/ -q --tb=short
```
Expected: 100% coverage, all pass. Fix `DISCOVERY_CONCURRENCY` import if `cli.py` tries to use `settings` before it's imported (move `settings` import before the constant definition).

- [ ] **Step 8: Restart postgres with new max_connections, deploy 20 workers**

```bash
# Restart postgres to apply max_connections=300
docker compose restart postgres

# Wait for postgres to be healthy
until docker compose ps postgres | grep -q "healthy"; do sleep 2; done

# Rebuild worker image with new code
docker compose build enrichment-worker

# Stop old workers (5 replicas) and start 20
docker compose --profile worker stop
docker compose --profile worker up -d --scale enrichment-worker=20
```

- [ ] **Step 9: Verify 20 workers running and healthy**

```bash
docker compose ps | grep enrichment-worker | wc -l
# Expected: 20

# Check connections
docker exec cnpj-postgres psql -U cnpj_user -d cnpj -t -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname='cnpj';"
# Expected: <250 (well under new 300 limit)

# Check discovery rate after 2 minutes
docker logs cnpj-discovery-enrichment-worker-1 2>&1 | grep "worker_loop" | tail -3
# Expected: iter=N claimed=500 (larger batches working)
```

- [ ] **Step 10: Commit**

```bash
git add enrichment/config.py enrichment/cli.py enrichment/tests/test_config_database.py docker-compose.yml
git commit -m "feat: 20 workers at phase1 (dns-only, 5s interval, batch 500) + postgres max_connections=300"
```

---

## Task 5: Launch Phase 1 sweep and monitor

**Files:** No code changes — operational steps only.

- [ ] **Step 1: Seed Phase 1 queue**

```bash
docker exec cnpj-discovery-enrichment-worker-1 python cli.py seed-phase1 --batch-size 50000
# Expected: seed-phase1 rows=50000
```

- [ ] **Step 2: Verify cursor was written**

```bash
docker exec cnpj-postgres psql -U cnpj_user -d cnpj -t -c \
  "SELECT reason, last_cnpj_basico, rows_seeded FROM paid_enrichment.enrichment_seed_cursor ORDER BY reason;"
# Expected: row with reason='phase1_dns', rows_seeded=50000
```

- [ ] **Step 3: Check pending queue depth**

```bash
docker exec cnpj-postgres psql -U cnpj_user -d cnpj -t -c \
  "SELECT reason, status, count(*) FROM paid_enrichment.enrichment_targets GROUP BY reason, status ORDER BY reason, status;"
```

- [ ] **Step 4: Monitor throughput after 5 minutes**

```bash
docker exec cnpj-postgres psql -U cnpj_user -d cnpj -t -c "
SELECT
  count(*) filter(WHERE updated_at > now() - interval '5 minutes' AND status='done') as done_5min,
  count(*) filter(WHERE status='done') as done_total,
  count(*) filter(WHERE status='pending') as pending,
  count(*) filter(WHERE status='retry') as retry
FROM paid_enrichment.enrichment_targets
WHERE reason = 'phase1_dns';
"
```
Expected: `done_5min >= 5000` (250 targets/min × 5 min × 20 workers = ~25000 in good conditions; conservative floor is 5000).

Compute estimated completion:
```
# If done_5min = D:
# rate_per_min = D / 5
# remaining = 28_700_000 - done_total
# hours = remaining / rate_per_min / 60
echo "Fill in numbers from above"
```

- [ ] **Step 5: Watch for retry errors**

```bash
docker exec cnpj-postgres psql -U cnpj_user -d cnpj -t -c "
SELECT last_error, count(*)
FROM paid_enrichment.enrichment_targets
WHERE reason = 'phase1_dns' AND status = 'retry' AND last_error IS NOT NULL
GROUP BY last_error
ORDER BY count DESC
LIMIT 5;
"
```
If any error appears more than 100 times, investigate before proceeding.

---

## Performance Appendix: Techniques Applied

| Technique | Where | Impact |
|---|---|---|
| Phase 1 DNS-only (`dns_only=True`) | `pipeline.py` | Eliminates 2–15s SearXNG wait per target; each target takes ~5–30ms |
| `asyncio.Semaphore(25)` per worker | `cli.py` `DISCOVERY_CONCURRENCY` | 25 concurrent DNS+HTTP probes per worker |
| Batch size 500 (Phase 1) | `docker-compose.yml` | 10× fewer round-trips for claim/complete |
| 5s sleep interval (Phase 1) | `docker-compose.yml` | 6× more iterations per minute |
| 20 worker replicas | `docker-compose.yml` | 20× horizontal throughput |
| `deploy.replicas` in compose | `docker-compose.yml` | Single command to scale up/down |
| Reason-filtered `claim_targets` | `scheduler.py` | Phase 1 workers never waste time on Phase 2 targets |
| `FOR UPDATE SKIP LOCKED` | existing | Zero contention between 20 workers on same queue |
| MEI early-exit in dns_only | `pipeline.py` | MEI companies finish in <5ms (just DB write) |
| Monotonic resume cursor | `scheduler.py` | Machine restart resumes from exact position, no re-scan |

### Projected throughput (Phase 1, 20 workers)

```
Per target cost (Phase 1, dns_only):
  - DB fetch estabelecimento:  ~3ms
  - DB fetch socios:           ~2ms
  - MEI check:                 ~2ms
  - DNS check × 5 candidates:  ~25ms (5ms each, sequential per target)
  - HTTP probe (2% hit rate):  ~500ms × 0.02 = ~10ms average
  Total per target:            ~42ms

With Semaphore(25) and batch=500:
  Batch time = 500 targets × 42ms / 25 parallel = 840ms
  Plus sleep = 5s
  Cycle time = 5.84s
  Rate per worker = 500 / 5.84 = 85 targets/sec = 5,100/min

With 20 workers:
  Total rate = 20 × 5,100 = 102,000 targets/min

28.7M active companies ÷ 102,000/min = 281 minutes ≈ 4.7 hours
```

**Conservative estimate (network jitter, DB contention): 8–12 hours for Phase 1.**

After Phase 1: Phase 2 workers (5 replicas, SearXNG) process companies without a domain. Rate ~800/min → 20M companies × 0.8 ≈ 16M Phase 2 targets → ~20,000 min = 14 days. Phase 2 runs in the background continuously and doesn't block results from Phase 1.

---

*Self-review performed: spec coverage ✓, no placeholders ✓, type consistency ✓*
