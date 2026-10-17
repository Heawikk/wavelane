"""The Wave engine: an endless, personalised and reactive stream of tracks.

How a batch is produced
-----------------------
1. **Context** — long-term taste profile, the live session vector, affinities,
   what was played recently, what is banned.
2. **Candidate pool** — several bounded SQL queries pulling from different
   angles (favourites, affine artists, affine genres, catalogue hits, never
   played, random). Mixing sources is what keeps the stream from collapsing
   into one cluster, and each query stays cheap and indexable.
3. **Ranking** — every candidate scored in numpy on the sonic vector plus
   affinities, popularity and penalties (see scoring.py).
4. **Selection** — greedy diversity pass with artist/album cooldowns and an
   exploration share, so a batch does not sound like one album.

For a catalogue in the millions, step 2 is where an approximate-nearest-
neighbour index (pgvector, FAISS) would replace the SQL pools; everything
downstream stays as it is.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Album,
    ArtistReaction,
    ArtistRole,
    AudioFeature,
    FeedbackKind,
    PlayEvent,
    TasteProfile,
    Track,
    TrackArtist,
    TrackGenre,
    TrackReaction,
    TrackStatus,
    WaveCharacter,
    WaveLanguage,
    WaveMood,
    WaveQueueItem,
    WaveSession,
    WaveSettings,
)
from ..utils import clamp, now_utc
from .features import FEATURE_COUNT, coerce_vector
from .feedback import apply_feedback, get_or_create_profile
from .scoring import (
    DEFAULT_WEIGHTS,
    Candidate,
    ScoredCandidate,
    ScoringWeights,
    UserContext,
    apply_mood_gate,
    explain,
    popularity_score,
    rank_candidates,
    select_diverse,
)

logger = logging.getLogger(__name__)

# Tracks hard-excluded from the pool because they just played.
RECENT_EXCLUDE_LIMIT = 30
# Longer memory, used for penalties and the freshness bonus.
RECENT_HISTORY_LIMIT = 400
# Upper bound on candidates scored per batch. Scoring is numpy and cheap; the
# SQL that fills the pool is what we are protecting here.
POOL_LIMIT = 900


@dataclass(slots=True)
class WavePick:
    """One track handed to the client, with the reason it was chosen."""

    track: Track
    score: float
    reason: dict[str, Any]
    position: int


class WaveEngine:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Settings and sessions
    # ------------------------------------------------------------------

    async def get_settings(self, user_id: uuid.UUID) -> WaveSettings:
        settings = await self.session.get(WaveSettings, user_id)
        if settings is None:
            settings = WaveSettings(user_id=user_id, updated_at=now_utc())
            self.session.add(settings)
            await self.session.flush()
        return settings

    async def update_settings(
        self,
        user_id: uuid.UUID,
        *,
        mood: WaveMood | None = None,
        character: WaveCharacter | None = None,
        language: WaveLanguage | None = None,
        diversity: float | None = None,
    ) -> WaveSettings:
        settings = await self.get_settings(user_id)
        if mood is not None:
            settings.mood = mood
        if character is not None:
            settings.character = character
        if language is not None:
            settings.language = language
        if diversity is not None:
            settings.diversity = clamp(diversity)
        settings.updated_at = now_utc()

        # The settings define the stream, so changing them starts a new one.
        await self._deactivate_sessions(user_id)
        await self.session.flush()
        return settings

    async def ensure_session(
        self, user_id: uuid.UUID, *, reset: bool = False
    ) -> WaveSession:
        if reset:
            await self._deactivate_sessions(user_id)

        existing = await self.session.scalar(
            select(WaveSession)
            .where(WaveSession.user_id == user_id, WaveSession.is_active.is_(True))
            .order_by(WaveSession.last_active_at.desc())
            .limit(1)
        )
        if existing is not None:
            return existing

        settings = await self.get_settings(user_id)
        wave_session = WaveSession(
            user_id=user_id,
            is_active=True,
            settings_snapshot={
                "mood": str(settings.mood),
                "character": str(settings.character),
                "language": str(settings.language),
                "diversity": settings.diversity,
            },
            session_vector=[],
            recent_artist_ids=[],
            banned_artist_ids=[],
            created_at=now_utc(),
            last_active_at=now_utc(),
        )
        self.session.add(wave_session)
        await self.session.flush()
        return wave_session

    async def _deactivate_sessions(self, user_id: uuid.UUID) -> None:
        active = await self.session.scalars(
            select(WaveSession).where(
                WaveSession.user_id == user_id, WaveSession.is_active.is_(True)
            )
        )
        for wave_session in active:
            wave_session.is_active = False

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    async def build_context(
        self, user_id: uuid.UUID, wave_session: WaveSession
    ) -> UserContext:
        profile = await get_or_create_profile(self.session, user_id)

        recent_rows = await self.session.execute(
            select(PlayEvent.track_id)
            .where(PlayEvent.user_id == user_id)
            .order_by(PlayEvent.started_at.desc())
            .limit(RECENT_HISTORY_LIMIT)
        )
        played_ids = [str(row[0]) for row in recent_rows]

        liked_rows = await self.session.execute(
            select(TrackReaction.track_id).where(
                TrackReaction.user_id == user_id, TrackReaction.kind == "like"
            )
        )
        liked_ids = {str(row[0]) for row in liked_rows}

        disliked_vectors = await self._disliked_vectors(user_id)

        return UserContext(
            user_id=user_id,
            positive_vector=coerce_vector(profile.positive_vector)
            if profile.positive_vector
            else np.zeros(FEATURE_COUNT, dtype=np.float32),
            negative_vector=coerce_vector(profile.negative_vector)
            if profile.negative_vector
            else np.zeros(FEATURE_COUNT, dtype=np.float32),
            session_vector=coerce_vector(wave_session.session_vector)
            if wave_session.session_vector
            else np.zeros(FEATURE_COUNT, dtype=np.float32),
            genre_affinity={k: float(v) for k, v in (profile.genre_affinity or {}).items()},
            artist_affinity={k: float(v) for k, v in (profile.artist_affinity or {}).items()},
            era_affinity={k: float(v) for k, v in (profile.era_affinity or {}).items()},
            language_affinity={
                k: float(v) for k, v in (profile.language_affinity or {}).items()
            },
            is_cold=profile.is_cold,
            has_negative=bool(profile.negative_vector),
            recent_artist_ids=list(wave_session.recent_artist_ids or []),
            recent_track_ids=set(played_ids[:RECENT_EXCLUDE_LIMIT]),
            played_track_ids=set(played_ids),
            liked_track_ids=liked_ids,
            disliked_vectors=disliked_vectors,
        )

    async def _disliked_vectors(self, user_id: uuid.UUID) -> list[np.ndarray]:
        """Sonic vectors of the most recent dislikes, for the similarity penalty."""
        rows = await self.session.execute(
            select(AudioFeature.vector)
            .join(TrackReaction, TrackReaction.track_id == AudioFeature.track_id)
            .where(TrackReaction.user_id == user_id, TrackReaction.kind == "dislike")
            .order_by(TrackReaction.created_at.desc())
            .limit(12)
        )
        return [coerce_vector(row[0]) for row in rows if row[0]]

    # ------------------------------------------------------------------
    # Candidate generation
    # ------------------------------------------------------------------

    def _hard_filtered_query(
        self, user_id: uuid.UUID, banned_artist_ids: Sequence[str]
    ) -> Select[Any]:
        """Only the constraints that must never be relaxed.

        These encode explicit user instructions — a disliked track, a banned
        artist — and playability. Everything else is a preference and may be
        loosened when the pool runs dry; these may not, because serving a
        banned artist because the catalogue ran short is worse than serving
        nothing at all.
        """
        query = (
            select(Track, AudioFeature)
            .join(AudioFeature, AudioFeature.track_id == Track.id)
            .where(Track.status == TrackStatus.READY, Track.duration_ms > 0)
        )

        dislikes = (
            select(TrackReaction.track_id)
            .where(TrackReaction.user_id == user_id, TrackReaction.kind == "dislike")
            .scalar_subquery()
        )
        query = query.where(Track.id.notin_(dislikes))

        library_bans = (
            select(ArtistReaction.artist_id)
            .where(ArtistReaction.user_id == user_id, ArtistReaction.kind == "ban")
            .scalar_subquery()
        )
        query = query.where(
            ~Track.artist_links.any(TrackArtist.artist_id.in_(library_bans))
        )

        # Session-level bans ("never play this artist again" during a session).
        banned_uuids = [uuid.UUID(a) for a in banned_artist_ids if _is_uuid(a)]
        if banned_uuids:
            query = query.where(
                ~Track.artist_links.any(TrackArtist.artist_id.in_(banned_uuids))
            )

        return query

    def _base_query(
        self,
        user_id: uuid.UUID,
        context: UserContext,
        settings: WaveSettings,
        banned_artist_ids: Sequence[str],
    ) -> Select[Any]:
        query = self._hard_filtered_query(user_id, banned_artist_ids)

        # Just-played tracks: a preference, relaxable on a tiny catalogue.
        if context.recent_track_ids:
            query = query.where(
                Track.id.notin_([uuid.UUID(t) for t in context.recent_track_ids])
            )

        # The language setting is an explicit instruction, but on a catalogue
        # with no matching tracks it would empty the stream, so it is applied
        # here rather than among the hard filters.
        if settings.language is WaveLanguage.RUSSIAN:
            query = query.where(AudioFeature.language == "russian")
        elif settings.language is WaveLanguage.FOREIGN:
            query = query.where(AudioFeature.language == "foreign")
        elif settings.language is WaveLanguage.INSTRUMENTAL:
            query = query.where(
                or_(
                    AudioFeature.language == "instrumental",
                    AudioFeature.instrumentalness >= 0.6,
                )
            )

        return query

    async def gather_candidates(
        self,
        user_id: uuid.UUID,
        context: UserContext,
        settings: WaveSettings,
        wave_session: WaveSession,
    ) -> list[Candidate]:
        base = self._base_query(
            user_id, context, settings, wave_session.banned_artist_ids or []
        )
        character = settings.character

        # Each pool answers a different question, and the mix is what gives the
        # stream both familiarity and surprise. Sizes shift with "character".
        plan: list[tuple[str, Select[Any], int]] = []

        top_artists = _top_keys(context.artist_affinity, 25, minimum=0.08)
        top_genres = _top_keys(context.genre_affinity, 12, minimum=0.08)

        if character is WaveCharacter.FAVOURITE:
            sizes = {"liked": 180, "artist": 260, "genre": 180, "popular": 60,
                     "fresh": 60, "random": 80}
        elif character is WaveCharacter.UNFAMILIAR:
            sizes = {"liked": 0, "artist": 80, "genre": 200, "popular": 80,
                     "fresh": 300, "random": 200}
        elif character is WaveCharacter.POPULAR:
            sizes = {"liked": 60, "artist": 120, "genre": 140, "popular": 320,
                     "fresh": 100, "random": 120}
        else:
            sizes = {"liked": 100, "artist": 200, "genre": 180, "popular": 150,
                     "fresh": 140, "random": 180}

        if context.is_cold:
            # Nothing to personalise with yet: show the catalogue's best.
            sizes = {"liked": 0, "artist": 0, "genre": 60, "popular": 400,
                     "fresh": 200, "random": 250}

        if sizes["liked"]:
            liked = (
                base.join(TrackReaction, TrackReaction.track_id == Track.id)
                .where(TrackReaction.user_id == user_id, TrackReaction.kind == "like")
                .order_by(func.random())
                .limit(sizes["liked"])
            )
            plan.append(("liked", liked, sizes["liked"]))

        if sizes["artist"] and top_artists:
            artist_uuids = [uuid.UUID(a) for a in top_artists if _is_uuid(a)]
            if artist_uuids:
                affine = (
                    base.where(Track.artist_links.any(TrackArtist.artist_id.in_(artist_uuids)))
                    .order_by(func.random())
                    .limit(sizes["artist"])
                )
                plan.append(("artist", affine, sizes["artist"]))

        if sizes["genre"] and top_genres:
            from ..models import Genre

            genre_pool = (
                base.where(
                    Track.genre_links.any(
                        TrackGenre.genre_id.in_(
                            select(Genre.id)
                            .where(or_(Genre.slug.in_(top_genres),
                                       Genre.parent_slug.in_(top_genres)))
                            .scalar_subquery()
                        )
                    )
                )
                .order_by(func.random())
                .limit(sizes["genre"])
            )
            plan.append(("genre", genre_pool, sizes["genre"]))

        if sizes["popular"]:
            popular = base.order_by(Track.play_count.desc()).limit(sizes["popular"])
            plan.append(("popular", popular, sizes["popular"]))

        if sizes["fresh"] and context.played_track_ids:
            fresh = (
                base.where(
                    Track.id.notin_(
                        [uuid.UUID(t) for t in list(context.played_track_ids)[:300]]
                    )
                )
                .order_by(func.random())
                .limit(sizes["fresh"])
            )
            plan.append(("fresh", fresh, sizes["fresh"]))
        elif sizes["fresh"]:
            plan.append(("fresh", base.order_by(func.random()).limit(sizes["fresh"]),
                         sizes["fresh"]))

        if sizes["random"]:
            plan.append(("random", base.order_by(func.random()).limit(sizes["random"]),
                         sizes["random"]))

        max_play_count = await self._max_play_count()
        seen: dict[uuid.UUID, Candidate] = {}

        for source, query, _ in plan:
            if len(seen) >= POOL_LIMIT:
                break
            rows = await self.session.execute(query)
            for track, features in rows:
                if track.id in seen:
                    continue
                seen[track.id] = _to_candidate(track, features, max_play_count, source)
                if len(seen) >= POOL_LIMIT:
                    break

        if not seen:
            # The preferences combined to nothing — a small catalogue, or a
            # language with no matches. Drop the preferences but keep the hard
            # filters, so the stream never dead-ends and never resurrects a
            # banned artist or a disliked track.
            fallback = await self.session.execute(
                self._hard_filtered_query(user_id, wave_session.banned_artist_ids or [])
                .order_by(func.random())
                .limit(120)
            )
            for track, features in fallback:
                seen[track.id] = _to_candidate(track, features, max_play_count, "fallback")

        return list(seen.values())

    async def _max_play_count(self) -> int:
        value = await self.session.scalar(select(func.max(Track.play_count)))
        return int(value or 0)

    # ------------------------------------------------------------------
    # Batch generation
    # ------------------------------------------------------------------

    async def next_batch(
        self, user_id: uuid.UUID, count: int = 5, *, reset: bool = False
    ) -> list[WavePick]:
        count = max(1, min(count, 20))
        wave_session = await self.ensure_session(user_id, reset=reset)
        settings = await self.get_settings(user_id)
        context = await self.build_context(user_id, wave_session)

        weights = self._weights_for(settings, context)
        candidates = await self.gather_candidates(user_id, context, settings, wave_session)
        if not candidates:
            return []

        # Mood gates the pool before taste orders it; see apply_mood_gate.
        candidates = apply_mood_gate(candidates, settings.mood, min_keep=max(40, count * 6))
        ranked = rank_candidates(candidates, context, weights, settings.mood)

        # A run of skips means the current direction is wrong; widen the search
        # instead of serving more of the same.
        exploration = clamp(settings.diversity, 0.05, 0.9)
        if wave_session.skip_streak >= 3:
            exploration = clamp(exploration + 0.25 * (wave_session.skip_streak - 2), 0.05, 0.95)

        chosen = select_diverse(
            ranked,
            count,
            exploration=exploration,
            recent_artist_ids=context.recent_artist_ids,
        )
        if not chosen:
            return []

        return await self._persist_batch(wave_session, chosen)

    def _weights_for(self, settings: WaveSettings, context: UserContext) -> ScoringWeights:
        weights = DEFAULT_WEIGHTS.for_character(settings.character)
        if context.is_cold:
            weights = weights.for_cold_start()
        return weights

    async def _persist_batch(
        self, wave_session: WaveSession, chosen: list[ScoredCandidate]
    ) -> list[WavePick]:
        track_ids = [item.track_id for item in chosen]
        tracks = await self.session.scalars(select(Track).where(Track.id.in_(track_ids)))
        by_id = {track.id: track for track in tracks}

        start_position = wave_session.served_count
        recent_artists = list(wave_session.recent_artist_ids or [])
        picks: list[WavePick] = []

        for offset, item in enumerate(chosen):
            track = by_id.get(item.track_id)
            if track is None:  # pragma: no cover - deleted between queries
                continue
            position = start_position + offset
            reason = explain(item)

            self.session.add(
                WaveQueueItem(
                    session_id=wave_session.id,
                    track_id=track.id,
                    position=position,
                    state="served",
                    score=item.score,
                    reason=reason,
                    created_at=now_utc(),
                    served_at=now_utc(),
                )
            )
            picks.append(
                WavePick(track=track, score=item.score, reason=reason, position=position)
            )
            recent_artists.extend(str(a) for a in item.candidate.artist_ids)

        wave_session.served_count = start_position + len(picks)
        wave_session.recent_artist_ids = recent_artists[-40:]
        wave_session.last_active_at = now_utc()
        await self.session.flush()
        return picks

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    async def feedback(
        self,
        user_id: uuid.UUID,
        track: Track,
        kind: FeedbackKind,
        *,
        completion: float | None = None,
        persist_reaction: bool = True,
    ) -> dict[str, Any]:
        """Apply one signal from the player.

        ``persist_reaction`` is what makes a dislike stick. The taste vectors
        only bias the ranking, so without a stored reaction a disliked track
        would keep coming back around; the stored row is what the candidate
        query filters on. Callers that already wrote the reaction themselves
        pass False so it is not written twice.
        """
        wave_session = await self.ensure_session(user_id)

        if persist_reaction:
            await self._persist_reaction(user_id, track, kind)

        outcome = await apply_feedback(
            self.session,
            user_id=user_id,
            track=track,
            kind=kind,
            completion=completion,
            wave_session=wave_session,
        )
        await self.session.flush()
        return {
            "applied": outcome.applied,
            "kind": str(outcome.kind),
            "weight": outcome.weight,
            "skip_streak": wave_session.skip_streak,
        }

    async def _persist_reaction(
        self, user_id: uuid.UUID, track: Track, kind: FeedbackKind
    ) -> None:
        """Mirror a like/dislike/ban from the player into the library tables."""
        if kind in (FeedbackKind.LIKE, FeedbackKind.DISLIKE):
            wanted = "like" if kind is FeedbackKind.LIKE else "dislike"
            existing = await self.session.get(TrackReaction, (user_id, track.id))
            if existing is None:
                self.session.add(
                    TrackReaction(
                        user_id=user_id,
                        track_id=track.id,
                        kind=wanted,
                        created_at=now_utc(),
                    )
                )
            elif existing.kind != wanted:
                existing.kind = wanted
                existing.created_at = now_utc()

        elif kind is FeedbackKind.UNLIKE:
            existing = await self.session.get(TrackReaction, (user_id, track.id))
            if existing is not None and existing.kind == "like":
                await self.session.delete(existing)

        elif kind is FeedbackKind.BAN_ARTIST:
            # A ban has to outlive the listening session that issued it.
            for link in track.artist_links:
                if link.role is not ArtistRole.MAIN:
                    continue
                existing_ban = await self.session.get(
                    ArtistReaction, (user_id, link.artist_id)
                )
                if existing_ban is None:
                    self.session.add(
                        ArtistReaction(
                            user_id=user_id,
                            artist_id=link.artist_id,
                            kind="ban",
                            created_at=now_utc(),
                        )
                    )
                else:
                    existing_ban.kind = "ban"
                    existing_ban.created_at = now_utc()

        await self.session.flush()

    async def profile(self, user_id: uuid.UUID) -> TasteProfile:
        return await get_or_create_profile(self.session, user_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_candidate(
    track: Track, features: AudioFeature, max_play_count: int, source: str
) -> Candidate:
    album: Album | None = track.album
    return Candidate(
        track_id=track.id,
        artist_ids=[link.artist_id for link in track.artist_links],
        album_id=track.album_id,
        vector=coerce_vector(features.vector),
        genre_slugs=[link.genre.slug for link in track.genre_links if link.genre],
        language=features.language or "unknown",
        release_year=album.release_year if album else None,
        play_count=track.play_count,
        like_count=track.like_count,
        skip_rate=track.skip_rate,
        popularity=popularity_score(track.play_count, max_play_count),
        source=source,
    )


def _top_keys(affinity: dict[str, float], limit: int, *, minimum: float = 0.0) -> list[str]:
    ranked = sorted(affinity.items(), key=lambda kv: -float(kv[1]))
    return [key for key, value in ranked[:limit] if float(value) > minimum]


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True
