"""Voice messages -> text via faster-whisper (loaded lazily: heavy import and model)."""
import os
from . import config, telegram

_whisper = None


def transcribe(file_id):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(config.CFG.get("whisper_model", "medium"), compute_type="int8")
    path = telegram.save_file(file_id, ".oga")
    try:
        segments, _info = _whisper.transcribe(path)
        return " ".join(segment.text.strip() for segment in segments)
    finally:
        os.remove(path)
