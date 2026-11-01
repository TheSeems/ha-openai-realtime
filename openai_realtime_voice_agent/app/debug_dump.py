"""TheSeems fork: per-turn WAV dumps of the mic audio, to hear what OpenAI actually got.

Between two input_audio_buffer.clear messages (wake, flush, interrupt) we keep the raw 16 kHz audio from the
device and the exact 24 kHz audio sent in input_audio_buffer.append, and write both to /media/rt-debug when
the buffer is cleared. Only the newest KEEP pairs stay. Needs the add-on's `media` map; without it, a no-op.
"""
import base64
import logging
import os
import time
import wave

logger = logging.getLogger(__name__)

DIR = "/media/rt-debug"
KEEP = 20
MAX_SECONDS = 60

_raw = bytearray()
_sent = bytearray()
_marks: list[str] = []
_started = 0.0
_enabled = os.path.isdir("/media")


def add_raw(audio: bytes) -> None:
    global _started
    if not _enabled:
        return
    if not _raw and not _sent:
        _started = time.monotonic()
    _raw.extend(audio)
    if len(_raw) > 16000 * 2 * MAX_SECONDS:
        cut("long")


def add_sent(audio_b64: str) -> None:
    if _enabled and audio_b64:
        try:
            _sent.extend(base64.b64decode(audio_b64))
        except Exception:
            pass


def mark(what: str) -> None:
    """Note an event with its offset into the sent audio (seconds), saved next to the WAVs."""
    if _enabled and (_raw or _sent):
        _marks.append(f"{len(_sent) / 48000:6.2f}s sent / {len(_raw) / 32000:6.2f}s raw  {what}")


def _write(path: str, data: bytes, rate: int) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(data[: len(data) // 2 * 2]))


def cut(reason: str) -> None:
    if not _enabled:
        return
    try:
        if len(_raw) >= 16000 * 2 // 2 or len(_sent) >= 24000 * 2 // 2:
            os.makedirs(DIR, exist_ok=True)
            stem = os.path.join(DIR, time.strftime("%Y%m%d-%H%M%S") + f"-{reason}")
            _write(stem + "-raw16k.wav", _raw, 16000)
            _write(stem + "-sent24k.wav", _sent, 24000)
            with open(stem + ".txt", "w") as f:
                f.write("\n".join(_marks) + "\n")
            logger.info(f"🎞️ dumped turn audio: {os.path.basename(stem)} raw {len(_raw) / 32000:.1f}s, "
                        f"sent {len(_sent) / 48000:.1f}s")
            files = sorted(f for f in os.listdir(DIR) if f.endswith(".txt"))
            for old in files[:-KEEP]:
                for suffix in (".txt", "-raw16k.wav", "-sent24k.wav"):
                    try:
                        os.remove(os.path.join(DIR, old[:-4] + suffix))
                    except OSError:
                        pass
    except Exception as e:
        logger.warning(f"⚠️ turn audio dump failed: {e!r}")
    finally:
        _raw.clear()
        _sent.clear()
        _marks.clear()
