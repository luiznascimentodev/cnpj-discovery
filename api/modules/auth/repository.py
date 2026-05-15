from __future__ import annotations

from datetime import datetime
from uuid import UUID

from modules.auth.schemas import UserRecord


class UserRepository:
    def __init__(self, pool):
        self._pool = pool

    async def insert(self, *, email: str, password_hash: str, name: str) -> UserRecord:
        row = await self._fetchrow(
            """
            INSERT INTO users (email, password_hash, name)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            email,
            password_hash,
            name,
        )
        return UserRecord(**dict(row))

    async def get_by_email(self, email: str) -> UserRecord | None:
        row = await self._fetchrow(
            "SELECT * FROM users WHERE email = $1 AND deleted_at IS NULL",
            email,
        )
        return UserRecord(**dict(row)) if row else None

    async def get_by_id(self, user_id: UUID) -> UserRecord | None:
        row = await self._fetchrow(
            "SELECT * FROM users WHERE id = $1 AND deleted_at IS NULL",
            user_id,
        )
        return UserRecord(**dict(row)) if row else None

    async def mark_verified(self, user_id: UUID, verified_at: datetime) -> None:
        await self._execute(
            "UPDATE users SET email_verified_at = $2, updated_at = now() WHERE id = $1",
            user_id,
            verified_at,
        )

    async def update_password(self, user_id: UUID, password_hash: str) -> None:
        await self._execute(
            "UPDATE users SET password_hash = $2, updated_at = now() WHERE id = $1",
            user_id,
            password_hash,
        )

    async def _fetchrow(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _execute(self, query: str, *args) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(query, *args)


class TokenRepository:
    def __init__(self, pool, table: str):
        self._pool = pool
        self._table = table

    async def insert(self, *, token_hash: bytes, user_id: UUID, expires_at: datetime) -> None:
        await self._execute(
            f"""
            INSERT INTO {self._table} (token_hash, user_id, expires_at)
            VALUES ($1, $2, $3)
            """,
            token_hash,
            user_id,
            expires_at,
        )

    async def get_valid(self, token_hash: bytes):
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(
                f"""
                SELECT * FROM {self._table}
                WHERE token_hash = $1 AND used_at IS NULL AND expires_at > now()
                """,
                token_hash,
            )

    async def mark_used(self, token_hash: bytes) -> None:
        await self._execute(
            f"UPDATE {self._table} SET used_at = now() WHERE token_hash = $1",
            token_hash,
        )

    async def _execute(self, query: str, *args) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(query, *args)


class EmailVerificationRepo(TokenRepository):
    def __init__(self, pool):
        super().__init__(pool, "email_verifications")


class PasswordResetRepo(TokenRepository):
    def __init__(self, pool):
        super().__init__(pool, "password_resets")


class AuthEventRepo:
    def __init__(self, pool):
        self._pool = pool

    async def record(
        self,
        *,
        event: str,
        user_id: UUID | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO auth_events (user_id, event, ip, user_agent)
                VALUES ($1, $2, $3, $4)
                """,
                user_id,
                event,
                ip,
                user_agent,
            )
