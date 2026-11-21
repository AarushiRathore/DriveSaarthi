"""Spoken warnings through offline text-to-speech (pyttsx3) on the in-vehicle machine. Never blocks the monitor."""
from __future__ import annotations

import importlib.util
import queue
import threading

PHONE_STAGES = [
    {"en": "Please put the phone down and keep your eyes on the road.",
     "hi": "कृपया फ़ोन नीचे रखें और सड़क पर ध्यान दें।"},
    {"en": "You are still using your phone. Please stop. If it is urgent, pull over safely before using it.",
     "hi": "आप अभी भी फ़ोन इस्तेमाल कर रहे हैं। कृपया इस्तेमाल बंद करें। ज़रूरी हो, तो गाड़ी सुरक्षित जगह रोककर ही बात करें।"},
    {"en": "Phone use has continued for {sec} seconds. Please slow down and stop at the next safe place.",
     "hi": "फ़ोन का इस्तेमाल {sec} सेकंड से जारी है। कृपया गाड़ी धीमी करें और अगली सुरक्षित जगह पर रोक लें।"},
]


def phone_message(stage: int, seconds: float) -> dict:
    """Wording escalates with each warning the driver ignores."""
    m = PHONE_STAGES[min(max(stage, 1), len(PHONE_STAGES)) - 1]
    return {k: v.format(sec=int(seconds)) for k, v in m.items()}


class VoiceAlert:
    """say() returns immediately; a worker thread speaks. One message may wait, extras are dropped."""

    def __init__(self, lang=lambda: "en", speaker=None, sync: bool = False):
        self.lang, self.speaker, self.sync = lang, speaker, sync
        self.history: list[str] = []
        self._q: queue.Queue = queue.Queue(maxsize=1)
        self._worker_started = False

    @property
    def available(self) -> bool:
        return self.speaker is not None or importlib.util.find_spec("pyttsx3") is not None

    def say(self, texts: dict) -> bool:
        if self.sync:
            return self._speak(texts, None, None, None)
        try:
            self._q.put_nowait(texts)
        except queue.Full:
            return False
        if not self._worker_started:
            self._worker_started = True
            threading.Thread(target=self._worker, daemon=True, name="voice").start()
        return True

    def _worker(self):
        eng = en_id = hi_id = None
        if self.speaker is None:
            try:
                import pyttsx3
                eng = pyttsx3.init()
                en_id = eng.getProperty("voice")
                for v in eng.getProperty("voices"):
                    langs = [(l.decode(errors="ignore") if isinstance(l, bytes) else str(l)).lower() for l in v.languages]
                    if "hindi" in v.name.lower() or any(l.startswith("hi") for l in langs):
                        hi_id = v.id
                        break
            except Exception:
                eng = None
        while True:
            self._speak(self._q.get(), eng, en_id, hi_id)

    def _speak(self, texts, eng, en_id, hi_id) -> bool:
        use_hi = self.lang() == "hi" and (self.speaker is not None or hi_id is not None)
        text = texts["hi"] if use_hi else texts["en"]
        self.history.append(text)
        try:
            if self.speaker:
                self.speaker(text)
            elif eng:
                eng.setProperty("voice", hi_id if use_hi else en_id)
                eng.say(text)
                eng.runAndWait()
            else:
                return False
        except Exception:
            return False
        return True
