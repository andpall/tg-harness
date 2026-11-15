"""Voice messages -> text via faster-whisper (loaded lazily: heavy import and model)."""
import tempfile, urllib.request
from . import config, telegram

_whisper = None


def transcribe(file_id):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(config.CFG.get("whisper_model", "medium"), compute_type="int8")
    file_path = telegram.tg("getFile", file_id=file_id)["file_path"]
    with tempfile.NamedTemporaryFile(suffix=".oga") as audio_file:
        url = f"https://api.telegram.org/file/bot{config.TOKEN}/{file_path}"
        with urllib.request.urlopen(url, timeout=70) as response:
            audio_file.write(response.read())
        audio_file.flush()
        segments, _info = _whisper.transcribe(audio_file.name)
        return " ".join(segment.text.strip() for segment in segments)
