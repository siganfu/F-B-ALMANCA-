"""Kağıt borsa simülasyonu ve uçtan uca akış (internetsiz)."""
import pandas as pd
import pytest

from bot import main as ana_modul
from bot.exchange import KagitBorsa
from bot.journal import Gunluk
from bot.risk import PiyasaKurallari, RiskSonucu
from bot.sahte_veri import SAAT_MS
from bot.strategy import Sinyal


def _borsa(cfg):
    return KagitBorsa(veri=None, gunluk=Gunluk(":memory:"), cfg=cfg)


def _mumlar(t0, satirlar):
    return pd.DataFrame([{"timestamp": t0 + (i + 1) * SAAT_MS, "open": o, "high": h, "low": l, "close": c,
                          "volume": 1} for i, (o, h, l, c) in enumerate(satirlar)])


def _ac(b, yon, giris, stop, kar, t0, miktar=1.0):
    s = Sinyal("BTC/USDT:USDT", yon, giris=giris, stop=stop, kar_al=kar, mum_zamani=t0)
    return b.pozisyon_ac(s, RiskSonucu(True, "", miktar=miktar, kaldirac=3), PiyasaKurallari(fiyat_adimi=0.1))


def test_kagit_long_kar_al(cfg):
    b, t0 = _borsa(cfg), 1_700_000_000_000
    assert _ac(b, "LONG", 100, 98, 103, t0).acildi
    assert "BTC/USDT:USDT" in b.acik_pozisyonlar()
    olay = b.bakim(["BTC/USDT:USDT"], {"BTC/USDT:USDT": _mumlar(t0, [(100, 101, 99, 100.5), (100.5, 103.5, 100, 103)])}, {})
    assert olay and "KAR_AL" in olay[0].mesaj
    assert b.acik_pozisyonlar() == {}
    assert b.bakiye() == pytest.approx(1000 + 3 - 0.0005 * 203)


def test_kagit_short_stop_ve_ayni_mumda_stop_oncelikli(cfg):
    b, t0 = _borsa(cfg), 1_700_000_000_000
    _ac(b, "SHORT", 100, 102, 97, t0)
    # Aynı mumda hem 102 hem 97 görülmüş → muhafazakâr: STOP
    olay = b.bakim(["BTC/USDT:USDT"], {"BTC/USDT:USDT": _mumlar(t0, [(100, 102.5, 96.5, 99)])}, {})
    assert "STOP" in olay[0].mesaj
    assert b.bakiye() < 1000 - 2


def test_kagit_acilis_mumu_tetiklemez(cfg):
    b, t0 = _borsa(cfg), 1_700_000_000_000
    _ac(b, "LONG", 100, 98, 103, t0)
    df = pd.DataFrame([{"timestamp": t0, "open": 99, "high": 110, "low": 90, "close": 100, "volume": 1}])
    assert b.bakim(["BTC/USDT:USDT"], {"BTC/USDT:USDT": df}, {}) == []
    assert b.bakiye({"BTC/USDT:USDT": 101}) == pytest.approx(1001)


def test_uctan_uca_sahte_veri(cfg, tmp_path, monkeypatch):
    """--sahte-veri ile tam akış: sinyal → risk → (Claude kapalı) → kağıt emir → kayıt."""
    cfg = dict(cfg)
    cfg["kayit"] = {"veritabani": str(tmp_path / "g.db"), "log_klasoru": str(tmp_path / "log")}
    cfg["claude"] = dict(cfg["claude"], kullanim="kapali")
    cfg["telegram"] = {"aktif": False}
    monkeypatch.setattr(ana_modul, "KOK", tmp_path)  # DURDUR dosyası aranacak yer
    assert ana_modul.calistir(cfg, sahte_veri=True) == 0
    g = Gunluk(tmp_path / "g.db")
    kararlar = g.db.execute("SELECT sembol, sinyal, islem_acildi, risk_nedeni FROM kararlar").fetchall()
    assert len(kararlar) == 3
    assert sum(k["islem_acildi"] for k in kararlar) <= 2  # max 2 açık pozisyon
    assert len(g.kagit_acik()) <= 2


def test_uctan_uca_durdur_dosyasi(cfg, tmp_path, monkeypatch):
    cfg = dict(cfg)
    cfg["kayit"] = {"veritabani": str(tmp_path / "g.db"), "log_klasoru": str(tmp_path / "log")}
    cfg["claude"] = dict(cfg["claude"], kullanim="kapali")
    cfg["telegram"] = {"aktif": False}
    (tmp_path / "DURDUR").touch()
    monkeypatch.setattr(ana_modul, "KOK", tmp_path)
    ana_modul.calistir(cfg, sahte_veri=True)
    g = Gunluk(tmp_path / "g.db")
    assert g.db.execute("SELECT COUNT(*) FROM kararlar WHERE islem_acildi=1").fetchone()[0] == 0
    assert g.kagit_acik() == []


def test_uctan_uca_claude_bekle_politikasi(cfg, tmp_path, monkeypatch):
    """Claude ulaşılamaz + bekle → hiç işlem açılmaz."""
    cfg = dict(cfg)
    cfg["kayit"] = {"veritabani": str(tmp_path / "g.db"), "log_klasoru": str(tmp_path / "log")}
    cfg["claude"] = dict(cfg["claude"], kullanim="onay", ulasilamazsa="bekle", komut="olmayan-claude-komutu-xyz")
    cfg["telegram"] = {"aktif": False}
    monkeypatch.setattr(ana_modul, "KOK", tmp_path)
    ana_modul.calistir(cfg, sahte_veri=True)
    g = Gunluk(tmp_path / "g.db")
    assert g.db.execute("SELECT COUNT(*) FROM kararlar WHERE islem_acildi=1").fetchone()[0] == 0
