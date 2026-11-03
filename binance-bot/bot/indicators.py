"""Teknik göstergeler — yalnızca pandas ile, harici kütüphane yok.

RSI ve ATR, Wilder yumuşatması (alpha = 1/periyot) ile hesaplanır;
bu, TradingView ve Binance grafiklerindeki değerlerle uyumludur.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(seri: pd.Series, periyot: int) -> pd.Series:
    """Üstel hareketli ortalama. İlk (periyot-1) değer NaN bırakılır."""
    return seri.ewm(span=periyot, adjust=False, min_periods=periyot).mean()


def rsi(kapanis: pd.Series, periyot: int = 14) -> pd.Series:
    """Göreceli Güç Endeksi (Wilder)."""
    fark = kapanis.diff()
    kazanc = fark.clip(lower=0.0)
    kayip = (-fark).clip(lower=0.0)
    ort_kazanc = kazanc.ewm(alpha=1.0 / periyot, adjust=False, min_periods=periyot).mean()
    ort_kayip = kayip.ewm(alpha=1.0 / periyot, adjust=False, min_periods=periyot).mean()

    rs = ort_kazanc / ort_kayip.replace(0.0, np.nan)
    sonuc = 100.0 - 100.0 / (1.0 + rs)
    # Hiç kayıp yoksa RSI = 100, hiç hareket yoksa 50
    sonuc = sonuc.where(~((ort_kayip == 0) & (ort_kazanc > 0)), 100.0)
    sonuc = sonuc.where(~((ort_kayip == 0) & (ort_kazanc == 0)), 50.0)
    return sonuc


def atr(df: pd.DataFrame, periyot: int = 14) -> pd.Series:
    """Ortalama Gerçek Aralık (Wilder). df: high, low, close sütunları."""
    onceki_kapanis = df["close"].shift(1)
    gercek_aralik = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - onceki_kapanis).abs(),
            (df["low"] - onceki_kapanis).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return gercek_aralik.ewm(alpha=1.0 / periyot, adjust=False, min_periods=periyot).mean()


def gostergeleri_ekle(df: pd.DataFrame, s: dict) -> pd.DataFrame:
    """Mum verisine strateji göstergelerini ekler (kopya döner)."""
    df = df.copy()
    df["ema_hizli"] = ema(df["close"], int(s["ema_hizli"]))
    df["ema_yavas"] = ema(df["close"], int(s["ema_yavas"]))
    df["ema_trend"] = ema(df["close"], int(s["ema_trend"]))
    df["rsi"] = rsi(df["close"], int(s["rsi_periyot"]))
    df["atr"] = atr(df, int(s["atr_periyot"]))
    return df
