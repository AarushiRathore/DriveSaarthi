"""Emergency notifications: Twilio SMS when credentials are set, otherwise a local outbox log.

Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM (your Twilio number) to send real SMS.
Every attempt, sent or simulated, is appended to <log_dir>/notifications.log.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime


class Notifier:
    def send(self, to: str, body: str, log_dir: str = "logs", on_done=None):
        """Fire-and-forget so the monitoring loop never waits on the network."""
        threading.Thread(target=self._send, args=(to, body, log_dir, on_done), daemon=True).start()

    def send_now(self, to: str, body: str, log_dir: str = "logs") -> str:
        return self._send(to, body, log_dir, None)

    def _send(self, to, body, log_dir, on_done) -> str:
        sid, tok, frm = (os.getenv(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"))
        status = "simulated (Twilio credentials not set)"
        if sid and tok and frm:
            for attempt in range(2):
                try:
                    from twilio.rest import Client
                    Client(sid, tok).messages.create(to=to, from_=frm, body=body)
                    status = "SMS sent"
                    break
                except Exception as exc:
                    status = f"failed: {exc}"
                    time.sleep(1.5)
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "notifications.log"), "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | to {to} | {status}\n    {body}\n")
        if on_done:
            on_done(status)
        return status
