#!/bin/bash

# GeoPolitical Domination - Standalone Unix/macOS/Linux/ChromeOS Installer
# This script installs and runs the complete game from GitHub with NO other files needed!
# Simply run: bash gpd-setup-unix.sh

set -e

# Configuration
REPO_URL="https://github.com/entity12208/GeoPoliticalDomination.git"
INSTALL_DIR="$HOME/GeoPoliticalDomination"
TEMP_DIR="/tmp/gpd-setup-temp-$$"

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    IS_MACOS=true
    OS_NAME="macOS"
else
    IS_MACOS=false
    OS_NAME="Linux"
fi

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

clear
echo "======================================================================="
echo "  GeoPolitical Domination - Standalone Installer for $OS_NAME"
echo "======================================================================="
echo ""
echo "This installer will:"
echo "  1. Download the game from GitHub"
echo "  2. Install Python and dependencies"
echo "  3. Set up the game environment"
echo "  4. Launch the game"
echo ""
echo -e "${BLUE}Installation directory: $INSTALL_DIR${NC}"
echo ""
read -p "Press Enter to continue..."
echo ""

# Step 1: Check Python
echo -e "${BLUE}[1/6] Checking Python installation...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Python not found. Installing...${NC}"
    
    if $IS_MACOS; then
        # macOS - check for Homebrew
        if ! command -v brew &> /dev/null; then
            echo -e "${YELLOW}Installing Homebrew...${NC}"
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        brew install python@3.13
    else
        # Linux/ChromeOS
        sudo apt update
        sudo apt install -y python3 python3-venv python3-pip
    fi
fi
python3 --version
echo ""

# Step 2: Check Git
echo -e "${BLUE}[2/6] Checking Git installation...${NC}"
USE_ZIP=0
if ! command -v git &> /dev/null; then
    echo -e "${YELLOW}Git not found. Will download as ZIP.${NC}"
    USE_ZIP=1
else
    git --version
fi
echo ""

# Step 3: Install SDL2 (required for graphics)
echo -e "${BLUE}[3/6] Installing graphics libraries...${NC}"
if $IS_MACOS; then
    if ! command -v brew &> /dev/null; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf
else
    sudo apt install -y libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev
fi
echo -e "${GREEN}Graphics libraries installed${NC}"
echo ""

# Step 4: Download game
echo -e "${BLUE}[4/6] Downloading game from GitHub...${NC}"
mkdir -p "$INSTALL_DIR"

if [ $USE_ZIP -eq 1 ]; then
    echo "Downloading as ZIP file..."
    mkdir -p "$TEMP_DIR"
    cd "$TEMP_DIR"
    
    if command -v wget &> /dev/null; then
        wget -q https://github.com/entity12208/GeoPoliticalDomination/archive/main.zip
    elif command -v curl &> /dev/null; then
        curl -sL -o main.zip https://github.com/entity12208/GeoPoliticalDomination/archive/main.zip
    else
        echo -e "${RED}[ERROR] wget or curl not found${NC}"
        exit 1
    fi
    
    unzip -q main.zip
    cp -r GeoPoliticalDomination-main/* "$INSTALL_DIR/"
else
    if [ -d "$INSTALL_DIR/.git" ]; then
        cd "$INSTALL_DIR"
        git pull -q
    else
        git clone -q "$REPO_URL" "$INSTALL_DIR"
    fi
fi
echo -e "${GREEN}Game downloaded successfully!${NC}"
echo ""

# Step 5: Set up environment
echo -e "${BLUE}[5/6] Setting up Python environment...${NC}"
cd "$INSTALL_DIR"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
echo "Installing dependencies..."
python3 -m pip install --upgrade pip -q
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt -q
fi
echo -e "${GREEN}Environment set up successfully!${NC}"
echo ""

# Step 6: Launch game
echo -e "${BLUE}[6/6] Launching game...${NC}"
echo ""

# Create launcher menu
while true; do
    clear
    echo "======================================================================="
    echo "         GeoPolitical Domination - Game Launcher"
    echo "======================================================================="
    echo ""
    echo "What would you like to do?"
    echo ""
    echo "  [1] Offline Play"
    echo "      Play offline on this computer"
    echo ""
    echo "  [2] Online Play"
    echo "      Play with friends online (requires gpd_secrets.txt)"
    echo ""
    echo "  [3] Exit"
    echo ""
    read -p "Enter your choice (1-3): " choice
    
    case $choice in
        1)
            echo ""
            echo "Starting offline mode..."
            echo ""
            python3 "$INSTALL_DIR/client_local.py" || true
            echo ""
            read -p "Press Enter to return to menu..."
            ;;
        2)
            if [ ! -f "$INSTALL_DIR/gpd_secrets.txt" ]; then
                echo ""
                echo -e "${YELLOW}[WARNING] gpd_secrets.txt not found!${NC}"
                echo ""
                echo "Online mode requires a Firebase service account JSON file."
                echo "Please create gpd_secrets.txt in: $INSTALL_DIR"
                echo ""
                read -p "Press Enter to return to menu..."
            else
                echo ""
                echo "Starting online mode..."
                echo ""
                python3 "$INSTALL_DIR/client_online.py" || true
                echo ""
                read -p "Press Enter to return to menu..."
            fi
            ;;
        3)
            echo ""
            echo "Goodbye! Thanks for playing GeoPolitical Domination!"
            echo ""
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice. Please try again.${NC}"
            sleep 2
            ;;
    esac
done

# Cleanup
rm -rf "$TEMP_DIR"
