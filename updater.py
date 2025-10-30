# updater.py
"""
GeoPolitical Domination - Updater Tool
Checks for updates from GitHub and allows downloading specific releases.
Repository: https://github.com/entity12208/GeoPoliticalDomination
"""

import os
import sys
import json
import urllib.request
import zipfile
import shutil
from pathlib import Path

GITHUB_API_URL = "https://api.github.com/repos/entity12208/GeoPoliticalDomination/releases"
GITHUB_REPO_URL = "https://github.com/entity12208/GeoPoliticalDomination"
CURRENT_VERSION_FILE = "version.txt"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_current_version():
    """Read the current version from version.txt"""
    version_path = os.path.join(BASE_DIR, CURRENT_VERSION_FILE)
    try:
        with open(version_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return "unknown"

def save_current_version(version):
    """Save the current version to version.txt"""
    version_path = os.path.join(BASE_DIR, CURRENT_VERSION_FILE)
    try:
        with open(version_path, 'w', encoding='utf-8') as f:
            f.write(version)
        return True
    except Exception as e:
        print(f"Error saving version: {e}")
        return False

def fetch_releases():
    """Fetch all releases from GitHub API"""
    try:
        print("Fetching releases from GitHub...")
        req = urllib.request.Request(GITHUB_API_URL)
        req.add_header('User-Agent', 'GPD-Updater/1.0')
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read()
            releases = json.loads(data)
            return releases
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        return None
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")
        return None
    except Exception as e:
        print(f"Error fetching releases: {e}")
        return None

def display_releases(releases):
    """Display available releases"""
    if not releases:
        print("No releases found.")
        return
    
    print("\n" + "="*70)
    print("Available Releases:")
    print("="*70)
    
    for idx, release in enumerate(releases, 1):
        tag = release.get('tag_name', 'unknown')
        name = release.get('name', 'Unnamed Release')
        published = release.get('published_at', 'unknown')[:10]
        prerelease = " [PRE-RELEASE]" if release.get('prerelease') else ""
        draft = " [DRAFT]" if release.get('draft') else ""
        
        print(f"{idx}. {name} ({tag}){prerelease}{draft}")
        print(f"   Published: {published}")
        
        assets = release.get('assets', [])
        if assets:
            print(f"   Assets: {len(assets)} file(s)")
        
        print()

def download_and_extract_release(release, target_dir=None):
    """Download and extract a release"""
    if target_dir is None:
        target_dir = BASE_DIR
    
    assets = release.get('assets', [])
    zipball_url = release.get('zipball_url')
    tag = release.get('tag_name', 'unknown')
    
    # Prefer zip asset if available, otherwise use zipball_url
    download_url = None
    asset_name = None
    
    for asset in assets:
        if asset['name'].endswith('.zip'):
            download_url = asset['browser_download_url']
            asset_name = asset['name']
            break
    
    if not download_url:
        download_url = zipball_url
        asset_name = f"GPD-{tag}.zip"
    
    if not download_url:
        print("No download URL found for this release.")
        return False
    
    print(f"\nDownloading {asset_name}...")
    temp_zip = os.path.join(target_dir, "temp_update.zip")
    
    try:
        # Download with progress
        req = urllib.request.Request(download_url)
        req.add_header('User-Agent', 'GPD-Updater/1.0')
        
        with urllib.request.urlopen(req, timeout=30) as response:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(temp_zip, 'wb') as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\rProgress: {percent:.1f}% ({downloaded}/{total_size} bytes)", end='')
        
        print("\n\nExtracting files...")
        
        # Create backup directory
        backup_dir = os.path.join(target_dir, "backup_before_update")
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir)
        os.makedirs(backup_dir, exist_ok=True)
        
        # Backup important files
        important_files = ['config.txt', 'gpd_secrets.txt', 'pin_overrides.json', 'version.txt']
        for fname in important_files:
            src = os.path.join(target_dir, fname)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(backup_dir, fname))
                print(f"Backed up: {fname}")

        # Clean the directory before extraction
        print("Cleaning old files...")
        files_to_keep = [
            os.path.basename(__file__),  # updater.py
            os.path.basename(backup_dir),
            os.path.basename(temp_zip),
            '.git'
        ]

        for item in os.listdir(target_dir):
            if item not in files_to_keep:
                item_path = os.path.join(target_dir, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                    print(f"Removed: {item}")
                except Exception as e:
                    print(f"Could not remove {item}: {e}")
        
        # Extract zip
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            # Get the root folder in the zip (for GitHub zipballs)
            namelist = zip_ref.namelist()
            root_folder = None
            
            if namelist:
                root_folder = namelist[0].split('/')[0] + '/'
            
            for member in namelist:
                # Do not overwrite the updater script
                if os.path.basename(member) == os.path.basename(__file__):
                    continue

                # Skip the root folder in path
                if root_folder and member.startswith(root_folder):
                    target_path = os.path.join(target_dir, member[len(root_folder):])
                else:
                    target_path = os.path.join(target_dir, member)
                
                if member.endswith('/'):
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with zip_ref.open(member) as source, open(target_path, 'wb') as target:
                        shutil.copyfileobj(source, target)
        
        # Restore important files
        for fname in important_files:
            backup_file = os.path.join(backup_dir, fname)
            if os.path.exists(backup_file):
                shutil.copy2(backup_file, os.path.join(target_dir, fname))
                print(f"Restored: {fname}")
        
        # Clean up
        os.remove(temp_zip)
        
        # Save new version
        save_current_version(tag)
        
        print(f"\n✓ Successfully updated to {tag}!")
        print(f"  Backup of your config files saved in: {backup_dir}")
        return True
        
    except Exception as e:
        print(f"\n✗ Error during download/extraction: {e}")
        if os.path.exists(temp_zip):
            os.remove(temp_zip)
        return False

def check_for_updates():
    """Check if a newer version is available"""
    current = get_current_version()
    releases = fetch_releases()
    
    if not releases or len(releases) == 0:
        return None, current
    
    latest = releases[0]
    latest_tag = latest.get('tag_name', 'unknown')
    
    return latest, current

def interactive_mode():
    """Interactive updater interface"""
    print("="*70)
    print("GeoPolitical Domination - Updater")
    print("="*70)
    print(f"Repository: {GITHUB_REPO_URL}")
    print(f"Current Version: {get_current_version()}")
    print()
    
    releases = fetch_releases()
    
    if not releases:
        print("Failed to fetch releases. Check your internet connection.")
        return
    
    if len(releases) == 0:
        print("No releases available yet.")
        return
    
    display_releases(releases)
    
    print("="*70)
    print("Options:")
    print("  1-{}: Download and install specific release".format(len(releases)))
    print("  L: Install latest release")
    print("  Q: Quit without updating")
    print("="*70)
    
    choice = input("\nEnter your choice: ").strip().upper()
    
    if choice == 'Q':
        print("Update cancelled.")
        return
    
    if choice == 'L':
        selected_release = releases[0]
        print(f"\nSelected: {selected_release.get('name')} ({selected_release.get('tag_name')})")
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(releases):
                selected_release = releases[idx]
                print(f"\nSelected: {selected_release.get('name')} ({selected_release.get('tag_name')})")
            else:
                print("Invalid selection.")
                return
        except ValueError:
            print("Invalid input.")
            return
    
    confirm = input("\nThis will overwrite existing files (config files will be backed up). Continue? (y/n): ").strip().lower()
    
    if confirm == 'y':
        success = download_and_extract_release(selected_release)
        if success:
            print("\n✓ Update completed successfully!")
            print("  Please restart the game to use the new version.")
        else:
            print("\n✗ Update failed. Your game files remain unchanged.")
    else:
        print("Update cancelled.")

def silent_check():
    """Silent check for updates (for integration into game client)"""
    latest, current = check_for_updates()
    
    if latest:
        latest_tag = latest.get('tag_name', 'unknown')
        if current != latest_tag and current != 'unknown':
            return {
                'update_available': True,
                'current': current,
                'latest': latest_tag,
                'release': latest
            }
    
    return {'update_available': False, 'current': current}

if __name__ == "__main__":
    try:
        interactive_mode()
    except KeyboardInterrupt:
        print("\n\nUpdate cancelled by user.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    
    input("\nPress Enter to exit...")