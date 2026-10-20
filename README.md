# Wavelane

A personal music streaming service with an endless personal radio —
**My Wave** ("Моя волна").

You upload your music library to the server; it reads the tags, extracts the
cover art, analyses the audio itself, and from then on picks music to match your
taste, mood and time of day — a stream that reacts to every like, dislike and
skip.

```
┌────────────────────┐        HTTP/JSON + Range        ┌──────────────────────┐
│  Qt 6 / QML client │ ◄─────────────────────────────► │  FastAPI server      │
│                    │                                 │                      │
│  • My Wave         │   GET  /wave/next               │  • catalogue         │
│  • player (FFmpeg) │   POST /wave/feedback           │  • ingest + DSP      │
│  • search, library │   GET  /stream/{id}  (Range)    │  • wave engine       │
│  • file upload     │   POST /library/plays           │  • streaming         │
└────────────────────┘                                 └──────────┬───────────┘
                                                                  │
                                                       SQLite / PostgreSQL
                                                       + file storage
```

## Status

| Component | State |
|---|---|
| Server (FastAPI) | Working. 67 API operations, 153 tests pass |
| My Wave engine | Working: learns from likes and listening, reacts to dislikes |
| Audio analysis (DSP) | Working: tempo, key, energy, brightness, dynamics |
| Windows client (Qt 6 / QML) | Builds and plays: sign-in, wave, search, library, upload |
| Android app | Working: phone layout, background playback, lyrics editor, swipes |
| Linux | Not started. The C++/QML client core is portable |

## Quick start

Windows is already set up — two scripts in the project root are enough:

```bat
run-server.bat          :: the server on http://127.0.0.1:8000
run-client.bat          :: the application
```

The server has to be running before the client starts. Stop the server with
`Ctrl+C` in its window.

### The server in more detail

```bash
cd server
python -m venv ../.venv
../.venv/Scripts/python.exe -m pip install -e ".[dev]"   # Linux: ../.venv/bin/python

cp .env.example .env        # be sure to change WAVELANE_SECRET_KEY
../.venv/Scripts/python.exe -m uvicorn wavelane.main:app --port 8000
```

`run-server.bat` does the same and passes any uvicorn options through:

```bat
run-server.bat --reload               :: restart when the code changes
run-server.bat --port 9000
run-server.bat --host 0.0.0.0         :: reachable from other devices on the network
```

The API documentation opens at <http://127.0.0.1:8000/docs>.

**The first registered account becomes the administrator** — create it right
away, through the client or through `POST /api/v1/auth/register`.

### Exposing the server to the internet

By default the server listens on `127.0.0.1` only. Before opening it to the
internet, go through this list.

