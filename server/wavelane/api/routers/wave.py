"""The Wave endpoints: an endless personalised stream and its controls."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from ...models import Track
from ...schemas.common import Message
from ...schemas.wave import (
    TasteProfileOut,
    WaveBatch,
    WaveFeedbackRequest,
    WaveFeedbackResult,
    WaveReason,
    WaveSettingsOut,
    WaveSettingsUpdate,
    WaveTrack,
)
from ...services.catalog import serialize_tracks
from ...services.security import create_stream_token
from ...utils import now_utc
from ...wave import WaveEngine
from ...wave.feedback import profile_snapshot
from ..deps import AppSettings, CurrentUser, DbSession

router = APIRouter(prefix="/wave", tags=["wave"])


@router.get("/settings", response_model=WaveSettingsOut, summary="Current wave settings")
async def get_wave_settings(user: CurrentUser, db: DbSession) -> WaveSettingsOut:
    settings = await WaveEngine(db).get_settings(user.id)
    return WaveSettingsOut.model_validate(settings)


@router.put(
    "/settings",
    response_model=WaveSettingsOut,
    summary="Change mood, character or language",
)
async def update_wave_settings(
    payload: WaveSettingsUpdate, user: CurrentUser, db: DbSession
) -> WaveSettingsOut:
    engine = WaveEngine(db)
    settings = await engine.update_settings(
        user.id,
        mood=payload.mood,
        character=payload.character,
        language=payload.language,
        diversity=payload.diversity,
    )
    return WaveSettingsOut.model_validate(settings)


@router.get("/next", response_model=WaveBatch, summary="Next tracks in the wave")
async def next_tracks(
    user: CurrentUser,
    db: DbSession,
    app_settings: AppSettings,
    count: Annotated[int, Query(ge=1, le=20, description="How many tracks to return")] = 5,
    reset: Annotated[bool, Query(description="Start a fresh wave session")] = False,
) -> WaveBatch:
    engine = WaveEngine(db)
    picks = await engine.next_batch(user.id, count=count, reset=reset)
    wave_session = await engine.ensure_session(user.id)
    settings = await engine.get_settings(user.id)

    if not picks:
        # An empty catalogue is the usual cause; say so rather than 500.
        return WaveBatch(
            session_id=wave_session.id,
            settings=WaveSettingsOut.model_validate(settings),
            items=[],
            generated_at=now_utc(),
        )

    serialized = await serialize_tracks(
        db, [pick.track for pick in picks], user.id, include_features=True
    )
    by_id = {item.id: item for item in serialized}

    items: list[WaveTrack] = []
    for pick in picks:
        track_out = by_id.get(pick.track.id)
        if track_out is None:  # pragma: no cover
            continue
        token = create_stream_token(user.id, pick.track.id, app_settings)
        items.append(
            WaveTrack(
                track=track_out,
                position=pick.position,
                score=pick.score,
                reason=WaveReason.model_validate(pick.reason),
                stream_url=f"{app_settings.api_prefix}/stream/{pick.track.id}?token={token}",
            )
        )

    return WaveBatch(
        session_id=wave_session.id,
        settings=WaveSettingsOut.model_validate(settings),
        items=items,
        generated_at=now_utc(),
    )


@router.post(
    "/feedback",
    response_model=WaveFeedbackResult,
    summary="Like, dislike, skip or complete the current track",
)
async def wave_feedback(
    payload: WaveFeedbackRequest, user: CurrentUser, db: DbSession
) -> WaveFeedbackResult:
    track = await db.get(Track, payload.track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="track not found")

    engine = WaveEngine(db)
    result = await engine.feedback(
        user.id, track, payload.kind, completion=payload.completion
    )
    return WaveFeedbackResult.model_validate(result)


@router.post("/reset", response_model=Message, summary="Start a new wave session")
async def reset_wave(user: CurrentUser, db: DbSession) -> Message:
    await WaveEngine(db).ensure_session(user.id, reset=True)
    return Message(detail="a new wave session was started")


@router.get(
    "/profile",
    response_model=TasteProfileOut,
    summary="What the wave currently believes about your taste",
)
async def taste_profile(user: CurrentUser, db: DbSession) -> TasteProfileOut:
    profile = await WaveEngine(db).profile(user.id)
    return TasteProfileOut.model_validate(profile_snapshot(profile))
