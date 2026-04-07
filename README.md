# GeoPolitical Domination

A turn-based strategy game where you compete to conquer the world. Build armies, expand territory, earn continent bonuses, and outmaneuver opponents.

## Quick Start

```bash
chmod +x setup.sh
./setup.sh
./play.sh
```

That's it. The setup script handles everything: Python, SDL2 libraries, virtual environment, and pip packages. It works on Ubuntu/Debian, Fedora, Arch, macOS (Homebrew), and Chromebook (Crostini).

## Manual Setup

If you prefer to do it yourself:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 client.py
```

On Debian/Ubuntu/Chromebook, you may also need SDL2:
```bash
sudo apt install -y libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
```

## Game Modes

### Local Game
Play against 0-6 AI bots on your machine. You pick a starting country, then take turns.

### Spectate Bots
Watch 2-8 AI bots battle each other. No human player — just sit back and watch.

### Online Game
Play with friends over the internet via Firebase. No setup required — uses public anonymous authentication.

## How to Play

Each turn you choose one action:

| Action | What it does |
|--------|-------------|
| **Peace** | Earn $100 per country you own — but you become vulnerable to attack |
| **Expand** | Move troops to an adjacent country. Costs $200. Unclaimed = free capture. Enemy = dice roll |
| **Gather Troops** | Roll d20 for buy limit, $50 per troop, distributed across your countries |
| **Do Nothing** | Skip your turn safely |

**Combat**: Attacker rolls 1d20, defender rolls 2d20 and takes the higher. Attacker wins if their roll is strictly greater (~25% odds). Attacking a player who chose Peace is a guaranteed win.

**Continent Bonuses** (one-time, for owning every country in a continent):
- Europe / Asia: $1,000
- North America: $800
- Africa: $400
- South America: $350
- Central America: $200

## Controls

| Control | Action |
|---------|--------|
| Scroll wheel | Zoom in/out |
| Right-click drag | Pan the map |
| F11 | Toggle fullscreen |
| Escape | Go back / quit |

## Tips

- Claim unclaimed territory first — it's free (just $200)
- Don't Peace when enemies have troops next to you — they'll take your land for free
- Continent bonuses are huge — prioritize completing one
- Watch your money. Every expansion costs $200 + crossing fees
- Gathering troops is capped by a d20 roll, so you can't stockpile in one turn

## Files

| File | Purpose |
|------|---------|
| `client.py` | Main game client (local + spectate + online) |
| `firebase_sync.py` | Firebase/Firestore backend for online mode |
| `heuristic_bot.py` | Bot AI entry point |
| `bot_playstyles.py` | Adaptive bot AI logic |
| `updater.py` | In-game update checker |
| `setup.sh` | One-command setup script |
| `play.sh` | Quick-launch script (created by setup.sh) |

## Troubleshooting

**"No module named pygame"** — Run `./setup.sh` again, or manually: `pip install pygame-ce`

**Game window is tiny** — Press F11 for fullscreen. The internal resolution is 2560x1440.

**"Firebase not available"** — Check your internet connection. Online mode uses anonymous Firebase auth (no secrets needed).

**SDL errors on Linux** — Install SDL2 dev packages: `sudo apt install libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev`
