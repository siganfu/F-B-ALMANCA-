"""Kayıt: SQLite (veri/gunluk.db) ve günlük log dosyaları (loglar/)."""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SEMA = """
CREATE TABLE IF NOT EXISTS kararlar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zaman TEXT NOT NULL,
    calisma_id TEXT,
    mod TEXT,
    sembol TEXT,
    mum_zamani TEXT,
    sinyal TEXT,
    sinyal_nedeni TEXT,
    gostergeler TEXT,
    giris REAL, stop REAL, kar_al REAL,
    miktar REAL, nominal REAL, kaldirac INTEGER,
    claude_karar TEXT, claude_guven REAL, claude_gerekce TEXT,
    risk_nedeni TEXT,
    islem_acildi INTEGER NOT NULL DEFAULT 0,
    emir_bilgisi TEXT,
    hata TEXT
);
CREATE TABLE IF NOT EXISTS gun_basi (
    tarih TEXT PRIMARY KEY,
    mod TEXT,
    bakiye REAL NOT NULL,
    kayit_zamani TEXT,
    limit_bildirildi INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS calismalar (
    calisma_id TEXT PRIMARY KEY,
    baslangic TEXT, bitis TEXT, mod TEXT,
    bakiye REAL, acik_pozisyon INTEGER, acilan_islem INTEGER,
    hata_sayisi INTEGER, ozet TEXT
);
CREATE TABLE IF NOT EXISTS kagit_pozisyonlar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sembol TEXT NOT NULL,
    yon TEXT NOT NULL,
    miktar REAL NOT NULL,
    giris REAL NOT NULL,
    stop REAL NOT NULL,
    kar_al REAL NOT NULL,
    kaldirac INTEGER,
    acilis_zamani TEXT,
    acilis_mum_zamani INTEGER NOT NULL,
    durum TEXT NOT NULL DEFAULT 'ACIK',
    kapanis_fiyati REAL,
    kapanis_zamani TEXT,
    kapanis_nedeni TEXT,
    pnl REAL
);
"""


def simdi_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime] = None) -> str:
    return (dt or simdi_utc()).isoformat(timespec="seconds")


def ms_iso(ms: Optional[int]) -> Optional[str]:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="minutes")


def log_kur(klasor: Path, seviye: int = logging.INFO) -> Path:
    """Konsola ve loglar/bot_YYYY-MM-DD.log (UTC) dosyasına yazan logger kurar."""
    klasor = Path(klasor)
    klasor.mkdir(parents=True, exist_ok=True)
    dosya = klasor / f"bot_{simdi_utc():%Y-%m-%d}.log"
    kok = logging.getLogger()
    kok.setLevel(seviye)
    for h in list(kok.handlers):
        kok.removeHandler(h)
    bicim = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(dosya, encoding="utf-8")
    fh.setFormatter(bicim)
    kok.addHandler(fh)
    try:  # Windows konsolunda Türkçe karakterler için
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(bicim)
    kok.addHandler(sh)
    # ccxt / urllib3 gürültüsünü azalt
    for gurultu in ("ccxt", "urllib3"):
        logging.getLogger(gurultu).setLevel(logging.WARNING)
    return dosya


class Gunluk:
    """SQLite kayıt defteri."""

    def __init__(self, yol: Path | str):
        yol = Path(yol)
        if str(yol) != ":memory:":
            yol.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(yol), timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SEMA)
        self.db.commit()

    def kapat(self) -> None:
        self.db.close()

    # ---------- kararlar ----------
    def karar_yaz(self, **k: Any) -> int:
        k.setdefault("zaman", iso())
        for alan in ("gostergeler", "emir_bilgisi"):
            if alan in k and not isinstance(k[alan], (str, type(None))):
                k[alan] = json.dumps(k[alan], ensure_ascii=False, default=str)
        if "islem_acildi" in k:
            k["islem_acildi"] = int(bool(k["islem_acildi"]))
        alanlar = ", ".join(k)
        yer = ", ".join("?" for _ in k)
        cur = self.db.execute(f"INSERT INTO kararlar ({alanlar}) VALUES ({yer})", list(k.values()))
        self.db.commit()
        return int(cur.lastrowid)

    # ---------- gün başı bakiyesi ----------
    def gun_basi_al(self, tarih: str, mod: str) -> Optional[float]:
        r = self.db.execute("SELECT bakiye FROM gun_basi WHERE tarih=? AND mod=?", (tarih, mod)).fetchone()
        return float(r["bakiye"]) if r else None

    def gun_basi_yaz(self, tarih: str, mod: str, bakiye: float) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO gun_basi (tarih, mod, bakiye, kayit_zamani) VALUES (?,?,?,?)",
            (tarih, mod, bakiye, iso()),
        )
        self.db.commit()

    def limit_bildirildi_mi(self, tarih: str, mod: str) -> bool:
        r = self.db.execute("SELECT limit_bildirildi FROM gun_basi WHERE tarih=? AND mod=?", (tarih, mod)).fetchone()
        return bool(r and r["limit_bildirildi"])

    def limit_bildirildi_isaretle(self, tarih: str, mod: str) -> None:
        self.db.execute("UPDATE gun_basi SET limit_bildirildi=1 WHERE tarih=? AND mod=?", (tarih, mod))
        self.db.commit()

    # ---------- çalışmalar ----------
    def calisma_yaz(self, **k: Any) -> None:
        if "ozet" in k and not isinstance(k["ozet"], str):
            k["ozet"] = json.dumps(k["ozet"], ensure_ascii=False, default=str)
        alanlar = ", ".join(k)
        yer = ", ".join("?" for _ in k)
        self.db.execute(f"INSERT OR REPLACE INTO calismalar ({alanlar}) VALUES ({yer})", list(k.values()))
        self.db.commit()

    # ---------- kağıt pozisyonları ----------
    def kagit_acik(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM kagit_pozisyonlar WHERE durum='ACIK' ORDER BY id").fetchall()

    def kagit_ekle(self, sembol: str, yon: str, miktar: float, giris: float, stop: float,
                   kar_al: float, kaldirac: int, mum_zamani: int) -> int:
        cur = self.db.execute(
            "INSERT INTO kagit_pozisyonlar (sembol, yon, miktar, giris, stop, kar_al, kaldirac, "
            "acilis_zamani, acilis_mum_zamani) VALUES (?,?,?,?,?,?,?,?,?)",
            (sembol, yon, miktar, giris, stop, kar_al, kaldirac, iso(), mum_zamani),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def kagit_kapat(self, poz_id: int, fiyat: float, neden: str, pnl: float, zaman: Optional[str] = None) -> None:
        self.db.execute(
            "UPDATE kagit_pozisyonlar SET durum='KAPALI', kapanis_fiyati=?, kapanis_zamani=?, "
            "kapanis_nedeni=?, pnl=? WHERE id=?",
            (fiyat, zaman or iso(), neden, pnl, poz_id),
        )
        self.db.commit()

    def kagit_gerceklesen_pnl(self) -> float:
        r = self.db.execute("SELECT COALESCE(SUM(pnl), 0) AS t FROM kagit_pozisyonlar WHERE durum='KAPALI'").fetchone()
        return float(r["t"])
