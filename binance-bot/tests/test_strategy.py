import numpy as np
import pytest

from bot.sahte_veri import SAAT_MS, egimli_seri, sentetik_mumlar
from bot.strategy import kapanmis_mumlar, seviyeleri_hesapla, sinyal_uret


def _trend(yon):
    """Gürültülü sentetik trend (deterministik tohum): RSI bant içinde kalır."""
    if yon == "LONG":
        return sentetik_mumlar(n=600, baslangic=60_000, egim=0.0006, oynaklik=0.004, tohum=7, son_mum_acik=False)
    return sentetik_mumlar(n=600, baslangic=0.6, egim=-0.0006, oynaklik=0.005, tohum=11, son_mum_acik=False)


def test_yukselen_trend_long(s_cfg):
    df = _trend("LONG")
    s = sinyal_uret("BTC/USDT:USDT", df, 0.0001, s_cfg)
    assert s.yon == "LONG", s.neden
    assert s.stop < s.giris < s.kar_al
    assert s.giris - s.stop == pytest.approx(2 * s.atr)
    assert s.kar_al - s.giris == pytest.approx(3 * s.atr)


def test_dusen_trend_short(s_cfg):
    df = _trend("SHORT")
    s = sinyal_uret("XRP/USDT:USDT", df, 0.0001, s_cfg)
    assert s.yon == "SHORT", s.neden
    assert s.kar_al < s.giris < s.stop
    assert s.stop - s.giris == pytest.approx(2 * s.atr)


def test_long_funding_yuksekse_sinyal_yok(s_cfg):
    df = _trend("LONG")
    s = sinyal_uret("BTC/USDT:USDT", df, 0.0006, s_cfg)
    assert s.yon is None
    assert "funding" in s.neden


def test_short_funding_cok_negatifse_sinyal_yok(s_cfg):
    df = _trend("SHORT")
    s = sinyal_uret("BTC/USDT:USDT", df, -0.0006, s_cfg)
    assert s.yon is None


def test_rsi_asiri_alimda_long_yok(s_cfg):
    # Pürüzsüz, kesintisiz yükseliş → RSI ~100 → band dışı
    df = egimli_seri(100 * np.exp(0.003 * np.arange(400)))
    s = sinyal_uret("BTC/USDT:USDT", df, 0.0, s_cfg)
    assert s.yon is None
    assert "RSI" in s.neden


def test_yetersiz_veri(s_cfg):
    s = sinyal_uret("BTC/USDT:USDT", egimli_seri(np.linspace(100, 110, 150)), 0.0, s_cfg)
    assert s.yon is None and "Yetersiz" in s.neden


def test_funding_yoksa_sinyal_yok(s_cfg):
    s = sinyal_uret("BTC/USDT:USDT", _trend("LONG"), None, s_cfg)
    assert s.yon is None and "Funding" in s.neden


def test_ayarlar_configten_okunur(s_cfg):
    df = _trend("LONG")
    s1 = sinyal_uret("BTC", df, 0.0, s_cfg)
    ozel = dict(s_cfg, long_rsi_max=s1.ozet["rsi"] - 1)
    assert sinyal_uret("BTC", df, 0.0, ozel).yon is None


def test_kapanmamis_mum_atilir():
    simdi = 1_700_000_000_000
    saat = simdi - simdi % SAAT_MS
    df = sentetik_mumlar(n=10, bitis_ms=saat, son_mum_acik=True)
    temiz = kapanmis_mumlar(df, "1h", saat + 60_000)  # saatin 1. dakikası
    assert len(temiz) == 9
    assert temiz["timestamp"].iloc[-1] == saat - SAAT_MS
    # Tam saat başında önceki mum kapanmış sayılır
    assert len(kapanmis_mumlar(df, "1h", saat)) == 9


def test_seviyeler(s_cfg):
    assert seviyeleri_hesapla("LONG", 100, 1, s_cfg) == (98, 103)
    assert seviyeleri_hesapla("SHORT", 100, 1, s_cfg) == (102, 97)
