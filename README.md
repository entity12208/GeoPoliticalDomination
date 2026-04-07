# GeoPolitical Domination

A turn-based strategy game where you compete to conquer the world. Build armies, expand territory, earn continent bonuses, and outmaneuver opponents — locally against AI bots, or online with friends.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/entity12208/GeoPoliticalDomination/main/setup.sh | bash
```

That's it. The script downloads the latest release, installs Python/SDL2 if needed, creates a virtual environment, and installs dependencies. Works on Ubuntu/Debian, Fedora, Arch, macOS, and Chromebook.

Then play:
```bash
cd ~/GeoPoliticalDomination
./play.sh
```

### Custom install location

```bash
GPD_INSTALL_DIR=/opt/gpd curl -fsSL https://raw.githubusercontent.com/entity12208/GeoPoliticalDomination/main/setup.sh | bash
```

### Manual setup (if you prefer)

```bash
git clone https://github.com/entity12208/GeoPoliticalDomination.git
cd GeoPoliticalDomination
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 client.py
```

On Debian/Ubuntu/Chromebook you may also need SDL2:
```bash
sudo apt install -y libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
```

## Game Modes

| Mode | Description |
|------|-------------|
| **Local Game** | Play against 0-6 AI bots on your machine |
| **Spectate Bots** | Watch 2-8 AI bots battle each other |
| **Online Game** | Play with friends via Firebase (no setup required) |

## How to Play

Each turn you choose one action:

| Action | What it does |
|--------|-------------|
| **Peace** | Earn $100 per country you own — but you become vulnerable for the entire round |
| **Expand** | Move troops to an adjacent country. $200 claim cost. Unclaimed = free. Enemy = dice roll |
| **Gather** | Roll d20 for buy limit, $50 per troop. Troops go to your border countries |
| **Nothing** | Skip your turn safely |

### Combat

Attacker rolls 1d20, defender rolls 2d20 (takes higher). Attacker wins if strictly greater (~25% odds). Attacking a player who chose Peace is a guaranteed win — no roll needed.

### Continent Bonuses (one-time)

| Continent | Bonus |
|-----------|-------|
| Europe / Asia | $1,000 |
| North America | $800 |
| Africa | $400 |
| South America | $350 |
| Central America | $200 |

## Controls

| Control | Action |
|---------|--------|
| Scroll wheel | Zoom in/out |
| Right-click drag | Pan the map |
| F11 | Toggle fullscreen |
| Escape | Go back / quit |

## Tips

- Claim unclaimed territory first — guaranteed for just $200
- Don't Peace when enemies have troops next to you — they auto-capture your land
- Continent bonuses are huge — prioritize completing one
- The AI adapts: it gathers troops on borders, exploits vulnerable players, and breaks stalemates

## Files

| File | Purpose |
|------|---------|
| `client.py` | Main game client (local + spectate + online) |
| `bot_playstyles.py` | Adaptive bot AI |
| `heuristic_bot.py` | Bot AI entry point |
| `firebase_sync.py` | Firebase REST backend (anonymous auth, no secrets needed) |
| `updater.py` | In-game update checker + downloader |
| `setup.sh` | Installer script (works via curl or locally) |

## Updating

The game checks for updates automatically on the main menu. Click "Update Now" to download and install in-app — it restarts automatically.

## Troubleshooting

**"No module named pygame"** — Run `./setup.sh` again, or: `source .venv/bin/activate && pip install pygame-ce`

**Game window is tiny** — Press F11 for fullscreen.

**"Firebase not available"** — Check your internet connection. Online mode uses anonymous auth (no secrets needed).

**SDL errors on Linux** — `sudo apt install libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev`

**venv creation fails** — `sudo apt install python3.XX-venv` (replace XX with your Python version, e.g. `python3.13-venv`)
