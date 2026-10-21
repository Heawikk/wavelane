"""One-off jobs on the catalogue, run by hand against the database the server uses.

    python -m wavelane.maintenance split-artists            what it would do, changing nothing
    python -m wavelane.maintenance split-artists --apply    do it

Stop to take a backup of the database first; the job is not undone by anything but that.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .db import dispose_engine, get_session_factory, init_models
from .services.artist_split import split_combined_artists


async def _split_artists(apply: bool) -> None:
    await init_models()
    async with get_session_factory()() as session:
        report = await split_combined_artists(session)
        if apply:
            await session.commit()
        else:
            await session.rollback()

    print(f"artists that are lists: {report.combined}")
    print(f"empty lists removed: {report.emptied}")
    print(f"artists created from their pieces: {report.created}")
    print(f"tracks re-credited: {report.tracks_changed}")
    print(f"albums moved: {report.albums_moved}, merged into an existing one: {report.albums_merged}")
    for name, pieces in report.examples:
        print(f"  {name!r} -> {pieces}")
    print("done." if apply else "nothing was changed; run again with --apply to do it.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m wavelane.maintenance")
    commands = parser.add_subparsers(dest="command", required=True)
    split = commands.add_parser("split-artists", help='turn artists named "A, B" into A and B')
    split.add_argument("--apply", action="store_true", help="make the change (default: only report)")
    args = parser.parse_args(argv)

    async def run() -> None:
        try:
            if args.command == "split-artists":
                await _split_artists(args.apply)
        finally:
            await dispose_engine()

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