1. **HTTPS is required.** The server does not do TLS itself, and without it the
   password and tokens travel in clear text. Put a reverse proxy in front of it,
   expose only the proxy's port, and keep `8000` closed. An example for Caddy
   (the Let's Encrypt certificate is obtained automatically):

   ```
   music.example.com {
       reverse_proxy 127.0.0.1:8000
   }
   ```

   A Cloudflare Tunnel (`cloudflared tunnel --url http://127.0.0.1:8000`) works
   too: no router ports are needed at all. If the proxy runs on another machine,
   start the server with `--forwarded-allow-ips <proxy address>`, otherwise the
   logs and the attempt limits will see the proxy's own address.
2. **Production mode** in `server\.env`. The server will not start while any of
   this is wrong:

   ```
   WAVELANE_ENVIRONMENT=production
   WAVELANE_DEBUG=false
   WAVELANE_SECRET_KEY=<a long random string, 32+ characters>
   WAVELANE_CORS_ORIGINS=[]
   ```

   In this mode the `/docs` and `/openapi.json` pages are closed. Generate a key
   with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Changing
   the key signs everybody out.
3. **Registration.** With `WAVELANE_ALLOW_REGISTRATION=true` anyone on the
   internet can create an account. Let your friends register, then set it to
   `false` and restart the server. The first account created is always the
   administrator, so never leave registration open on an empty database.
4. **The administrator password** should be long, preferably random (12+
   characters). It is the only thing protecting file uploads and folder imports.
5. **Files.** `server\.env`, `wavelane.db` and `storage\` must not end up in a
   repository or in shared folders; back them up.

What the server does by itself: neither the catalogue, nor search, nor
playlists, nor lyrics are served without signing in; sign-in attempts are
limited (6 failures per address + account pair in 15 minutes, 30 from one
address, 5 registrations an hour from one address, answered with `429`);
passwords are hashed off the main thread, so a flood of sign-in requests does
not stall everyone else; oversized JSON requests are rejected; playback tokens
are hidden in the access log; responses carry `nosniff` and `X-Frame-Options`.
Covers and avatars are open by link (the file name is its hash) because Discord
fetches them.

What is missing: two-factor authentication and attempt counting across restarts
(the counters live in memory). Check the dependencies with `pip-audit`.

### Demo catalogue

No music at hand? Generate 23 synthesised tracks in six styles — from ambient to
indie rock, with tags and genuinely different sound:

```bash
cd server
python scripts/make_demo_catalogue.py --out ../demo_music
```

### Adding music

**Only administrators** can add music (the first registered account is an
administrator). Everyone else just listens.

**A whole folder.** In the client: *Library → Import folder*. The server reads
the tags, extracts the covers and analyses the audio in the background: a
progress bar runs, the import can be stopped, and the client picks up an import
that is already running after a restart. Folders may be nested, files are
processed on several threads (the count is set by `WAVELANE_IMPORT_WORKERS`; by
default it is chosen automatically, up to 4). One import runs at a time. The same
through the API:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/imports   -H "Authorization: Bearer <access_token>" -H "Content-Type: application/json"   -d '{"path":"E:/Wavelane/demo_music"}'
curl http://127.0.0.1:8000/api/v1/admin/imports/<id> -H "Authorization: Bearer <access_token>"
```

The path is on **the machine where the server runs**. The source files are not
modified: the server copies them into its own storage.

**Individual files** — *Library → Upload files* (Ctrl+U); this works from another
computer too.

**Conflicts.** If a file is the same recording that is already in the library
(same artist and title, length within 8 seconds) but the file itself is
different, it is not imported silently but waits for your decision: *keep the
old one* or *replace it with the new one*. The conflicts window shows the
quality, length and size of both files side by side; the server only suggests
"replace" in advance for a clearly better copy (lossless instead of lossy, or a
bitrate more than 5% higher). There are buttons for deciding all at once.
Replacing swaps only the file itself — **likes, playlists, the listening history
and what the wave has learned from that track are untouched**. An exact copy of
a file that already exists is not a conflict, it is just a duplicate. Files
awaiting a decision are kept in the server's memory: after a restart the
question disappears, and the file can be imported again.

### Deleting

An administrator deletes a track in the details panel (the bin) or with the
Delete key, after a confirmation. Along with the track the file goes from the
disk, and so do albums and artists left empty; it disappears from playlists and
their totals are recalculated. Through the API there is also a bulk delete:
`POST /api/v1/tracks/bulk-delete`.

Windows will not let you delete a file that is playing right now. Such a file is
left on the disk as surplus, and `POST /api/v1/admin/cleanup` removes it. This
cleanup is deliberately manual and refuses to run on an empty catalogue:
otherwise, after recreating the database from scratch, you would be ordering it
to delete the whole library as unneeded.

### The client in more detail

Run it with `run-client.bat`. Options:

```bat
run-client.bat --wave                        :: start the wave straight away
run-client.bat --server http://host:8000     :: a different server
run-client.bat --help                        :: the rest
```

The log is written to `%LOCALAPPDATA%\Wavelane\client.log` — the GUI build on
Windows has no console, so for any unclear problem that is where to look.

### Lyrics

The **Lyrics** button in the bottom bar opens the words of the playing track over
the page.

- **Synchronised** lyrics follow the music: the line being sung is highlighted
  and kept in the centre. If you scroll with the wheel or drag, the view waits
  five seconds and returns to the line by itself (or use the "To the current
  line" button). Clicking a line seeks the song to it.
- **Plain** lyrics are simply shown and scrolled.
- If there are no lyrics, it says so.

Only an administrator adds and edits lyrics: "Add lyrics" / "Edit" in the lyrics
window itself. The "Text" tab accepts plain text or LRC (`[01:23.45] line`). The
"Sync" tab plays the track and you press Enter (or "Mark") at the moment each
line starts; Backspace goes a step back and rewinds the track. The finished
result is stored as LRC in the track's `lyrics` field, so it can be copied and
edited by hand. If the file's tags already contained lyrics, they are picked up
as plain text on import.

API: `GET /tracks/{id}/lyrics` (everyone), `PUT` and `DELETE` on the same path
(administrator).

In lists a mark follows the track title: grey — there are plain lyrics, blue —
the lyrics are synchronised. The track arrives with a `lyrics_kind` field for it
(`none` / `plain` / `synced`).

### Personalisation

Settings (the gear at the bottom left) → "Personalisation":

- The **glowing blobs** of the My Wave page background can be turned off. This is
  the most expensive thing the client draws: a shader on the GPU is evaluated
  every frame. A disabled background is not loaded at all (in a check on a test
  build, the process load dropped from ~59% to ~12% of one core with the blobs
  and the visualiser off).
- The **visualiser** under the buttons: bars, wave, dots, a ring around the play
  button, or off. If both the blobs and the visualiser are off, the page animates
  nothing.

### Windows and Discord

What is playing is visible outside the window. Settings are the gear in the
bottom left corner.

The **Windows media panel** (volume, lock screen, quick settings) works by
itself, with no setup: cover, title, artist, progress bar. The media keys of the
keyboard and headset pause, switch the track and seek. This is a system API
(`SystemMediaTransportControls`); on other systems this part is simply not
enabled.

In the panel the application is labelled "Wavelane": at start-up the client
registers its name with Windows (an entry in the Start menu and in the registry
under `HKCU\Software\Classes\AppUserModelId`). Without it the panel shows
"Unknown app".

**Discord Rich Presence** ("Listening to Wavelane", title, artist, time bar)
needs no setup: the application in Discord is shared, and its Application ID is
built into the client (`DiscordPresence.cpp`). In the settings it can only be
switched on or off.

The connection to Discord is held not by the client itself but by a small helper
— the same `wavelane.exe`, started with `--discord-relay` and outside the
client's process tree. When the client closes in any way (the cross, Alt+F4,
"End task" in the task manager), the helper notices the connection has dropped,
clears the status and exits. Otherwise Discord would go on showing "Listening to
Wavelane" for a long time.

Discord downloads track covers on its own side, so they appear only if the server
is visible from the internet (the address comes from the client's server
setting). With a server on the same computer or on a home network, the logo
uploaded to the application under the name `wavelane` is shown instead of a cover.

The client looks for a running Discord by itself and connects as soon as it
appears; if Discord is closed, nothing happens.

### Android

The phone app is built from the same sources: `client\build-android.bat` makes a
signed `dist\Wavelane-android.apk`, and `client\build-android.bat install` also
puts it on the phone through `adb` (USB debugging must be on). You need Qt 6.8.3
for Android (arm64), NDK r26b, JDK 17 and Android SDK 34; all of it lives in
`E:\Wavelane\tools`. Keep the signing key `tools\android\wavelane.keystore`: an
installed app can only be updated with the same key.

Qt has no TLS of its own on Android, so https:// (the update check, a server behind HTTPS) needs OpenSSL
next to the app: put `libssl_3.so` and `libcrypto_3.so` from the `ssl_3/arm64-v8a` folder of
[KDAB/android_openssl](https://github.com/KDAB/android_openssl) into `toolsndroid\opensslrm64-v8a` (or point
`-DWAVELANE_OPENSSL_DIR` elsewhere). Without them the build warns and https fails.

The look is the same, but the layout is its own (`MobileMain.qml`): the tabs
"Search / My Wave / Library" at the bottom, the mini player above them, the full
player and the lyrics on tap. To see it on a computer, start the client with
`WAVELANE_MOBILE=1`. Icons on the phone come from the built-in Material Icons
font (there is no Segoe font there), and the labels stay monospaced thanks to the
built-in Cascadia Mono.

Swipes: in the full player, down closes it, left skips to the next track, right
likes the current one; on the mini player, up opens the full player and left
skips; on the pages, a horizontal swipe turns to the next tab.

Music keeps playing with the screen off: there is a foreground service with a
notification (Previous / Pause / Next buttons, the cover, seeking on the lock
screen). The Back button on the main screen minimises the app, and swiping it
away from the recents list closes it together with the music. Qt's normal event
loop on Android freezes as soon as the window leaves the screen (and with it the
move to the next track), so the main thread has an event loop of its own without
that stop (`main.cpp`); the audio analysis for the picture and the animations
are switched off meanwhile to save battery.

The server over `http://` is allowed by the manifest (`usesCleartextTraffic`)
until it has HTTPS. From mobile data you need an address reachable from the
internet; on a home network an address like `http://192.168.0.202:8768` will do.

When the server cannot be reached, the app still opens and shows a "No connection
to the server" strip until it answers again.

### Building the client

You need Qt 6.5+ with the Multimedia module, CMake 3.21+ and a C++20 compiler.

```bat
client\build.bat Release     :: or Debug
```

Rebuild only after changes in `client\src` or `client\qml`. If the client is
running, close it — otherwise the linker cannot overwrite `wavelane.exe`.

`build.bat` hard-codes the Qt in `tools\Qt`, MSVC and the pip versions of
cmake/ninja, so the build does not depend on `PATH`. With Qt somewhere else,
change `QT_DIR` in it or build by hand:

```bash
cmake -S client -B client/build -G Ninja -DCMAKE_PREFIX_PATH=/path/to/Qt/6.8.3/gcc_64
cmake --build client/build --parallel
```

After the first build the Qt libraries have to be laid out next to
`wavelane.exe` — once:

```bat
tools\Qt\6.8.3\msvc2022_64\bin\windeployqt.exe --qmldir client\qml client\build\wavelane.exe
```

### Releases and updating

Ready-made files are published under
[Releases](https://github.com/Heawikk/wavelane/releases):

- `Wavelane_<version>_x64-portable.zip` — Windows, unpack and run `wavelane.exe`;
- `Wavelane_<version>_android.apk` — Android.

Settings show the version and a "Check for updates" button. If a newer version
has been released, an "Update" button appears: on Windows the app downloads the
zip, closes, replaces its files and starts again (its folder must be writable);
on Android the downloaded `.apk` is opened by the system installer (the first
time you need to allow Wavelane to install apps). The downloaded file is checked
against the checksum that GitHub reports.

Releasing a new version:

1. Raise the number in `client/CMakeLists.txt` (`project(Wavelane VERSION …)`);
   both the version shown in the app and the Android `versionCode` follow from it
   (it has to grow, or the system will not install the update over the old one).
2. `client\package-release.ps1` — builds both files into `dist\release`.
3. Create a release tagged `v<version>` and attach both files. The names must end
   in `portable.zip` and `.apk`: the app finds the right file by them.

The repository the app checks is set at build time
(`-DWAVELANE_UPDATE_REPO=owner/name`, `Heawikk/wavelane` by default). The APK is
signed with the key `tools\android\wavelane.keystore`; if you lose it, an already
installed app can no longer be updated, so keep a copy.

### ffmpeg — strongly recommended

Without ffmpeg the analysis relies on tags alone, and every track without genre
tags gets the same characteristics — the wave has nothing to learn from. Give the
path in `.env`:

```ini
WAVELANE_FFMPEG_PATH=/usr/bin/ffmpeg
```

To check: `GET /health` returns `"dsp_analysis": true`.

## How My Wave works

Every track is reduced to a vector of 10 normalised characteristics — tempo,
energy, valence, danceability, acousticness, instrumentalness, brightness,
loudness, dynamics, vocal presence. They are extracted by
[`services/audio_analysis.py`](server/wavelane/services/audio_analysis.py):
tempo from the autocorrelation of the onset envelope, key and major/minor from
the correlation of the chroma with the Krumhansl profiles, the rest from the
spectrogram. All of it is numpy, with no heavy ML dependencies.

The selection goes in four steps
([`wave/engine.py`](server/wavelane/wave/engine.py)):

1. **Context** — the long-term taste profile, the vector of the current session,
   affinities for genres and artists, what played recently, what is banned.
2. **Candidate pool** — several independent SQL queries from different angles:
   favourites, close artists, close genres, catalogue hits, never heard,
   random. Mixing the sources keeps the stream from sliding into a single
   cluster.
3. **Scoring** — numpy over the sound vector plus affinities, popularity and
   penalties ([`wave/scoring.py`](server/wavelane/wave/scoring.py)).
4. **Diversified selection** — a greedy pass with a cooldown on artist and album
   and a share of exploration, so the selection does not sound like one album.

A few decisions worth knowing:

- **Mood is a filter, not a term.** A trained taste vector gives a cosine of about
  0.95, and mood as one more weighted term always lost: a request for "upbeat"
  returned the same calm favourites. Choosing a mood says *which* music is
  allowed, and taste then decides the order within the allowed.
- **Two learning horizons.** The long-term profile is a moving average with a
  ceiling on the weight, the session vector changes fast. So one dislike visibly
  changes the next few tracks but does not rewrite your taste.
- **A dislike is irreversible.** It does not merely shift the vector, it is stored
  as a reaction that the selection is filtered on hard — otherwise the track would
  come back on the next round.
- **Hard filters are not relaxed.** If the pool is empty (a small catalogue, a
  narrow language filter), only the preferences are relaxed. A banned artist
  never comes back, even if there is nothing else to play.
- **Cosine is computed from the centre.** All characteristics in 0..1 point the
  same way, so a raw cosine is close to 1 even for opposite tracks; subtracting
  the neutral midpoint gives a feature its discriminating power back.
- **The genre tag resolves the tempo octave.** Autocorrelation regularly returns
  exactly half or double the tempo. Averaging is out — the midpoint between 66 and
  132 is 99, a musically meaningless value. Instead the typical tempo of the genre
  chooses which octave is plausible; on the demo catalogue this raised accuracy
  from 4/6 to 6/6.

Ordinary listening teaches the wave on a par with likes: the client sends
`POST /library/plays` with the time actually listened, and listening to the end is
a strong positive signal, abandoning after four seconds a negative one.

## Structure

```
server/
  wavelane/
    models/      — SQLAlchemy 2 (19 tables), compatible with SQLite and PostgreSQL
    schemas/     — Pydantic v2 DTOs
    api/routers/ — auth, catalog, wave, library, playlists, upload, stream
    services/    — security, storage, ingest, audio_analysis, streaming
    wave/        — features, scoring, feedback, engine
  scripts/       — the demo catalogue generator
  tests/         — 153 tests
client/
  src/           — the C++ core: ApiClient, Player, controllers
  qml/           — the interface
```

## Development

```bash
cd server
../.venv/Scripts/python.exe -m pytest -q        # 153 tests, ~30 s
../.venv/Scripts/python.exe -m ruff check .
```

The tests are hermetic: each test has its own database and its own storage, DSP
analysis is off (it has its own tests on a synthetic signal), so the result does
not depend on what is installed on the machine.

### Icon and logo

The logo is three waves with no background. There is one drawing for everything:
`client/qml/Logo.qml` (in the interface) and `client/resources/make_icons.py` (the
application icon) use the same geometry and the same colours. If you change the
drawing, regenerate the icon files:

```bash
.venv/Scripts/python.exe client/resources/make_icons.py
```

The script writes `wavelane.ico` (the icon of the `.exe` itself) and
`wavelane-<size>.png` (the window icon); both are embedded automatically at build
time.

## Moving to PostgreSQL

The code has been PostgreSQL-compatible from the start: JSON fields expand to
JSONB, and the schema is checked on both dialects. One line changes:

```ini
WAVELANE_DATABASE_URL=postgresql+asyncpg://wavelane:password@localhost:5432/wavelane
```

Plus `pip install -e ".[postgres]"`. On large catalogues the candidate pool
generation is worth replacing with an approximate nearest-neighbour index
(pgvector); everything else in the engine stays as it is.

## What next

- Alembic migrations instead of `create_all` (now the schema is created at start-up)
- Full-text search (PostgreSQL `tsvector` / SQLite FTS5) instead of `LIKE`
- Collaborative filtering on co-listening — now the recommendations are built on
  content, which works well for a single user but does not use "people like you
  enjoyed this"
- Transcoding to fit the bandwidth, and HLS
- A Linux client on the same core
- Vocal detection: `instrumentalness` is currently the weakest of the
  characteristics, relying on fundamental-frequency movement and vibrato

## Licensing and rights

The project code is yours. The music you upload is your responsibility:
Wavelane downloads nothing from the internet and is meant for a personal library.
The tracks from `scripts/make_demo_catalogue.py` are synthesised from scratch.
