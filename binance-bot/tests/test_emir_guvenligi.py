"""CanliBorsa emir güvenliği — sahte ccxt nesnesiyle, internetsiz."""
import pytest

from bot import exchange as ex_mod
from bot.exchange import CanliBorsa
from bot.risk import PiyasaKurallari, RiskSonucu
from bot.strategy import Sinyal


class SahteEx:
    def __init__(self, stop_hata=False, tp_hata=False):
        self.stop_hata, self.tp_hata = stop_hata, tp_hata
        self.emirler, self.iptaller, self.pozisyon = [], [], None
        self.acik = {"normal": [], "kosullu": []}
        self.marjin, self.kaldirac = None, None

    def fetch_position_mode(self):
        return {"hedged": False}

    def set_margin_mode(self, mod, sembol):
        self.marjin = mod

    def set_leverage(self, k, sembol):
        self.kaldirac = k

    def amount_to_precision(self, s, m):
        return f"{m:.3f}"

    def price_to_precision(self, s, p):
        return f"{p:.1f}"

    def create_order(self, sembol, tur, taraf, miktar, fiyat=None, params=None):
        params = params or {}
        self.emirler.append((tur, taraf, miktar, params))
        if tur == "STOP_MARKET" and self.stop_hata:
            raise RuntimeError("stop reddedildi")
        if tur == "TAKE_PROFIT_MARKET" and self.tp_hata:
            raise RuntimeError("tp reddedildi")
        if tur == "market" and not params.get("reduceOnly"):
            self.pozisyon = {"symbol": sembol, "contracts": miktar, "side": "long" if taraf == "buy" else "short",
                             "entryPrice": 100.5}
            return {"id": "g1", "average": 100.5, "filled": miktar}
        if tur == "market" and params.get("reduceOnly"):
            self.pozisyon = None
        return {"id": f"e{len(self.emirler)}"}

    def fetch_positions(self, semboller):
        return [self.pozisyon] if self.pozisyon else []

    def fetch_open_orders(self, sembol, params=None):
        return list(self.acik["kosullu" if (params or {}).get("trigger") else "normal"])

    def cancel_order(self, i, sembol, params=None):
        self.iptaller.append((i, params))

    def fetch_ticker(self, s):
        return {"last": 100.0}


@pytest.fixture(autouse=True)
def hizli_uyku(monkeypatch):
    monkeypatch.setattr(ex_mod.time, "sleep", lambda s: None)


def _cfg(cfg):
    return dict(cfg, mod="demo")


def _sinyal():
    return Sinyal("BTC/USDT:USDT", "LONG", giris=100.0, stop=98.0, kar_al=103.0, atr=1.0, mum_zamani=1)


def test_basarili_acilis_stop_ve_tp_dolum_fiyatina_gore(cfg):
    e = SahteEx()
    b = CanliBorsa(e, _cfg(cfg))
    s = b.pozisyon_ac(_sinyal(), RiskSonucu(True, "", miktar=5.0, kaldirac=3), PiyasaKurallari())
    assert s.acildi
    assert e.marjin == "isolated" and e.kaldirac == 3
    turler = [x[0] for x in e.emirler]
    assert turler == ["market", "STOP_MARKET", "TAKE_PROFIT_MARKET"]
    stop_params = e.emirler[1][3]
    assert stop_params["reduceOnly"] is True and stop_params["workingType"] == "MARK_PRICE"
    # Dolum 100.5 → stop 98.5, tp 103.5 (aynı ATR mesafeleri)
    assert stop_params["triggerPrice"] == pytest.approx(98.5)
    assert e.emirler[2][3]["triggerPrice"] == pytest.approx(103.5)


def test_stop_konulamazsa_pozisyon_hemen_kapatilir(cfg):
    e = SahteEx(stop_hata=True)
    b = CanliBorsa(e, _cfg(cfg))
    s = b.pozisyon_ac(_sinyal(), RiskSonucu(True, "", miktar=5.0, kaldirac=3), PiyasaKurallari())
    assert not s.acildi and s.kritik
    assert "kapatıldı" in s.mesaj
    son = e.emirler[-1]
    assert son[0] == "market" and son[1] == "sell" and son[3].get("reduceOnly") is True
    assert e.pozisyon is None
    assert [x[0] for x in e.emirler].count("STOP_MARKET") == cfg["emir"]["stop_deneme_sayisi"]


def test_tp_konulamazsa_pozisyon_stoplu_kalir(cfg):
    e = SahteEx(tp_hata=True)
    s = CanliBorsa(e, _cfg(cfg)).pozisyon_ac(_sinyal(), RiskSonucu(True, "", miktar=5.0, kaldirac=3), PiyasaKurallari())
    assert s.acildi and "KÂR AL KONULAMADI" in s.mesaj
    assert e.pozisyon is not None


def test_yetim_emirler_iptal(cfg):
    e = SahteEx()
    e.acik["kosullu"] = [{"id": "s1", "type": "stop_market", "info": {"orderType": "STOP_MARKET"}}]
    e.acik["normal"] = [{"id": "n1", "type": "limit", "info": {}}]
    olaylar = CanliBorsa(e, _cfg(cfg)).bakim(["BTC/USDT:USDT"], {}, {})
    assert {i for i, _ in e.iptaller} == {"s1", "n1"}
    assert ("s1", {"trigger": True}) in e.iptaller
    assert all(o.tur == "yetim_iptal" for o in olaylar)


def test_stopsuz_pozisyona_stop_eklenir(cfg):
    e = SahteEx()
    e.pozisyon = {"symbol": "BTC/USDT:USDT", "contracts": 1.0, "side": "long", "entryPrice": 100.0}
    olaylar = CanliBorsa(e, _cfg(cfg)).bakim(["BTC/USDT:USDT"], {}, {"BTC/USDT:USDT": 1.0})
    assert any(o.tur == "stop_eklendi" for o in olaylar)
    assert e.pozisyon is not None


def test_stopsuz_pozisyon_stop_konulamazsa_kapatilir(cfg):
    e = SahteEx(stop_hata=True)
    e.pozisyon = {"symbol": "BTC/USDT:USDT", "contracts": 1.0, "side": "long", "entryPrice": 100.0}
    olaylar = CanliBorsa(e, _cfg(cfg)).bakim(["BTC/USDT:USDT"], {}, {"BTC/USDT:USDT": 1.0})
    assert any(o.tur == "acil_kapatildi" for o in olaylar)
    assert e.pozisyon is None


def test_demo_modu_demo_sunucusuna_baglanir():
    """ccxt nesnesi internetsiz oluşturulur; demo modunda URL'ler demo-fapi'ye döner."""
    from bot.exchange import ccxt_olustur
    assert "demo-fapi" in ccxt_olustur("demo", "a", "b").urls["api"]["fapiPrivate"]
    assert "demo" not in ccxt_olustur("kagit").urls["api"]["fapiPublic"]
