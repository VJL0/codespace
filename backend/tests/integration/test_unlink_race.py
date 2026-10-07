"""Concurrent changes to one user's sign-in methods."""

from __future__ import annotations

import asyncio

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.auth.models import OAuthAccount, OAuthProvider
from app.modules.auth.service import unlink_oauth_account
from app.modules.users.models import User


async def test_concurrent_unlinks_leave_one_sign_in_method(engine: AsyncEngine) -> None:
    # Two requests each unlink one of a user's two accounts. Each alone is
    # allowed; together they'd leave none, unless the second waits for the
    # first. Real concurrency takes separate connections and committed data,
    # so this test runs outside the per-test rollback and cleans up after.
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        user = User(full_name="Two Methods")
        setup.add_all(
            [
                user,
                OAuthAccount(
                    user=user, provider=OAuthProvider.GOOGLE, provider_user_id="race-1"
                ),
                OAuthAccount(
                    user=user, provider=OAuthProvider.GITHUB, provider_user_id="race-2"
                ),
            ]
        )
        await setup.commit()

    async def unlink(provider: OAuthProvider) -> bool:
        async with AsyncSession(engine) as db:
            try:
                await unlink_oauth_account(db, user.id, provider)
            except HTTPException as exc:
                assert exc.detail["code"] == "last_method"
                return False

            await db.commit()

            return True

    try:
        results = await asyncio.gather(
            unlink(OAuthProvider.GOOGLE), unlink(OAuthProvider.GITHUB)
        )

        assert sorted(results) == [False, True]
        async with AsyncSession(engine) as db:
            remaining = await db.scalar(
                select(func.count())
                .select_from(OAuthAccount)
                .where(OAuthAccount.user_id == user.id)
            )
        assert remaining == 1
    finally:
        async with AsyncSession(engine) as db:
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()
