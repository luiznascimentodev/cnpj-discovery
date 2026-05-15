"""Cross-cutting concerns shared across modules.

Modules under `core/` contain infrastructure used by every feature module:
database pool, cache client, config, security primitives, middleware, etc.
Anything inside `core/` MUST NOT import from `modules/` — only the reverse.
"""
