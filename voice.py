
from __future__ import annotations

import os
import platform
import queue
import shutil
import subprocess
import threading

PHONE_STAGES = [
    {"en": "Please put the phone down and keep your eyes on the road.",
     "hi": "कृपया फ़ोन नीचे रखें और सड़क पर ध्यान दें।"},
    {"en": "You are still using your phone. Please stop. If it is urgent, pull over safely before using it.",
     "hi": "आप अभी भी फ़ोन इस्तेमाल कर रहे हैं। कृपया इस्तेमाल बंद करें। ज़रूरी हो, तो गाड़ी सुरक्षित जगह रोककर ही बात करें।"},
    {"en": "Phone use has continued for {sec} seconds. Please slow down and stop at the next safe place.",
     "hi": "फ़ोन का इस्तेमाल {sec} सेकंड से जारी है। कृपया गाड़ी धीमी करें और अगली सुरक्षित जगह पर रोक लें।"},
]
SPEED_STAGES = [
    {"en": "You are over the speed limit. Please slow down.",
     "hi": "आप गति सीमा से ऊपर हैं। कृपया गाड़ी धीमी करें।"},
    {"en": "You are still driving at {speed} kilometres per hour, above the limit of {limit}. Please reduce your speed now.",
     "hi": "आप अभी भी {speed} किलोमीटर प्रति घंटे की रफ़्तार पर हैं, जो सीमा {limit} से ज़्यादा है। कृपया अभी गति कम करें।"},
    {"en": "You have been over the speed limit for {sec} seconds. Please slow down and keep a safe distance.",
     "hi": "आप {sec} सेकंड से गति सीमा से ऊपर चल रहे हैं। कृपया गाड़ी धीमी करें और सुरक्षित दूरी बनाए रखें।"},
]
STAGES = {"phone": PHONE_STAGES, "speed": SPEED_STAGES}


def message(param: str, stage: int, sec: float = 0, speed: float = 0, limit: float = 0) -> dict | None:
    """Wording that escalates with each warning the driver ignores. None if this parameter has no voice text."""
    table = STAGES.get(param)
    if not table:
        return None
    m = table[min(max(stage, 1), len(table)) - 1]
    return {k: v.format(sec=int(sec), speed=int(round(speed)), limit=int(round(limit))) for k, v in m.items()}


def phone_message(stage: int, seconds: float) -> dict:         # kept for older callers
    return message("phone", stage, sec=seconds)


_PS = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
       "$t = $env:VOICE_EN; if ($env:VOICE_HI_WANTED -eq '1') { "
       "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'hi*' } | Select-Object -First 1; "
       "if ($v) { $s.SelectVoice($v.VoiceInfo.Name); $t = $env:VOICE_HI } }; $s.Speak($t)")


def _run(cmd, env=None):
    kw = {"creationflags": 0x08000000} if platform.system() == "Windows" else {}      # no console window
    subprocess.run(cmd, env=env, timeout=45, check=True, capture_output=True, **kw)


def _os_speak(texts: dict, want_hindi: bool):
    system = platform.system()
    if system == "Windows":
        env = {**os.environ, "VOICE_EN": texts["en"], "VOICE_HI": texts["hi"], "VOICE_HI_WANTED": "1" if want_hindi else "0"}
        return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS], env)
    if system == "Darwin":
        hi = want_hindi and "Lekha" in subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
        return _run(["say", *(["-v", "Lekha"] if hi else []), texts["hi"] if hi else texts["en"]])
    for tool in ("espeak-ng", "espeak"):
        if shutil.which(tool):
            hi = want_hindi and len(subprocess.run([tool, "--voices=hi"], capture_output=True, text=True).stdout.splitlines()) > 1
            return _run([tool, "-v", "hi" if hi else "en", texts["hi"] if hi else texts["en"]])
    if shutil.which("spd-say"):
        return _run(["spd-say", "-w", texts["en"]])
    raise RuntimeError("no speech tool found (install espeak-ng)")


def _pyttsx3_speak(texts: dict, want_hindi: bool):
    import pyttsx3
    eng = pyttsx3.init()                           # a fresh engine each time avoids the "speaks only once" bug
    text = texts["en"]
    if want_hindi:
        for v in eng.getProperty("voices"):
            langs = [(l.decode(errors="ignore") if isinstance(l, bytes) else str(l)).lower() for l in v.languages]
            if "hindi" in v.name.lower() or any(l.startswith("hi") for l in langs):
                eng.setProperty("voice", v.id)
                text = texts["hi"]
                break
    eng.say(text)
    eng.runAndWait()
    eng.stop()


class VoiceAlert:
    def __init__(self, lang=lambda: "en", speaker=None, sync: bool = False):
        self.lang, self.speaker, self.sync = lang, speaker, sync
        self.history: list[str] = []
        self.last_error = ""
        self._q: queue.Queue = queue.Queue(maxsize=1)
        self._started = False

    @property
    def available(self) -> bool:
        if self.speaker is not None:
            return True
        system = platform.system()
        if system == "Windows":
            return shutil.which("powershell") is not None
        if system == "Darwin":
            return shutil.which("say") is not None
        return any(shutil.which(t) for t in ("espeak-ng", "espeak", "spd-say")) or _has_pyttsx3()

    def say(self, texts: dict) -> bool:
        if self.sync:
            return self._speak(texts)
        try:
            self._q.put_nowait(texts)
        except queue.Full:
            return False
        if not self._started:
            self._started = True
            threading.Thread(target=self._worker, daemon=True, name="voice").start()
        return True

    def test(self) -> bool:
        """Blocking check you can run from a button or `python diagnose.py --speak`."""
        return self._speak({"en": "Voice warnings are working.", "hi": "आवाज़ चेतावनी काम कर रही है।"})

    def _worker(self):
        while True:
            self._speak(self._q.get())

    def _speak(self, texts: dict) -> bool:
        want_hi = self.lang() == "hi"
        self.history.append(texts["hi"] if want_hi and self.speaker else texts["en"])
        try:
            if self.speaker:
                self.speaker(texts["hi"] if want_hi else texts["en"])
            else:
                try:
                    _os_speak(texts, want_hi)
                except Exception as first:
                    if not _has_pyttsx3():
                        raise first
                    _pyttsx3_speak(texts, want_hi)
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            return False


def _has_pyttsx3() -> bool:
    import importlib.util
    return importlib.util.find_spec("pyttsx3") is not None
