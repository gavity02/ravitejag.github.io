"""Audio Agent - Generates narration and background music for videos.

Produces two audio assets:
1. Narration: Uses edge-tts (free Microsoft TTS) to synthesize speech
   for each scene's narration text.
2. Background music: Procedurally generated sine-wave melodies
   (pentatonic / major scale) so the entire pipeline stays $0-cost.

The generated AudioAsset is stored on context.audio for the
downstream VideoComposerAgent.
"""

from __future__ import annotations

import asyncio
import math
import random
import struct
import wave
from pathlib import Path
from typing import Any

import edge_tts

from ..core.base_agent import BaseAgent
from ..core.bus import EventType
from ..core.models import AudioAsset, PipelineContext, Script


# ---------------------------------------------------------------------------
# Musical constants
# ---------------------------------------------------------------------------

# Frequencies in Hz for the C4-based pentatonic scale (C D E G A)
PENTATONIC_SCALE: list[float] = [
    261.63,  # C4
    293.66,  # D4
    329.63,  # E4
    392.00,  # G4
    440.00,  # A4
]

# C-major scale (C4 through B4)
MAJOR_SCALE: list[float] = [
    261.63,  # C4
    293.66,  # D4
    329.63,  # E4
    349.23,  # F4
    392.00,  # G4
    440.00,  # A4
    493.88,  # B4
]

# Playful mix: major scale plus a higher octave root
PLAYFUL_SCALE: list[float] = [
    261.63,  # C4
    293.66,  # D4
    329.63,  # E4
    349.23,  # F4
    392.00,  # G4
    440.00,  # A4
    493.88,  # B4
    523.25,  # C5
]

# Tempo ranges per style (min BPM, max BPM)
STYLE_TEMPO: dict[str, tuple[int, int]] = {
    "calm": (60, 80),
    "upbeat": (100, 120),
    "playful": (90, 110),
}

# Scale mapping per style
STYLE_SCALE: dict[str, list[float]] = {
    "calm": PENTATONIC_SCALE,
    "upbeat": MAJOR_SCALE,
    "playful": PLAYFUL_SCALE,
}

# Average words-per-second for rough narration duration estimation.
# Baby-content speech is deliberately slow (~2.5 wps).
_WORDS_PER_SECOND: float = 2.5


