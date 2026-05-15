"""Feature modules (Vertical Slice Architecture).

Each subpackage under `modules/` is a feature module (auth, prospecting,
pipeline, billing, enrichment, ...). Within a module the canonical layout is:

    modules/<feature>/
        router.py        # FastAPI APIRouter — HTTP endpoints
        service.py       # use cases / orchestration
        repository.py    # data access
        schemas.py       # Pydantic request/response
        dependencies.py  # DI specific to this module
        tests/

Layers not needed by a feature may be omitted. Modules may import from
`core/` freely. Modules MUST NOT import from each other directly — to expose
something cross-module, re-export it from the module's `__init__.py`.
Boundaries are enforced by `import-linter` (see `api/.importlinter`).
"""
