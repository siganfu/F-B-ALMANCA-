"""Kural tabanlı strateji: EMA trend + RSI bandı + funding filtresi.

LONG : kapanış > EMA200, EMA20 > EMA50, RSI long bandında, funding < long_max_funding
SHORT: kapanış < EMA200, EMA20 < EMA50, RSI short bandında, funding > short_min_funding
Stop  = giriş ∓ stop_atr_carpani × ATR
Kâr al = giriş ± kar_al_atr_carpani × ATR
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .indicators import gostergeleri_ekle

ZAMAN_DILIMI_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "1d": 86_400_000,
}


@dataclass
class Sinyal:
    sembol: str
    yon: Optional[str]            # "LONG", "SHORT" veya None
    giris: float = 0.0
    stop: float = 0.0
    kar_al: float = 0.0
    atr: float = 0.0
    mum_zamani: int = 0           # sinyali üreten kapanmış mumun açılış zamanı (ms)
    neden: str = ""
    ozet: dict = field(default_factory=dict)

    @property
    def var_mi(self) -> bool:
        return self.yon in ("LONG", "SHORT")


def kapanmis_mumlar(df: pd.DataFrame, zaman_dilimi: str, simdi_ms: int) -> pd.DataFrame:
    """Henüz kapanmamış mumları atar. df['timestamp'] mumun AÇILIŞ zamanıdır (ms)."""
    sure = ZAMAN_DILIMI_MS[zaman_dilimi]
    return df[df["timestamp"] + sure <= simdi_ms].reset_index(drop=True)


def seviyeleri_hesapla(yon: str, giris: float, atr_degeri: float, s: dict) -> tuple[float, float]:
    """Girişe göre stop ve kâr al seviyeleri."""
    stop_m = float(s["stop_atr_carpani"]) * atr_degeri
    kar_m = float(s["kar_al_atr_carpani"]) * atr_degeri
    if yon == "LONG":
        return giris - stop_m, giris + kar_m
    return giris + stop_m, giris - kar_m


def _yuvarla(x: float, n: int = 6) -> float:
    return round(float(x), n) if x is not None and not math.isnan(x) else float("nan")


def sinyal_uret(sembol: str, df: pd.DataFrame, funding: Optional[float], s: dict) -> Sinyal:
    """Kapanmış mumlardan (df) ve funding oranından sinyal üretir.

    df yalnızca KAPANMIŞ mumları içermelidir (bkz. kapanmis_mumlar).
    """
    gerekli = int(s["ema_trend"]) + 1
    if len(df) < gerekli:
        return Sinyal(sembol, None, neden=f"Yetersiz veri: {len(df)} mum (en az {gerekli} gerekli)")

    g = gostergeleri_ekle(df, s)
    son = g.iloc[-1]
    kapanis = float(son["close"])
    ozet = {
        "kapanis": _yuvarla(kapanis),
        "ema20": _yuvarla(son["ema_hizli"]),
        "ema50": _yuvarla(son["ema_yavas"]),
        "ema200": _yuvarla(son["ema_trend"]),
        "rsi": _yuvarla(son["rsi"], 2),
        "atr": _yuvarla(son["atr"]),
        "atr_yuzde": _yuvarla(float(son["atr"]) / kapanis * 100, 3) if kapanis else None,
        "funding": funding,
        "mum_zamani": int(son["timestamp"]),
        "son_24s_degisim_yuzde": _yuvarla((kapanis / float(g["close"].iloc[-25]) - 1) * 100, 2)
        if len(g) > 25 else None,
    }
    mz = int(son["timestamp"])

    if any(pd.isna(son[k]) for k in ("ema_hizli", "ema_yavas", "ema_trend", "rsi", "atr")):
        return Sinyal(sembol, None, mum_zamani=mz, neden="Göstergeler hesaplanamadı (NaN)", ozet=ozet)
    if funding is None:
        return Sinyal(sembol, None, mum_zamani=mz, neden="Funding oranı alınamadı", ozet=ozet)

    ema20, ema50, ema200 = float(son["ema_hizli"]), float(son["ema_yavas"]), float(son["ema_trend"])
    r, a = float(son["rsi"]), float(son["atr"])

    long_kosul = {
        "fiyat>EMA200": kapanis > ema200,
        "EMA20>EMA50": ema20 > ema50,
        "RSI long bandı": s["long_rsi_min"] <= r <= s["long_rsi_max"],
        "funding uygun": funding < s["long_max_funding"],
    }
    short_kosul = {
        "fiyat<EMA200": kapanis < ema200,
        "EMA20<EMA50": ema20 < ema50,
        "RSI short bandı": s["short_rsi_min"] <= r <= s["short_rsi_max"],
        "funding uygun": funding > s["short_min_funding"],
    }

    if all(long_kosul.values()):
        yon = "LONG"
    elif all(short_kosul.values()):
        yon = "SHORT"
    else:
        # Hangi koşulların tutmadığını açıkla (trend yönüne göre)
        kosullar = long_kosul if kapanis > ema200 else short_kosul
        eksik = [k for k, v in kosullar.items() if not v]
        return Sinyal(sembol, None, mum_zamani=mz, neden="Sinyal yok: " + ", ".join(eksik) + " sağlanmadı",
                      ozet=ozet)

    stop, kar = seviyeleri_hesapla(yon, kapanis, a, s)
    return Sinyal(sembol, yon, giris=kapanis, stop=stop, kar_al=kar, atr=a, mum_zamani=mz,
                  neden=f"{yon} koşullarının tümü sağlandı", ozet=ozet)
