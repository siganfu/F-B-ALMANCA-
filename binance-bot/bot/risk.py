"""Risk motoru — sabit kurallar, LLM YOK. Ağa erişmez, saf fonksiyonlardan oluşur."""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Optional


@dataclass
class PiyasaKurallari:
    """Borsanın parite için hassasiyet ve limitleri."""
    miktar_adimi: float = 0.001      # miktar hassasiyeti (adım)
    fiyat_adimi: float = 0.01        # fiyat hassasiyeti (tick)
    min_miktar: float = 0.0
    min_nominal: float = 0.0         # minimum emir değeri (USDT)


@dataclass
class RiskSonucu:
    izin: bool
    neden: str
    miktar: float = 0.0
    nominal: float = 0.0
    kaldirac: int = 1
    risk_tutari: float = 0.0
    stop_mesafesi_orani: float = 0.0
    kaldirac_tavanina_takildi: bool = False


def adima_yuvarla_asagi(deger: float, adim: float) -> float:
    """Değeri adımın katına AŞAĞI yuvarlar (miktar için; risk asla büyümez)."""
    if adim <= 0:
        return float(deger)
    d, a = Decimal(str(deger)), Decimal(str(adim))
    return float((d / a).to_integral_value(rounding=ROUND_DOWN) * a)


def adima_yuvarla(deger: float, adim: float) -> float:
    """Değeri adımın en yakın katına yuvarlar (fiyat için)."""
    if adim <= 0:
        return float(deger)
    d, a = Decimal(str(deger)), Decimal(str(adim))
    return float((d / a).to_integral_value(rounding=ROUND_HALF_UP) * a)


def durdur_dosyasi_var_mi(klasor: Path, ad: str = "DURDUR") -> bool:
    return (Path(klasor) / ad).exists()


def gunluk_zarar_orani(gun_basi_bakiye: Optional[float], simdiki_bakiye: float) -> float:
    """Gün başına göre zarar oranı (pozitif = zarar). Gün başı bilinmiyorsa 0."""
    if not gun_basi_bakiye or gun_basi_bakiye <= 0:
        return 0.0
    return (gun_basi_bakiye - simdiki_bakiye) / gun_basi_bakiye


def genel_kontrol(
    durdur_var: bool,
    zarar_orani: float,
    acik_pozisyon_sayisi: int,
    r: dict,
) -> tuple[bool, str]:
    """Tüm coinler için ortak kapılar. (izin, neden) döner."""
    if durdur_var:
        return False, f"Kill switch: '{r.get('durdur_dosyasi', 'DURDUR')}' dosyası mevcut"
    if zarar_orani >= float(r["gunluk_zarar_limiti"]):
        return False, (f"Günlük zarar limiti aşıldı: %{zarar_orani * 100:.2f} "
                       f"(limit %{float(r['gunluk_zarar_limiti']) * 100:.2f})")
    if acik_pozisyon_sayisi >= int(r["max_acik_pozisyon"]):
        return False, f"Maksimum açık pozisyon sayısına ulaşıldı ({acik_pozisyon_sayisi}/{r['max_acik_pozisyon']})"
    return True, "Genel kontroller geçti"


def parite_kontrolu(sembol: str, acik_semboller: set[str], acik_pozisyon_sayisi: int, r: dict) -> tuple[bool, str]:
    """Pariteye özel kapılar."""
    if sembol in acik_semboller:
        return False, f"{sembol} için zaten açık pozisyon var"
    if acik_pozisyon_sayisi >= int(r["max_acik_pozisyon"]):
        return False, f"Maksimum açık pozisyon sayısına ulaşıldı ({acik_pozisyon_sayisi}/{r['max_acik_pozisyon']})"
    return True, "Parite kontrolü geçti"


def pozisyon_hesapla(
    bakiye: float,
    giris: float,
    stop: float,
    max_kaldirac: int,
    kurallar: PiyasaKurallari,
    r: dict,
) -> RiskSonucu:
    """Pozisyon büyüklüğünü hesaplar ve sınırları uygular.

    miktar = (bakiye × islem_basi_risk) / |giris − stop|
    nominal ≤ bakiye × max_kaldirac
    """
    if bakiye is None or bakiye <= 0 or math.isnan(bakiye):
        return RiskSonucu(False, f"Geçersiz bakiye: {bakiye}")
    if giris <= 0 or stop <= 0:
        return RiskSonucu(False, f"Geçersiz giriş/stop: {giris}/{stop}")

    mesafe = abs(giris - stop)
    oran = mesafe / giris
    if oran < float(r["min_stop_mesafesi"]):
        return RiskSonucu(False, f"Stop mesafesi çok küçük: %{oran * 100:.3f} (min %{r['min_stop_mesafesi'] * 100:.2f})",
                          stop_mesafesi_orani=oran)
    if oran > float(r["max_stop_mesafesi"]):
        return RiskSonucu(False, f"Stop mesafesi çok büyük: %{oran * 100:.3f} (max %{r['max_stop_mesafesi'] * 100:.2f})",
                          stop_mesafesi_orani=oran)

    risk_tutari = bakiye * float(r["islem_basi_risk"])
    miktar = risk_tutari / mesafe
    max_nominal = bakiye * int(max_kaldirac)
    tavan = False
    if miktar * giris > max_nominal:
        miktar = max_nominal / giris
        tavan = True

    miktar = adima_yuvarla_asagi(miktar, kurallar.miktar_adimi)
    nominal = miktar * giris

    if miktar <= 0 or miktar < kurallar.min_miktar:
        return RiskSonucu(False, f"Miktar borsa minimumunun altında: {miktar} < {kurallar.min_miktar}",
                          miktar=miktar, nominal=nominal, stop_mesafesi_orani=oran)
    if kurallar.min_nominal and nominal < kurallar.min_nominal:
        return RiskSonucu(False, f"Emir değeri borsa minimumunun altında: {nominal:.2f} < {kurallar.min_nominal} USDT",
                          miktar=miktar, nominal=nominal, stop_mesafesi_orani=oran)

    gercek_risk = miktar * mesafe
    return RiskSonucu(
        True,
        "Risk kontrolleri geçti" + (" (kaldıraç tavanı uygulandı)" if tavan else ""),
        miktar=miktar,
        nominal=nominal,
        kaldirac=int(max_kaldirac),
        risk_tutari=gercek_risk,
        stop_mesafesi_orani=oran,
        kaldirac_tavanina_takildi=tavan,
    )
