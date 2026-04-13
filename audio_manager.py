"""
audio_manager.py - SFX and music management for GeoPolitical Domination.

Provides AudioManager class for playing sound effects and background music.
Programmatically generates sound effects using pygame.sndarray if audio files
don't exist. Falls back gracefully if mixer initialization fails.
"""

import os
import logging
from pathlib import Path

import pygame
import pygame.mixer

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from constants import AUDIO_DIR, DEFAULT_SFX_VOLUME, DEFAULT_MUSIC_VOLUME

logger = logging.getLogger(__name__)


class AudioManager:
    """Manages SFX and background music for the game."""

    def __init__(self, sfx_volume=None, music_volume=None):
        """
        Initialize the audio manager.

        Args:
            sfx_volume: SFX volume (0.0-1.0), defaults to DEFAULT_SFX_VOLUME
            music_volume: Music volume (0.0-1.0), defaults to DEFAULT_MUSIC_VOLUME
        """
        if sfx_volume is None:
            sfx_volume = DEFAULT_SFX_VOLUME
        if music_volume is None:
            music_volume = DEFAULT_MUSIC_VOLUME

        self.sfx_volume = max(0.0, min(1.0, sfx_volume))
        self.music_volume = max(0.0, min(1.0, music_volume))
        self.mixer_initialized = False
        self.sfx_sounds = {}  # name -> pygame.mixer.Sound
        self.current_music = None
        self.music_files = []

        self._init_mixer()
        self._load_sounds()
        self._scan_music_files()

    def _init_mixer(self):
        """Initialize pygame mixer, handle gracefully if it fails."""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(
                    frequency=22050,
                    size=-16,
                    channels=2,
                    buffer=512,
                )
            self.mixer_initialized = True
            logger.info("Pygame mixer initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize pygame mixer: {e}")
            self.mixer_initialized = False

    def _load_sounds(self):
        """Load or generate sound effects. Safe to call even if mixer init failed."""
        if not self.mixer_initialized:
            logger.debug("Mixer not initialized; skipping sound loading")
            return

        sound_names = [
            "click",
            "attack",
            "capture",
            "turn",
            "victory",
            "defeat",
            "chat",
            "error",
        ]

        # Try to load from files first
        audio_sfx_dir = os.path.join(AUDIO_DIR, "sfx")
        for name in sound_names:
            # Try .ogg, then .wav, then .mp3
            for ext in [".ogg", ".wav", ".mp3"]:
                sound_path = os.path.join(audio_sfx_dir, f"{name}{ext}")
                if os.path.exists(sound_path):
                    try:
                        sound = pygame.mixer.Sound(sound_path)
                        sound.set_volume(self.sfx_volume)
                        self.sfx_sounds[name] = sound
                        logger.debug(f"Loaded SFX: {name} from {sound_path}")
                        break
                    except Exception as e:
                        logger.warning(f"Failed to load SFX '{name}' from {sound_path}: {e}")

        # Generate sounds for any that weren't loaded
        for name in sound_names:
            if name not in self.sfx_sounds:
                try:
                    sound = self._generate_sfx(name)
                    if sound:
                        self.sfx_sounds[name] = sound
                        logger.debug(f"Generated SFX: {name}")
                except Exception as e:
                    logger.warning(f"Failed to generate SFX '{name}': {e}")

    def _generate_sfx(self, name):
        """
        Programmatically generate a sound effect.

        Args:
            name: Sound name (click, attack, capture, turn, victory, defeat, chat, error)

        Returns:
            pygame.mixer.Sound or None
        """
        if not self.mixer_initialized:
            return None

        try:
            if name == "click":
                return self._gen_click()
            elif name == "attack":
                return self._gen_attack()
            elif name == "capture":
                return self._gen_capture()
            elif name == "turn":
                return self._gen_turn()
            elif name == "victory":
                return self._gen_victory()
            elif name == "defeat":
                return self._gen_defeat()
            elif name == "chat":
                return self._gen_chat()
            elif name == "error":
                return self._gen_error()
            else:
                return None
        except Exception as e:
            logger.warning(f"Error generating SFX '{name}': {e}")
            return None

    def _gen_click(self):
        """Generate short UI click (high pitched blip, ~50ms)."""
        sample_rate = 22050
        duration = 0.05  # 50ms
        num_samples = int(sample_rate * duration)
        frequency = 1200  # high pitch

        if HAS_NUMPY:
            t = np.linspace(0, duration, num_samples, dtype=np.float32)
            # Sine wave with sharp envelope
            envelope = np.exp(-30 * t)  # quick decay
            wave = np.sin(2 * np.pi * frequency * t) * envelope
            wave = (wave * 32767).astype(np.int16)
        else:
            wave = self._gen_sine_wave_fallback(frequency, duration, sample_rate)

        sound = pygame.mixer.Sound(buffer=wave.tobytes())
        sound.set_volume(self.sfx_volume)
        return sound

    def _gen_attack(self):
        """Generate combat sound (noise burst, ~200ms)."""
        sample_rate = 22050
        duration = 0.2  # 200ms
        num_samples = int(sample_rate * duration)

        if HAS_NUMPY:
            t = np.linspace(0, duration, num_samples, dtype=np.float32)
            # White noise with envelope
            noise = np.random.randn(num_samples).astype(np.float32) * 0.7
            envelope = np.exp(-5 * t)  # moderate decay
            wave = noise * envelope
            wave = (wave * 32767).astype(np.int16)
        else:
            # Fallback: sine wave with modulation
            wave = self._gen_sine_wave_fallback(800, duration, sample_rate)

        sound = pygame.mixer.Sound(buffer=wave.tobytes())
        sound.set_volume(self.sfx_volume)
        return sound

    def _gen_capture(self):
        """Generate territory captured (rising tone, ~300ms)."""
        sample_rate = 22050
        duration = 0.3  # 300ms
        num_samples = int(sample_rate * duration)

        if HAS_NUMPY:
            t = np.linspace(0, duration, num_samples, dtype=np.float32)
            # Frequency sweep from 600 to 1000 Hz
            freq_start, freq_end = 600, 1000
            freq = freq_start + (freq_end - freq_start) * (t / duration)
            phase = 2 * np.pi * np.cumsum(freq) / sample_rate
            wave = np.sin(phase).astype(np.float32)
            # Fade in and out
            envelope = np.sin(np.pi * t / duration) ** 0.5
            wave = wave * envelope * 0.8
            wave = (wave * 32767).astype(np.int16)
        else:
            wave = self._gen_sine_wave_fallback(800, duration, sample_rate)

        sound = pygame.mixer.Sound(buffer=wave.tobytes())
        sound.set_volume(self.sfx_volume)
        return sound

    def _gen_turn(self):
        """Generate turn change (soft chime, ~150ms)."""
        sample_rate = 22050
        duration = 0.15  # 150ms
        num_samples = int(sample_rate * duration)

        if HAS_NUMPY:
            t = np.linspace(0, duration, num_samples, dtype=np.float32)
            # Bell-like: mix of two frequencies
            freq1, freq2 = 1000, 1500
            wave = (
                np.sin(2 * np.pi * freq1 * t) * 0.5
                + np.sin(2 * np.pi * freq2 * t) * 0.5
            )
            # Gentle decay envelope
            envelope = np.exp(-8 * t)
            wave = wave * envelope * 0.7
            wave = (wave * 32767).astype(np.int16)
        else:
            wave = self._gen_sine_wave_fallback(1200, duration, sample_rate)

        sound = pygame.mixer.Sound(buffer=wave.tobytes())
        sound.set_volume(self.sfx_volume)
        return sound

    def _gen_victory(self):
        """Generate game won (ascending arpeggio, ~500ms)."""
        sample_rate = 22050
        duration = 0.5  # 500ms
        num_samples = int(sample_rate * duration)

        if HAS_NUMPY:
            t = np.linspace(0, duration, num_samples, dtype=np.float32)
            # Arpeggio: C, E, G (261, 329, 392 Hz) ascending
            freq1_start, freq1_end = 0, 0.15
            freq2_start, freq2_end = 0.25, 0.4
            freq3_start, freq3_end = 0.4, 0.5

            wave = np.zeros(num_samples, dtype=np.float32)

            # First note
            mask1 = t < 0.15
            t1 = t[mask1]
            wave[mask1] += (
                np.sin(2 * np.pi * 261 * t1)
                * np.sin(np.pi * t1 / 0.15) ** 0.3
            )

            # Second note
            mask2 = (t >= 0.15) & (t < 0.35)
            t2 = t[mask2] - 0.15
            wave[mask2] += (
                np.sin(2 * np.pi * 329 * t2)
                * np.sin(np.pi * t2 / 0.2) ** 0.3
            )

            # Third note
            mask3 = t >= 0.35
            t3 = t[mask3] - 0.35
            wave[mask3] += (
                np.sin(2 * np.pi * 392 * t3)
                * np.sin(np.pi * t3 / 0.15) ** 0.3
            )

            wave = (wave * 32767 * 0.7).astype(np.int16)
        else:
            wave = self._gen_sine_wave_fallback(1000, duration, sample_rate)

        sound = pygame.mixer.Sound(buffer=wave.tobytes())
        sound.set_volume(self.sfx_volume)
        return sound

    def _gen_defeat(self):
        """Generate game lost (descending tone, ~400ms)."""
        sample_rate = 22050
        duration = 0.4  # 400ms
        num_samples = int(sample_rate * duration)

        if HAS_NUMPY:
            t = np.linspace(0, duration, num_samples, dtype=np.float32)
            # Frequency sweep from 800 down to 300 Hz
            freq_start, freq_end = 800, 300
            freq = freq_start + (freq_end - freq_start) * (t / duration)
            phase = 2 * np.pi * np.cumsum(freq) / sample_rate
            wave = np.sin(phase).astype(np.float32)
            # Fade out (sad sound)
            envelope = np.exp(-6 * t) * np.sin(np.pi * t / duration)
            wave = wave * envelope * 0.8
            wave = (wave * 32767).astype(np.int16)
        else:
            wave = self._gen_sine_wave_fallback(600, duration, sample_rate)

        sound = pygame.mixer.Sound(buffer=wave.tobytes())
        sound.set_volume(self.sfx_volume)
        return sound

    def _gen_chat(self):
        """Generate new chat message (soft ding, ~100ms)."""
        sample_rate = 22050
        duration = 0.1  # 100ms
        num_samples = int(sample_rate * duration)

        if HAS_NUMPY:
            t = np.linspace(0, duration, num_samples, dtype=np.float32)
            # Soft ding: 800 Hz with bell-like envelope
            frequency = 800
            wave = np.sin(2 * np.pi * frequency * t)
            envelope = np.exp(-20 * t) * np.sin(np.pi * t / duration) ** 0.4
            wave = wave * envelope * 0.6
            wave = (wave * 32767).astype(np.int16)
        else:
            wave = self._gen_sine_wave_fallback(800, duration, sample_rate)

        sound = pygame.mixer.Sound(buffer=wave.tobytes())
        sound.set_volume(self.sfx_volume)
        return sound

    def _gen_error(self):
        """Generate error/invalid action (low buzz, ~200ms)."""
        sample_rate = 22050
        duration = 0.2  # 200ms
        num_samples = int(sample_rate * duration)

        if HAS_NUMPY:
            t = np.linspace(0, duration, num_samples, dtype=np.float32)
            # Low frequency buzz with wobble
            freq_base = 300
            freq_wobble = np.sin(2 * np.pi * 8 * t) * 50  # 8 Hz wobble
            freq = freq_base + freq_wobble
            phase = 2 * np.pi * np.cumsum(freq) / sample_rate
            wave = np.sin(phase).astype(np.float32)
            # Sharp attack, moderate decay (alarm-like)
            envelope = np.exp(-4 * t) * np.clip(t * 30, 0, 1)
            wave = wave * envelope * 0.7
            wave = (wave * 32767).astype(np.int16)
        else:
            wave = self._gen_sine_wave_fallback(300, duration, sample_rate)

        sound = pygame.mixer.Sound(buffer=wave.tobytes())
        sound.set_volume(self.sfx_volume)
        return sound

    def _gen_sine_wave_fallback(self, frequency, duration, sample_rate):
        """
        Fallback sine wave generator when numpy is not available.

        Args:
            frequency: Frequency in Hz
            duration: Duration in seconds
            sample_rate: Sample rate in Hz

        Returns:
            np.ndarray of int16 samples (or array-like)
        """
        import array

        num_samples = int(sample_rate * duration)
        samples = []
        for i in range(num_samples):
            t = i / sample_rate
            # Simple sine with exponential decay
            decay = 2.71828 ** (-5 * t)  # e^(-5*t)
            sample = int(32767 * 0.7 * decay * (1 if int(t * frequency) % 2 == 0 else -1))
            samples.append(sample)

        # Return as bytes-like for pygame.mixer.Sound
        wave_array = array.array("h", samples)
        return wave_array

    def _scan_music_files(self):
        """Scan AUDIO_DIR/music/ for .ogg and .mp3 files."""
        music_dir = os.path.join(AUDIO_DIR, "music")
        if not os.path.isdir(music_dir):
            logger.debug(f"Music directory not found: {music_dir}")
            return

        try:
            for filename in os.listdir(music_dir):
                if filename.endswith((".ogg", ".mp3")):
                    full_path = os.path.join(music_dir, filename)
                    self.music_files.append(full_path)
            if self.music_files:
                logger.debug(f"Found {len(self.music_files)} music file(s)")
        except OSError as e:
            logger.warning(f"Failed to scan music directory: {e}")

    def play_sfx(self, name):
        """
        Play a named sound effect.

        Args:
            name: Sound effect name (click, attack, capture, turn, victory, defeat, chat, error)
        """
        if not self.mixer_initialized:
            return

        sound = self.sfx_sounds.get(name)
        if sound:
            try:
                sound.set_volume(self.sfx_volume)
                sound.play()
            except Exception as e:
                logger.warning(f"Failed to play SFX '{name}': {e}")
        else:
            logger.debug(f"SFX '{name}' not loaded")

    def play_music(self, track_name=None):
        """
        Start background music loop.

        Args:
            track_name: Optional specific track name (filename without directory).
                       If None, plays the first available music file.
        """
        if not self.mixer_initialized or not self.music_files:
            return

        try:
            if track_name:
                # Try to find specific track
                for music_file in self.music_files:
                    if os.path.basename(music_file) == track_name:
                        pygame.mixer.music.load(music_file)
                        pygame.mixer.music.set_volume(self.music_volume)
                        pygame.mixer.music.play(-1)  # loop forever
                        self.current_music = music_file
                        logger.debug(f"Playing music: {track_name}")
                        return
                logger.warning(f"Music track '{track_name}' not found")
            else:
                # Play first available music file
                if self.music_files:
                    pygame.mixer.music.load(self.music_files[0])
                    pygame.mixer.music.set_volume(self.music_volume)
                    pygame.mixer.music.play(-1)  # loop forever
                    self.current_music = self.music_files[0]
                    logger.debug(f"Playing music: {os.path.basename(self.music_files[0])}")
        except Exception as e:
            logger.warning(f"Failed to play music: {e}")

    def stop_music(self):
        """Stop current background music."""
        if not self.mixer_initialized:
            return

        try:
            pygame.mixer.music.stop()
            self.current_music = None
        except Exception as e:
            logger.warning(f"Failed to stop music: {e}")

    def set_sfx_volume(self, vol):
        """
        Set SFX volume (0.0 to 1.0).

        Args:
            vol: Volume level (clamped to 0.0-1.0)
        """
        self.sfx_volume = max(0.0, min(1.0, vol))
        for sound in self.sfx_sounds.values():
            try:
                sound.set_volume(self.sfx_volume)
            except Exception:
                pass

    def set_music_volume(self, vol):
        """
        Set music volume (0.0 to 1.0).

        Args:
            vol: Volume level (clamped to 0.0-1.0)
        """
        self.music_volume = max(0.0, min(1.0, vol))
        if self.mixer_initialized:
            try:
                pygame.mixer.music.set_volume(self.music_volume)
            except Exception:
                pass

    def get_music_files(self):
        """Return list of available music files."""
        return self.music_files.copy()

    def is_mixer_initialized(self):
        """Check if mixer was successfully initialized."""
        return self.mixer_initialized
