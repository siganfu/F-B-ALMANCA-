"""İnternetsiz test ve `--sahte-veri` demosu için sentetik piyasa verisi.

Gerçek işlem kararı için KULLANILMAZ; yalnızca akışı uçtan uca denemek içindir.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .risk import PiyasaKurallari

SAAT_MS = 3_600_000


def sentetik_mumlar(
    n: int = 600,
    baslangic: float = 100.0,
    egim: float = 0.0,
    oynaklik: float = 0.004,
    tohum: int = 1,
    bitis_ms: int | None = None,
    son_mum_acik: bool = True,
) -> pd.DataFrame:
    """Rastgele yürüyüş + eğim ile OHLCV üretir.

    egim: mum başına ortalama getiri (ör. 0.0008 = yükselen trend).
    son_mum_acik: True ise en son mum henüz kapanmamış gibi zaman damgalanır.
    """
    rng = np.random.default_rng(tohum)
    getiriler = rng.normal(egim, oynaklik, n)
    kapanis = baslangic * np.exp(np.cumsum(getiriler))
    acilis = np.concatenate([[baslangic], kapanis[:-1]])
    fitil = np.abs(rng.normal(0, oynaklik / 2, n)) * kapanis
    yuksek = np.maximum(acilis, kapanis) + fitil
    dusuk = np.minimum(acilis, kapanis) - fitil
    hacim = rng.uniform(100, 1000, n)

    if bitis_ms is None:
        bitis_ms = int(pd.Timestamp.now(tz="UTC").floor("h").value // 1_000_000)
    # Son mumun açılış zamanı: açık olsun istenirse "şu anki saat", değilse bir önceki saat
    son_acilis = bitis_ms if son_mum_acik else bitis_ms - SAAT_MS
    zaman = son_acilis - SAAT_MS * np.arange(n - 1, -1, -1)
    return pd.DataFrame({
        "timestamp": zaman.astype("int64"),
        "open": acilis, "high": yuksek, "low": dusuk, "close": kapanis, "volume": hacim,
    })


def egimli_seri(fiyatlar: list[float] | np.ndarray, bitis_ms: int = 1_700_000_000_000) -> pd.DataFrame:
    """Verilen kapanış dizisinden deterministik OHLCV üretir (testler için)."""
    k = np.asarray(fiyatlar, dtype=float)
    a = np.concatenate([[k[0]], k[:-1]])
    n = len(k)
    zaman = bitis_ms - SAAT_MS * np.arange(n - 1, -1, -1)
    return pd.DataFrame({
        "timestamp": zaman.astype("int64"), "open": a,
        "high": np.maximum(a, k) * 1.001, "low": np.minimum(a, k) * 0.999,
        "close": k, "volume": np.full(n, 500.0),
    })


class SahteVeri:
    """Exchange veri arayüzünü taklit eden internetsiz kaynak."""

    PROFILLER = {
        # sembol: (başlangıç fiyatı, eğim, oynaklık, tohum)
        "BTC/USDT:USDT": (60_000.0, 0.0006, 0.004, 7),
        "BNB/USDT:USDT": (600.0, 0.0, 0.005, 3),
        "XRP/USDT:USDT": (0.60, -0.0006, 0.005, 11),
    }

    def __init__(self, funding: float = 0.0001):
        self._funding = funding

    def kurallar(self, sembol: str) -> PiyasaKurallari:
        if sembol.startswith("BTC"):
            return PiyasaKurallari(miktar_adimi=0.001, fiyat_adimi=0.1, min_miktar=0.001, min_nominal=100)
        if sembol.startswith("BNB"):
            return PiyasaKurallari(miktar_adimi=0.01, fiyat_adimi=0.01, min_miktar=0.01, min_nominal=5)
        return PiyasaKurallari(miktar_adimi=0.1, fiyat_adimi=0.0001, min_miktar=0.1, min_nominal=5)

    def mumlar(self, sembol: str, zaman_dilimi: str, limit: int) -> pd.DataFrame:
        bas, egim, oyn, tohum = self.PROFILLER.get(sembol, (100.0, 0.0, 0.005, 1))
        return sentetik_mumlar(n=min(limit, 1000), baslangic=bas, egim=egim, oynaklik=oyn, tohum=tohum)

    def funding(self, sembol: str) -> float:
        return self._funding
