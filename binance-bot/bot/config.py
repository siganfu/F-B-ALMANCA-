"""config.yaml ve .env dosyalarını okur, temel doğrulamaları yapar."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Proje kök klasörü (binance-bot/)
KOK = Path(__file__).resolve().parent.parent

GECERLI_MODLAR = {"kagit", "demo", "gercek"}


class AyarHatasi(Exception):
    """config.yaml veya .env içinde geçersiz / eksik ayar."""


def ayarlari_yukle(yol: str | Path | None = None) -> dict[str, Any]:
    """config.yaml'ı okur, .env'i ortam değişkenlerine yükler ve doğrular."""
    load_dotenv(KOK / ".env")
    yol = Path(yol) if yol else KOK / "config.yaml"
    if not yol.is_absolute():
        yol = KOK / yol
    if not yol.exists():
        raise AyarHatasi(f"Ayar dosyası bulunamadı: {yol}")
    with open(yol, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    ayarlari_dogrula(cfg)
    return cfg


def ayarlari_dogrula(cfg: dict[str, Any]) -> None:
    """Kritik ayarları kontrol eder; hatalıysa AyarHatasi fırlatır."""
    mod = cfg.get("mod", "kagit")
    if mod not in GECERLI_MODLAR:
        raise AyarHatasi(f"Geçersiz mod: {mod!r}. Seçenekler: {sorted(GECERLI_MODLAR)}")
    if mod == "gercek" and cfg.get("gercek_para_onayi") is not True:
        raise AyarHatasi(
            "mod: gercek seçili ama gercek_para_onayi: true değil. "
            "Gerçek parayla çalışmak için config.yaml'da bunu bilinçli olarak açın."
        )
    if not cfg.get("coinler"):
        raise AyarHatasi("coinler listesi boş.")
    for c in cfg["coinler"]:
        if "sembol" not in c or "max_kaldirac" not in c:
            raise AyarHatasi(f"Coin tanımı eksik: {c}")
        if not (1 <= int(c["max_kaldirac"]) <= 125):
            raise AyarHatasi(f"{c['sembol']} için max_kaldirac geçersiz: {c['max_kaldirac']}")
    for bolum in ("strateji", "risk", "claude", "telegram", "kayit"):
        if bolum not in cfg:
            raise AyarHatasi(f"config.yaml içinde '{bolum}' bölümü eksik.")
    if cfg["claude"].get("kullanim") not in ("kapali", "onay"):
        raise AyarHatasi("claude.kullanim 'kapali' veya 'onay' olmalı.")
    if cfg["claude"].get("ulasilamazsa") not in ("bekle", "kurallar"):
        raise AyarHatasi("claude.ulasilamazsa 'bekle' veya 'kurallar' olmalı.")
    r = cfg["risk"]
    if not (0 < r["islem_basi_risk"] <= 0.05):
        raise AyarHatasi("risk.islem_basi_risk 0 ile 0.05 arasında olmalı.")
    if r.get("marjin_modu", "isolated") != "isolated":
        raise AyarHatasi("Bu bot yalnızca isolated marjin moduyla çalışır.")


def api_anahtarlari() -> tuple[str, str]:
    """.env'den Binance anahtarlarını döner (boş olabilir)."""
    return os.getenv("BINANCE_API_KEY", "").strip(), os.getenv("BINANCE_API_SECRET", "").strip()


def kok_yolu(goreli: str) -> Path:
    """Config'teki göreli yolu proje köküne göre mutlak yola çevirir."""
    p = Path(goreli)
    return p if p.is_absolute() else KOK / p
