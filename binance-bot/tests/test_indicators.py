import numpy as np
import pandas as pd
import pytest

from bot.indicators import atr, ema, rsi


def test_ema_sabit_seri_kendisine_esit():
    s = pd.Series([10.0] * 50)
    assert ema(s, 20).iloc[-1] == pytest.approx(10.0)
    assert ema(s, 20).iloc[:19].isna().all()


def test_ema_elle_hesapla():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    alfa = 2 / (3 + 1)
    beklenen = 1.0
    for x in [2.0, 3.0, 4.0, 5.0]:
        beklenen = alfa * x + (1 - alfa) * beklenen
    assert ema(s, 3).iloc[-1] == pytest.approx(beklenen)


def test_rsi_surekli_yukselen_100_dusen_0():
    yukselen = pd.Series(np.arange(1, 60, dtype=float))
    dusen = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert rsi(yukselen, 14).iloc[-1] == pytest.approx(100.0)
    assert rsi(dusen, 14).iloc[-1] == pytest.approx(0.0)


def test_rsi_yatay_50_ve_aralik():
    assert rsi(pd.Series([5.0] * 40), 14).iloc[-1] == pytest.approx(50.0)
    rng = np.random.default_rng(0)
    r = rsi(pd.Series(100 + rng.normal(0, 1, 500).cumsum()), 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_rsi_wilder_ozyineleme():
    """RSI, Wilder'ın özyinelemeli ortalamasıyla elle hesaplanan değere eşit olmalı."""
    k = pd.Series([44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
                   45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64])
    n = 14
    d = k.diff().dropna().tolist()   # ilk fark tohum olarak kullanılır
    ok, ol = max(d[0], 0), max(-d[0], 0)
    for x in d[1:]:
        ok = ok + (max(x, 0) - ok) / n
        ol = ol + (max(-x, 0) - ol) / n
    beklenen = 100 - 100 / (1 + ok / ol)
    assert rsi(k, n).iloc[-1] == pytest.approx(beklenen)


def test_atr_sabit_aralik():
    n = 40
    df = pd.DataFrame({"high": [11.0] * n, "low": [9.0] * n, "close": [10.0] * n})
    assert atr(df, 14).iloc[-1] == pytest.approx(2.0)


def test_atr_bosluk_true_range_kullanir():
    df = pd.DataFrame({"high": [10.0, 21.0], "low": [9.0, 20.0], "close": [9.5, 20.5]})
    # 2. mumda TR = |21 - 9.5| = 11.5
    tr = atr(df, 1)
    assert tr.iloc[-1] == pytest.approx(11.5)
