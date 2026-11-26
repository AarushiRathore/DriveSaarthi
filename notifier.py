"""
notifier.py – Emergency SMS dispatch for DriveSaarthi.

Supports Fast2SMS, MSG91, and Twilio.  All three are optional; if none are
configured the message is logged to a local file so the app still runs.

Usage in backend.py
-------------------
    from notifier import IST, Notifier

    n = Notifier()

    # Fire-and-forget (spawns a daemon thread):
    n.send(phone, kind, vals, log_dir, callback=lambda status: ...)

    # Blocking – returns a human-readable status string:
    status = n.send_now(phone, text, log_dir)

Environment variables (all optional)
--------------------------------------
    FAST2SMS_KEY    – Fast2SMS API key  (https://www.fast2sms.com)
    MSG91_AUTHKEY   – MSG91 auth-key    (https://msg91.com)
    MSG91_SENDER    – 6-char sender ID  (default "DRVSRT")
    TWILIO_SID      – Twilio account SID
    TWILIO_TOKEN    – Twilio auth token
    TWILIO_FROM     – Twilio source number (e.g. +14155552671)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta

# Indian Standard Time  (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30), "IST")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------
_TEMPLATES: dict[str, str] = {
    "alert": (
        "⚠️ DriveSaarthi ALERT\n"
        "Driver : {0}\n"
        "Speed  : {1} km/h (limit {2} km/h)\n"
        "Duration: {3}\n"
        "Location: {4}\n"
        "Time    : {5}"
    ),
    "update": (
        "✅ DriveSaarthi UPDATE\n"
        "Driver : {0}\n"
        "Speed is now within the {1} km/h limit.\n"
        "Overspeed duration: {2}\n"
        "Location: {3}"
    ),
}


def _fmt(kind: str, vals: list[str]) -> str:
    tpl = _TEMPLATES.get(kind, "{0}")
    try:
        return tpl.format(*vals)
    except IndexError:
        return tpl


# ---------------------------------------------------------------------------
# Gateway implementations
# ---------------------------------------------------------------------------

def _send_fast2sms(phone: str, text: str) -> str:
    """Fast2SMS DLT / developer route.  Requires FAST2SMS_KEY env var."""
    import requests  # noqa: PLC0415

    key = os.environ.get("FAST2SMS_KEY", "")
    if not key:
        raise EnvironmentError("FAST2SMS_KEY not set")

    # Fast2SMS expects a plain 10-digit number for Indian numbers
    number = phone.lstrip("+").lstrip("91") if phone.startswith("+91") else phone.lstrip("+")
    resp = requests.post(
        "https://www.fast2sms.com/dev/bulkV2",
        headers={"authorization": key, "Content-Type": "application/json"},
        json={"route": "v3", "sender_id": "TXTIND", "message": text,
              "language": "english", "flash": 0, "numbers": number},
        timeout=10,
    )
    data = resp.json()
    if data.get("return"):
        return f"Fast2SMS OK – request_id={data.get('request_id', '?')}"
    raise RuntimeError(f"Fast2SMS error: {data.get('message', data)}")


def _send_msg91(phone: str, text: str) -> str:
    """MSG91 SMS.  Requires MSG91_AUTHKEY env var."""
    import requests  # noqa: PLC0415

    key    = os.environ.get("MSG91_AUTHKEY", "")
    sender = os.environ.get("MSG91_SENDER", "DRVSRT")
    if not key:
        raise EnvironmentError("MSG91_AUTHKEY not set")

    # MSG91 wants country-code prefixed number without '+'
    number = phone.lstrip("+")
    resp = requests.post(
        "https://api.msg91.com/api/v5/flow/",
        headers={"authkey": key, "Content-Type": "application/json"},
        json={
            "template_id": "",           # leave blank for plain transactional
            "sender":  sender,
            "mobiles": number,
            "body":    text,
        },
        timeout=10,
    )
    data = resp.json()
    if data.get("type") == "success":
        return f"MSG91 OK – {data.get('message', '')}"
    raise RuntimeError(f"MSG91 error: {data}")


def _send_twilio(phone: str, text: str) -> str:
    """Twilio SMS.  Requires TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM env vars."""
    sid   = os.environ.get("TWILIO_SID", "")
    token = os.environ.get("TWILIO_TOKEN", "")
    frm   = os.environ.get("TWILIO_FROM", "")
    if not (sid and token and frm):
        raise EnvironmentError("TWILIO_SID / TWILIO_TOKEN / TWILIO_FROM not set")
    try:
        from twilio.rest import Client  # noqa: PLC0415
        msg = Client(sid, token).messages.create(body=text, from_=frm, to=phone)
        return f"Twilio OK – {msg.sid}"
    except ImportError as exc:
        raise ImportError("twilio package not installed (pip install twilio)") from exc


# ---------------------------------------------------------------------------
# Log-only fallback
# ---------------------------------------------------------------------------

def _log_only(phone: str, text: str, log_dir: str) -> str:
    """When no SMS gateway is configured, write the message to a local file."""
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "sms_log.txt")
    stamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    entry = f"\n[{stamp}] TO: {phone}\n{text}\n{'-'*60}"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(entry)
    return f"[No SMS gateway configured] Message logged to {path}"


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class Notifier:
    """
    Thin wrapper that tries each configured gateway in order:
      Fast2SMS → MSG91 → Twilio → log-only fallback.
    """

    def send_now(self, phone: str, text: str, log_dir: str = "logs") -> str:
        """Blocking send.  Returns a human-readable status string."""
        gateways = []
        if os.environ.get("FAST2SMS_KEY"):
            gateways.append(("Fast2SMS", _send_fast2sms))
        if os.environ.get("MSG91_AUTHKEY"):
            gateways.append(("MSG91", _send_msg91))
        if os.environ.get("TWILIO_SID"):
            gateways.append(("Twilio", _send_twilio))

        last_err = ""
        for name, fn in gateways:
            try:
                status = fn(phone, text)
                logger.info("SMS sent via %s to %s", name, phone)
                return status
            except Exception as exc:
                last_err = f"{name}: {exc}"
                logger.warning("SMS gateway %s failed: %s", name, exc)

        # No gateway worked (or none configured)
        fallback = _log_only(phone, text, log_dir)
        if last_err:
            return f"{fallback} | Last gateway error: {last_err}"
        return fallback

    def send(
        self,
        phone: str,
        kind: str,
        vals: list[str],
        log_dir: str = "logs",
        callback=None,
    ) -> None:
        """
        Non-blocking send.  Formats *kind* template with *vals*, then
        dispatches in a daemon thread.  Calls ``callback(status_str)`` on
        completion if provided.
        """
        text = _fmt(kind, vals)

        def _work():
            status = self.send_now(phone, text, log_dir)
            if callback:
                try:
                    callback(status)
                except Exception:
                    pass

        t = threading.Thread(target=_work, daemon=True, name="notifier-send")
        t.start()