class AudioAgent(BaseAgent):
    """Generates narration audio and procedural background music.

    Narration is synthesised with *edge-tts* (Microsoft Edge's free
    cloud TTS).  Background music is a simple sine-wave melody written
    directly to a WAV file using the ``wave`` and ``struct`` stdlib
    modules, keeping external dependencies (and costs) at zero.
    """

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "audio"

    @property
    def completion_event_type(self) -> EventType:
        return EventType.AUDIO_GENERATED

    # ------------------------------------------------------------------
    # Checkpoint validation
    # ------------------------------------------------------------------

    def _validate_checkpoint(self, data: dict[str, Any]) -> bool:
        """Accept checkpoint only when audio data is present."""
        return data.get("audio") is not None

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    async def _execute(self, context: PipelineContext) -> PipelineContext:
        """Generate narration and background music for every scene."""
        script: Script | None = context.script
        if script is None:
            raise ValueError(
                "No script found in context - scriptwriter agent must run first"
            )

        video_id: str = context.video_id

        # Prepare output directory
        audio_dir: Path = self._ensure_dir(
            Path(self.config.output_dir) / video_id / "audio"
        )

        # --- 1. Narration --------------------------------------------------
        narration_segments: list[dict[str, Any]] = []
        total_narration_duration: float = 0.0

        for scene in script.scenes:
            if not scene.narration_text.strip():
                self.logger.debug(
                    "Scene %d has no narration text, skipping TTS",
                    scene.scene_number,
                )
                continue

            segment = await self._generate_narration(
                text=scene.narration_text,
                scene_number=scene.scene_number,
                output_dir=audio_dir,
            )
            narration_segments.append(segment)
            total_narration_duration += segment["duration"]

        self.logger.info(
            "Generated %d narration segments (%.1fs total)",
            len(narration_segments),
            total_narration_duration,
        )

        # --- 2. Background music -------------------------------------------
        music_style: str = script.music_style or "upbeat"
        # Use the script's declared duration, but fall back to narration length
        target_duration: float = (
            script.total_duration_seconds
            if script.total_duration_seconds > 0
            else max(total_narration_duration, 30.0)
        )

        music_path: Path = audio_dir / "background_music.wav"
        self._generate_music(
            style=music_style,
            duration_seconds=target_duration,
            output_path=music_path,
        )
        self.logger.info(
            "Generated %.1fs of '%s' background music -> %s",
            target_duration,
            music_style,
            music_path,
        )

        # --- 3. Build the AudioAsset --------------------------------------
        # Determine the full-narration path (the composer will concatenate
        # the individual segments; we record the intended output location).
        full_narration_path: Path = audio_dir / "full_narration.mp3"

        context.audio = AudioAsset(
            video_id=video_id,
            narration_path=full_narration_path,
            music_path=music_path,
            narration_segments=narration_segments,
            total_duration_seconds=max(total_narration_duration, target_duration),
        )

        return context

    # ------------------------------------------------------------------
    # Narration helpers
    # ------------------------------------------------------------------

    async def _generate_narration(
        self,
        text: str,
        scene_number: int,
        output_dir: Path,
    ) -> dict[str, Any]:
        """Synthesise narration for a single scene using edge-tts.

        Returns a segment dict compatible with ``AudioAsset.narration_segments``.
        """
        voice: str = self.config.tts.voice
        rate: str = self.config.tts.rate

        output_path: Path = output_dir / f"scene_{scene_number}.mp3"

        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(str(output_path))

        # Estimate duration from word count (edge-tts doesn't expose
        # duration metadata directly without parsing the audio).
        word_count: int = len(text.split())
        estimated_duration: float = max(word_count / _WORDS_PER_SECOND, 1.0)

        self.logger.debug(
            "Scene %d narration: %d words, ~%.1fs -> %s",
            scene_number,
            word_count,
            estimated_duration,
            output_path,
        )

        return {
            "scene": scene_number,
            "path": str(output_path),
            "duration": estimated_duration,
        }

    # ------------------------------------------------------------------
    # Procedural music generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_tone(
        frequency: float,
        duration: float,
        sample_rate: int = 44100,
        volume: float = 0.3,
    ) -> bytes:
        """Generate raw PCM bytes for a sine-wave tone.

        Parameters
        ----------
        frequency:
            Tone frequency in Hz.
        duration:
            Length of the tone in seconds.
        sample_rate:
            Audio sample rate (samples per second).
        volume:
            Amplitude multiplier in [0.0, 1.0].

        Returns
        -------
        bytes
            Packed 16-bit signed little-endian PCM samples.
        """
        num_samples: int = int(sample_rate * duration)
        max_amplitude: int = 32767  # max value for 16-bit signed int
        amplitude: float = max_amplitude * min(max(volume, 0.0), 1.0)

        samples: list[bytes] = []
        for i in range(num_samples):
            t: float = i / sample_rate
            # Basic sine wave with a gentle amplitude envelope
            # (fade-in / fade-out) to avoid clicks between notes.
            envelope: float = 1.0
            fade_samples: int = min(int(sample_rate * 0.02), num_samples // 2)
            if i < fade_samples:
                envelope = i / fade_samples
            elif i > num_samples - fade_samples:
                envelope = (num_samples - i) / fade_samples

            value: float = amplitude * envelope * math.sin(
                2.0 * math.pi * frequency * t
            )
            samples.append(struct.pack("<h", int(value)))

        return b"".join(samples)

    def _generate_music(
        self,
        style: str,
        duration_seconds: float,
        output_path: Path,
    ) -> None:
        """Generate procedural background music and write it to a WAV file.

        The melody is a random sequence of notes drawn from a scale that
        depends on the requested *style* (``calm``, ``upbeat``, or
        ``playful``).
        """
        sample_rate: int = 44100
        num_channels: int = 1  # mono
        sample_width: int = 2  # 16-bit

        # Resolve style parameters
        scale: list[float] = STYLE_SCALE.get(style, PENTATONIC_SCALE)
        tempo_min, tempo_max = STYLE_TEMPO.get(style, (90, 110))
        tempo_bpm: int = random.randint(tempo_min, tempo_max)

        # Beat duration determines the base note length.  We randomise
        # individual notes between 0.5x and 1.0x of a beat to add variety.
        beat_duration: float = 60.0 / tempo_bpm

        self.logger.debug(
            "Music generation: style=%s, tempo=%d BPM, beat=%.2fs, target=%.1fs",
            style,
            tempo_bpm,
            beat_duration,
            duration_seconds,
        )

        # Build the melody as raw PCM bytes
        pcm_data: list[bytes] = []
        elapsed: float = 0.0

        while elapsed < duration_seconds:
            frequency: float = random.choice(scale)

            # Note duration: between half a beat and a full beat
            note_duration: float = beat_duration * random.uniform(0.5, 1.0)

            # Don't overshoot the target duration
            note_duration = min(note_duration, duration_seconds - elapsed)
            if note_duration <= 0:
                break

            tone_bytes: bytes = self._generate_tone(
                frequency=frequency,
                duration=note_duration,
                sample_rate=sample_rate,
                volume=0.3,
            )
            pcm_data.append(tone_bytes)
            elapsed += note_duration

        # Write the WAV file
        raw_audio: bytes = b"".join(pcm_data)

        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(num_channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(raw_audio)

        self.logger.debug(
            "Wrote %d bytes of PCM data to %s", len(raw_audio), output_path
        )
