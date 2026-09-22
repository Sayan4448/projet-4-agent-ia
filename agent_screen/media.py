"""Bounded media observations for editing workflows."""
import base64
import mimetypes
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import time

from .ai_client import chat_with_fallback, AIError

MAX_MOTION_SECONDS = 6.0
MAX_MOTION_FRAMES = 4
MAX_AUDIO_BYTES = 20 * 1024 * 1024
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}

MAX_VIDEO_SECONDS = 30.0
MAX_VIDEO_FPS = 15


def _ffmpeg_exe() -> str:
    """Path to a usable ffmpeg: the bundled imageio-ffmpeg binary first, then
    any ffmpeg on PATH. Returns '' when no encoder is available."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:  # noqa: BLE001 - optional encoder
        pass
    return shutil.which("ffmpeg") or ""


def record_video(capture, seconds=5, fps=8, out_dir=None, stop_event=None):
    """Record a real screen video (MP4, H.264) and return its path.

    `capture` is a callable returning a PIL RGB image (display.capture_frame).
    The clip is saved to `out_dir` (default: data/recordings) and can be dropped
    straight into Premiere Pro / CapCut / DaVinci Resolve. Bounded in duration
    and framerate, and stoppable like every other observation.
    """
    duration = max(1.0, min(MAX_VIDEO_SECONDS, float(seconds or 5)))
    fps = max(2, min(MAX_VIDEO_FPS, int(fps or 8)))
    exe = _ffmpeg_exe()
    if not exe:
        raise RuntimeError(
            "Encodage vidéo indisponible : ffmpeg introuvable. Réinstalle l'application "
            "ou installe ffmpeg pour activer record_video.")
    if out_dir is None:
        from .paths import recordings_dir
        out_dir = recordings_dir()
    out_dir = Path(str(out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    target = out_dir / f"rec_{stamp}.mp4"
    interval = 1.0 / fps
    count = max(1, int(round(duration * fps)))

    with tempfile.TemporaryDirectory() as tmp:
        frames_dir = Path(tmp)
        n = 0
        for i in range(count):
            if stop_event is not None and stop_event.is_set():
                break
            t0 = time.monotonic()
            try:
                frame = capture()
            except Exception:  # noqa: BLE001 - a locked desktop must not crash the run
                break
            frame.convert("RGB").save(frames_dir / f"frame_{i:04d}.jpg",
                                      "JPEG", quality=88)
            n += 1
            if i + 1 < count:
                delay = max(0.0, interval - (time.monotonic() - t0))
                if stop_event is not None:
                    if stop_event.wait(delay):
                        break
                else:
                    time.sleep(delay)
        if n == 0:
            raise RuntimeError("Aucune image capturée pour la vidéo (écran verrouillé ?).")

        cmd = [exe, "-y", "-framerate", str(fps), "-i", str(frames_dir / "frame_%04d.jpg"),
               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(target)]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f"Encodage vidéo échoué : {e}") from e
        if res.returncode != 0 or not target.is_file():
            detail = (res.stderr or b"").decode("utf-8", "replace")[-300:]
            raise RuntimeError(f"Encodage vidéo échoué (ffmpeg) : {detail.strip()}")

    return {"ok": True, "path": str(target), "file": target.name,
            "seconds": round(n / fps, 2), "fps": fps, "frames": n}


def capture_motion(capture, seconds=5, stop_event=None):
    """Take at most four sparse frames; no video file or background recording."""
    duration = max(1.0, min(MAX_MOTION_SECONDS, float(seconds or 5)))
    count = min(MAX_MOTION_FRAMES, max(2, int(round(duration / 2)) + 1))
    frames = []
    interval = duration / (count - 1)
    for index in range(count):
        if stop_event is not None and stop_event.is_set():
            break
        frames.append(capture())
        if index + 1 < count:
            if stop_event is not None:
                if stop_event.wait(interval):
                    break
            else:
                time.sleep(interval)
    return frames, duration


def analyze_audio(path, provider, prompt, stop_event=None, max_tokens=500):
    """Analyze an explicit local audio file. Gemini audio models are supported.

    No microphone or permanent listening is performed. Other provider schemas vary
    too much to silently upload a file in a format they may misinterpret.
    """
    source = Path(str(path or "")).expanduser().resolve()
    if source.suffix.lower() not in AUDIO_EXTENSIONS or not source.is_file():
        raise ValueError("Fichier audio introuvable ou format non accepté (mp3, wav, m4a, aac, ogg, flac, opus).")
    size = source.stat().st_size
    if size <= 0 or size > MAX_AUDIO_BYTES:
        raise ValueError("Audio vide ou trop volumineux (maximum 20 Mo). Découpe-le avant l’analyse.")
    if provider != "gemini":
        raise AIError("L’analyse audio intégrée nécessite actuellement Gemini et un modèle compatible audio.")
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    mime = mimetypes.guess_type(source.name)[0] or "audio/mpeg"
    request = (str(prompt or "Transcris et résume cet audio pour préparer le montage.")[:1000]
               + " Réponds brièvement avec transcription utile, silences, rythme et points de coupe.")
    text, used = _call_gemini_audio(encoded, mime, provider, request, stop_event, max_tokens)
    return {"ok": True, "provider": used, "analysis": text[:6000],
            "file": source.name, "bytes": size}


def _call_gemini_audio(encoded, mime, provider, request, stop_event, max_tokens):
    """Kept separate so tests can prove no hidden fallback or microphone use."""
    return chat_with_fallback(provider, request,
                              system="Tu aides au montage audio/vidéo. Sois factuel et concis.",
                              b64_png=encoded, mime=mime, max_tokens=max_tokens,
                              cancel_event=stop_event, allow_fallback=False)
