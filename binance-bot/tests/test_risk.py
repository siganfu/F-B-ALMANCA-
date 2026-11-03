import pytest

from bot.risk import (
    PiyasaKurallari, adima_yuvarla, adima_yuvarla_asagi, durdur_dosyasi_var_mi,
    genel_kontrol, gunluk_zarar_orani, parite_kontrolu, pozisyon_hesapla,
)

K = PiyasaKurallari(miktar_adimi=0.001, fiyat_adimi=0.1, min_miktar=0.001, min_nominal=5)


def test_boyut_formulu(r_cfg):
    # bakiye 1000, risk %1 = 10 USDT, stop mesafesi 2 (%2) → 5 adet, nominal 500
    s = pozisyon_hesapla(1000, 100, 98, 3, K, r_cfg)
    assert s.izin
    assert s.miktar == pytest.approx(5.0)
    assert s.nominal == pytest.approx(500.0)
    assert s.risk_tutari == pytest.approx(10.0)
    assert s.kaldirac == 3
    assert not s.kaldirac_tavanina_takildi


def test_kaldirac_tavani(r_cfg):
    # stop %0.5 → ham miktar 20 → nominal 2000 > 1000×2 değil ama 1000×1'i geçer
    s = pozisyon_hesapla(1000, 100, 99.5, 1, K, r_cfg)
    assert s.izin and s.kaldirac_tavanina_takildi
    assert s.nominal <= 1000 * 1 + 1e-9
    s2 = pozisyon_hesapla(1000, 100, 99.5, 2, K, r_cfg)
    assert s2.nominal == pytest.approx(2000.0)
    assert s2.nominal <= 1000 * 2


@pytest.mark.parametrize("stop, izin", [(99.7, False), (99.6, True), (94.0, True), (93.9, False)])
def test_stop_mesafesi_sinirlari(r_cfg, stop, izin):
    # %0.3 → red, %0.4 → kabul, %6 → kabul, %6.1 → red
    assert pozisyon_hesapla(1000, 100, stop, 3, K, r_cfg).izin is izin


def test_short_icin_de_calisir(r_cfg):
    s = pozisyon_hesapla(1000, 100, 102, 3, K, r_cfg)
    assert s.izin and s.miktar == pytest.approx(5.0)


def test_min_miktar_ve_nominal(r_cfg):
    buyuk = PiyasaKurallari(miktar_adimi=0.001, fiyat_adimi=0.1, min_miktar=0.001, min_nominal=100)
    # bakiye 50 → risk 0.5 USDT, stop %2 (2000) → miktar 0.00025 → 0'a yuvarlanır
    s = pozisyon_hesapla(50, 100_000, 98_000, 3, buyuk, r_cfg)
    assert not s.izin and "minimum" in s.neden
    # min nominal: ince adımlı piyasada bakiye 150 → miktar 0.0007 → nominal 70 < 100
    ince = PiyasaKurallari(miktar_adimi=0.0001, fiyat_adimi=0.1, min_miktar=0.0001, min_nominal=100)
    s2 = pozisyon_hesapla(150, 100_000, 98_000, 3, ince, r_cfg)
    assert not s2.izin and "Emir değeri" in s2.neden


def test_gecersiz_bakiye(r_cfg):
    assert not pozisyon_hesapla(0, 100, 98, 3, K, r_cfg).izin


def test_yuvarlama():
    assert adima_yuvarla_asagi(1.23456, 0.001) == pytest.approx(1.234)
    assert adima_yuvarla_asagi(0.29999, 0.1) == pytest.approx(0.2)
    assert adima_yuvarla_asagi(7.0, 1) == 7
    assert adima_yuvarla(100.06, 0.1) == pytest.approx(100.1)
    assert adima_yuvarla(0.512345, 0.0001) == pytest.approx(0.5123)


def test_miktar_asagi_yuvarlanir_risk_asilmaz(r_cfg):
    k = PiyasaKurallari(miktar_adimi=0.1, fiyat_adimi=0.0001, min_miktar=0.1, min_nominal=5)
    s = pozisyon_hesapla(1000, 0.6, 0.588, 2, k, r_cfg)
    assert s.izin
    assert s.risk_tutari <= 10.0 + 1e-9
    assert round(s.miktar / 0.1, 6) == int(round(s.miktar / 0.1, 6))


def test_gunluk_zarar():
    assert gunluk_zarar_orani(1000, 950) == pytest.approx(0.05)
    assert gunluk_zarar_orani(1000, 1100) == pytest.approx(-0.1)
    assert gunluk_zarar_orani(None, 900) == 0.0


def test_genel_kontrol(r_cfg):
    assert genel_kontrol(False, 0.0, 0, r_cfg)[0]
    izin, neden = genel_kontrol(True, 0.0, 0, r_cfg)
    assert not izin and "Kill switch" in neden
    izin, neden = genel_kontrol(False, 0.05, 0, r_cfg)
    assert not izin and "Günlük zarar" in neden
    assert genel_kontrol(False, 0.049, 1, r_cfg)[0]
    izin, neden = genel_kontrol(False, 0.0, 2, r_cfg)
    assert not izin and "Maksimum" in neden


def test_parite_kontrolu(r_cfg):
    assert not parite_kontrolu("BTC", {"BTC"}, 1, r_cfg)[0]
    assert parite_kontrolu("BNB", {"BTC"}, 1, r_cfg)[0]
    assert not parite_kontrolu("XRP", {"BTC", "BNB"}, 2, r_cfg)[0]


def test_durdur_dosyasi(tmp_path):
    assert not durdur_dosyasi_var_mi(tmp_path)
    (tmp_path / "DURDUR").touch()
    assert durdur_dosyasi_var_mi(tmp_path)
