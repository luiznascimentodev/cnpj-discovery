_SQL_HAS_ENTITLEMENT = """
    SELECT EXISTS (
        SELECT 1
        FROM app_private.active_entitlements
        WHERE account_id = $1
          AND feature_key = $2
          AND (quota_monthly IS NULL OR used_this_period < quota_monthly)
    )
"""


async def has_entitlement(pool, account_id: str, feature_key: str) -> bool:
    async with pool.acquire() as conn:
        return bool(await conn.fetchval(_SQL_HAS_ENTITLEMENT, account_id, feature_key))

