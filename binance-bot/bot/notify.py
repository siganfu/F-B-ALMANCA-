"""Telegram bildirimleri. Hiçbir Telegram hatası botu durdurmaz."""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

import requests

log = logging.getLogger("bot.telegram")

TURLER = ("islem_acilisi", "hatalar", "gunluk_limit", "ozet")


class Bildirici:
    def __init__(self, t: dict, mod: str = "kagit",
                 gonderici: Optional[Callable[..., object]] = None):
        self.t = t or {}
        self.mod = mod
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self._post = gonderici or requests.post
        self.aktif = bool(self.t.get("aktif")) and bool(self.token) and bool(self.chat_id)
        if self.t.get("aktif") and not self.aktif:
            log.warning("Telegram açık ama TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID .env'de eksik; bildirim gönderilmeyecek.")

    def gonder(self, metin: str, tur: str) -> bool:
        """tur: islem_acilisi | hatalar | gunluk_limit | ozet. Başarılıysa True."""
        if not self.aktif or not self.t.get(tur, True):
            return False
        etiket = {"kagit": "📝 KAĞIT", "demo": "🧪 DEMO", "gercek": "💰 GERÇEK"}.get(self.mod, self.mod)
        govde = f"[{etiket}] {metin}"[:4000]
        try:
            yanit = self._post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": govde, "disable_web_page_preview": True},
                timeout=10,
            )
            durum = getattr(yanit, "status_code", 200)
            if durum != 200:
                log.warning("Telegram gönderilemedi: HTTP %s %s", durum, getattr(yanit, "text", "")[:200])
                return False
            return True
        except Exception as e:  # noqa: BLE001 — Telegram hatası asla botu durdurmamalı
            log.warning("Telegram hatası (yok sayıldı): %s", e)
            return False
