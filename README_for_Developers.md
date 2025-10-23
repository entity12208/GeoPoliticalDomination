# GeoPolitical Domination (GPD)

A small, local/online turn-based strategy game that uses clickable country polygons (generated from a GeoJSON world map). The project contains three playable clients:

- `client_local.py` — a cleaned/fixed local-only variant with improved bookkeeping, continent bonuses and safer bot behaviour.
- `client_online.py` — an online client that syncs authoritative game state with Firestore using `firebase_sync.FirebaseController`.
- `client_old.py` — the **(outdated)** main (single-file) game client with UI, map rendering and local bot support.

Other components:

- `firebase_sync.py` — Firestore controller and transaction logic for hosting multiplayer games.
- `heuristic_bot.py` — a local heuristic AI used by bots (client-side). The clients call `heuristic_bot.decide(snapshot, player_name)`.
- `assets/countries.geojson` — optional cached GeoJSON world map used to render country polygons.
- `gpd_secrets.txt` — (not for public sharing) service account JSON used by `firebase_sync` to connect to Firestore.
- `requirements.txt` — recommended Python packages.
- `config.txt`, `rules.txt`, `pin_overrides.json` — auxiliary configuration and rules.

## High-level summary

GPD renders a Mercator-projected world map and turns countries into clickable polygons. Players take turns to perform one of four actions: Peace (earn money if not attacked), Expand (move/attack into adjacent countries), Gather Troops (buy troops with money subject to a d20 roll), or Do Nothing. The online client uses a Firestore document per game to store authoritative state and transactions are applied server-side via `FirebaseController.submit_action`.

The codebase is intentionally small and self-contained. It uses `pygame` for rendering and optionally `google-cloud-firestore` for online multiplayer.

## Quick start (local)

1. Create a virtual environment and install dependencies (recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Run the local client:

```powershell
python client_local.py
```

3. Or run the single-file client with built-in download of GeoJSON (if `requests` is installed):

```powershell
python client.py
```

## Quick start (online)
**Note:** Online mode does not allow camera zoom.
1. Place your Firestore service account JSON into `gpd_secrets.txt` (full JSON content). Do NOT commit or share this file.

2. Install dependencies (see above) and run:

```powershell
python client_online.py
```

3. The online client can Create & Host or Join a room. The server-side logic is performed by Firestore transactions in `firebase_sync.py`.

## Files of interest

- `client.py` — main UI/game; will try to download `countries.geojson` into `assets/` if `requests` is available.
- `client_local.py` — local mode with improved rules and bot adapter.
- `client_online.py` — online mode; requires `gpd_secrets.txt` to connect to Firestore.
- `firebase_sync.py` — Firestore transaction and listeners. See `FirebaseController.create_or_open_game`, `claim_starting_country`, `submit_action`.
- `heuristic_bot.py` — exposes `decide(snapshot, name)`; used by local bots.
- `assets/countries.geojson` — if missing, the clients fall back to a tiny synthetic map.

## Configuration

- `config.txt` holds simple UI defaults (player name, default bot count, pin-scale overrides).
- `pin_overrides.json` may be used to tweak pin locations.
- `requirements.txt` lists the typical dependencies. The project was tested with Python 3.13 and pygame 2.x.

### Platform-specific notes

Below are copy-paste friendly setup and run steps for Windows (PowerShell), macOS, and ChromeOS (Crostini / Linux). Adjust the Python executable name if your system uses `python3`.

- Windows (PowerShell)

```powershell
# create and activate venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# install dependencies
pip install -r requirements.txt

# run local client
python client_local.py

# or run online client (ensure gpd_secrets.txt is present and valid)
python client_online.py
```

- macOS (Homebrew / terminal)

```bash
# install Python 3 if needed (homebrew)
brew install python

# create & activate venv
python3 -m venv .venv
source .venv/bin/activate

# install dependencies
pip install -r requirements.txt

# on macOS you may need to install SDL dependencies if pygame fails; using brew:
brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf

# run local client
python3 client_local.py
```

- ChromeOS (Linux / Crostini)

ChromeOS uses a Linux container (Crostini) for running Linux apps. The GUI from `pygame` generally works but may need additional packages. These steps assume you're in the Linux terminal (not the ChromeOS shell):

```bash
# update packages
sudo apt update && sudo apt upgrade -y

# install Python and build deps
sudo apt install -y python3 python3-venv python3-pip libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libsdl2-gfx-dev

# create venv and activate
python3 -m venv .venv
source .venv/bin/activate

# install Python deps
pip install -r requirements.txt

# If the display doesn't open, ensure the Crostini container has GUI support and that you're running from the Terminal app with "Linux (Beta)" enabled. You may also need to allow X11/Wayland forwarding depending on your setup.

# run the game
python3 client_local.py
```

Notes for ChromeOS GUI:

- Use the built-in Terminal (Linux Beta). If the pygame window does not appear, try launching the Terminal app from the ChromeOS launcher and ensure the container has the "Terminal" permission to show GUI windows.
- On some Chromebooks the container may need additional libraries; using the `apt` packages above usually resolves SDL backend issues.
- If using VNC/X11 or a remote display, ensure $DISPLAY is set properly in the container.

## Security and secrets

- `gpd_secrets.txt` contains a Google service account JSON — keep it secret. Do not commit or share the file publicly. If you need a separate service account, create one in Google Cloud IAM and download the JSON. The `FirebaseController` expects the full JSON inside `gpd_secrets.txt`.
- If you want to avoid storing credentials on disk, modify `firebase_sync.py` to use application default credentials or another secret mechanism.

## Development notes & testing

- The UI code is implemented with `pygame`; the rendering and input loops live in each client file.
- To run unit-like smoke checks, try importing key modules in a Python REPL:

```powershell
python -c "import pygame, requests; print('ok')"
```

- The code logs gameplay events to the in-game log (and stdout). `heuristic_bot.py` includes a small test harness at the bottom.

## Known behaviours & tips

- If `assets/countries.geojson` is missing the clients will fall back to a tiny synthetic two-country map.
- The online client expects the Firestore `games` collection structure managed by `FirebaseController`.
- Bots use `heuristic_bot.decide(...)`; if `heuristic_bot.py` fails to import, bots are disabled with a warning message.

## **This project is not for distribution!**