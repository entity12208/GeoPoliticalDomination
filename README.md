# GeoPolitical Domination - Player's Guide

Welcome to GeoPolitical Domination (GPD), a turn-based strategy game where you compete to conquer the world! This guide will help you get started, no matter what computer you're using.

## What is this game?

GPD is a map-based strategy game where you:
- Take turns controlling countries on a world map
- Build armies and expand your territory
- Earn money to fund your conquests
- Compete against computer opponents or play online with friends
- Earn bonuses for controlling entire continents

## Getting Started

### On Windows:

1. Make sure you have Python installed:
   - Download Python from the [official website](https://www.python.org/downloads/)
   - During installation, make sure to check "Add Python to PATH"
   - Click Install Now (use all the default settings)

2. Download this game's files to a folder on your computer

3. Open PowerShell or Command Prompt:
   - Press Windows+R
   - Type "powershell" and press Enter
   - Use `cd` to navigate to where you saved the game files
   
4. Set up the game (copy and paste these commands):
```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

5. Run the game:
```
python client_local.py
```

### On Mac:

1. Install Python and required tools:
   - Install Homebrew first: Open Terminal and paste this command:
     ```
     /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
     ```
   - After Homebrew installs, run these commands:
     ```
     brew install python
     brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf
     ```

2. Download the game files to a folder

3. Open Terminal:
   - Press Command+Space
   - Type "Terminal" and press Enter
   - Use `cd` to navigate to your game folder

4. Set up the game:
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

5. Run the game:
```
python3 client_local.py
```

### On Chromebook:

1. Enable Linux on your Chromebook:
   - Click the time (bottom-right)
   - Click Settings
   - Under "Advanced", click "Developers"
   - Turn on "Linux development environment"
   - Wait for Linux to install

2. Open the Terminal app from your launcher

3. Install required software:
```
sudo apt update
sudo apt install -y python3 python3-venv python3-pip libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libsdl2-gfx-dev
```

4. Download the game files and navigate to that folder in Terminal

5. Set up the game:
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

6. Run the game:
```
python3 client_local.py
```

## How to Play

1. When you start the game, you'll see:
   - A world map
   - A "New Game" button
   - A slider to choose how many computer opponents you want

2. Click "New Game" and choose your starting country by clicking it on the map

3. On your turn, you have four choices:

   A) Peace (Green button)
   - Makes you vulnerable but earns money
   - Get $100 per country you own if nobody attacks you
   - Good for building up your treasury!

   B) Expand (Blue button)
   - Attack or claim nearby countries
   - Costs $200 to claim a country
   - Extra $100 cost to cross water, $200 to cross oceans
   - When attacking: You roll one 20-sided die, defender rolls two and uses the higher number
   - Winner takes the country!

   C) Gather Troops (Orange button)
   - Roll a die to see how many troops you can buy
   - Each troop costs $50
   - Troops are split among your countries
   - More troops = better defense and attack power

   D) Do Nothing (Red button)
   - Skip your turn
   - You won't be vulnerable
   - Use this if you can't or don't want to do anything else

## Tips for New Players

- Start by gathering troops and money
- Try to capture entire continents for bonus money:
  - Europe or Asia = $1000
  - North America = $800
  - South America, Central America, or Africa = $200
- Watch your money! Don't spend it all on troops
- Leave at least some troops in each country for defense
- If someone looks weak, that might be a trap (they might be in "Peace" mode)

## Troubleshooting

If the game won't start:
- Make sure you followed ALL the setup steps for your computer type
- Try closing and reopening your Terminal/PowerShell
- Make sure you're in the correct folder when running commands
- On Chromebook: Make sure Linux is fully installed and updated

If you see any error messages, try:
1. Closing the game
2. Opening Terminal/PowerShell again
3. Going to your game folder
4. Running the activate command for your computer
5. Running the game again



## Playing Online

To play with friends online, you'll need additional setup and a special file called `gpd_secrets.txt`. Ask the game maintainers for help setting this up - it requires some technical knowledge to configure properly.

Enjoy conquering the world! 🌎