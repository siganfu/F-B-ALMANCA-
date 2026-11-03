"""Borsa katmanı.

- CcxtVeri    : ccxt üzerinden mum, funding ve piyasa kuralları (herkese açık veri)
- KagitBorsa  : emir göndermez; sanal pozisyonları SQLite'ta tutar, stop/kâr al'ı mumlarla simüle eder
- CanliBorsa  : demo veya gerçek hesapta emir gönderir (isolated, market giriş + STOP_MARKET + TAKE_PROFIT_MARKET)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from .journal import Gunluk, ms_iso
from .risk import PiyasaKurallari, RiskSonucu, adima_yuvarla
from .strategy import Sinyal

log = logging.getLogger("bot.borsa")


@dataclass
class IslemSonucu:
    acildi: bool
    mesaj: str
    giris: float = 0.0
    stop: float = 0.0
    kar_al: float = 0.0
    miktar: float = 0.0
    emirler: dict = field(default_factory=dict)
    kritik: bool = False          # stop'suz pozisyon riski vb. acil durum


@dataclass
class BakimOlayi:
    sembol: str
    tur: str                      # kagit_kapandi | yetim_iptal | stop_eklendi | acil_kapatildi | kritik | uyari
    mesaj: str


# ---------------------------------------------------------------------------
# ccxt kurulum ve veri
# ---------------------------------------------------------------------------
def ccxt_olustur(mod: str, anahtar: str = "", gizli: str = ""):
    """Binance USDⓈ-M Futures ccxt nesnesi oluşturur."""
    import ccxt  # geç içe aktarma: testler ccxt olmadan da çalışabilsin

    ayar: dict[str, Any] = {
        "enableRateLimit": True,
        "timeout": 20_000,
        "options": {"defaultType": "future", "adjustForTimeDifference": True},
    }
    if anahtar and gizli:
        ayar["apiKey"], ayar["secret"] = anahtar, gizli
    ex = ccxt.binanceusdm(ayar)
    if mod == "demo":
        if hasattr(ex, "enable_demo_trading"):
            ex.enable_demo_trading(True)
            log.info("Binance Demo Trading etkin (enable_demo_trading).")
        else:
            ex.set_sandbox_mode(True)
            log.info("Binance testnet etkin (set_sandbox_mode).")
    return ex


class CcxtVeri:
    """ccxt üzerinden piyasa verisi."""

    def __init__(self, ex):
        self.ex = ex
        self._piyasalar_yuklendi = False

    def _yukle(self) -> None:
        if not self._piyasalar_yuklendi:
            self.ex.load_markets()
            self._piyasalar_yuklendi = True

    def kurallar(self, sembol: str) -> PiyasaKurallari:
        self._yukle()
        m = self.ex.market(sembol)
        hassas, lim = m.get("precision", {}), m.get("limits", {})
        return PiyasaKurallari(
            miktar_adimi=float(hassas.get("amount") or 0.001),
            fiyat_adimi=float(hassas.get("price") or 0.01),
            min_miktar=float((lim.get("amount") or {}).get("min") or 0.0),
            min_nominal=float((lim.get("cost") or {}).get("min") or 0.0),
        )

    def mumlar(self, sembol: str, zaman_dilimi: str, limit: int) -> pd.DataFrame:
        self._yukle()
        satirlar = self.ex.fetch_ohlcv(sembol, timeframe=zaman_dilimi, limit=int(limit))
        df = pd.DataFrame(satirlar, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = df["timestamp"].astype("int64")
        return df.astype({c: float for c in ("open", "high", "low", "close", "volume")})

    def funding(self, sembol: str) -> Optional[float]:
        self._yukle()
        f = self.ex.fetch_funding_rate(sembol)
        oran = f.get("fundingRate")
        return float(oran) if oran is not None else None


# ---------------------------------------------------------------------------
# Kağıt (simülasyon) borsası
# ---------------------------------------------------------------------------
class KagitBorsa:
    """Borsaya emir göndermez. Sanal pozisyonlar SQLite'ta tutulur."""

    def __init__(self, veri, gunluk: Gunluk, cfg: dict):
        self.mod = "kagit"
        self.veri = veri
        self.gunluk = gunluk
        self.cfg = cfg
        self.k = cfg.get("kagit", {})

    def acik_pozisyonlar(self) -> dict[str, dict]:
        return {r["sembol"]: {"yon": r["yon"], "miktar": r["miktar"], "giris": r["giris"],
                              "stop": r["stop"], "kar_al": r["kar_al"], "id": r["id"]}
                for r in self.gunluk.kagit_acik()}

    def _pnl(self, yon: str, giris: float, cikis: float, miktar: float) -> float:
        brut = (cikis - giris) * miktar * (1 if yon == "LONG" else -1)
        komisyon = float(self.k.get("komisyon_orani", 0.0005)) * (giris + cikis) * miktar
        return brut - komisyon

    def bakiye(self, son_fiyatlar: Optional[dict[str, float]] = None) -> float:
        """Sanal özsermaye = başlangıç + gerçekleşen PnL + açık pozisyonların gerçekleşmemiş PnL'i."""
        b = float(self.k.get("baslangic_bakiyesi", 1000)) + self.gunluk.kagit_gerceklesen_pnl()
        for s, p in self.acik_pozisyonlar().items():
            fiyat = (son_fiyatlar or {}).get(s)
            if fiyat:
                brut = (fiyat - p["giris"]) * p["miktar"] * (1 if p["yon"] == "LONG" else -1)
                b += brut
        return b

    def bakim(self, semboller: list[str], mum_cache: dict[str, pd.DataFrame],
              atr_cache: dict[str, float]) -> list[BakimOlayi]:
        """Açık sanal pozisyonları, açılıştan sonraki kapanmış mumlara göre stop/kâr al için kontrol eder.

        Aynı mumda hem stop hem kâr al seviyesi görülmüşse muhafazakâr davranılır: stop sayılır.
        """
        olaylar: list[BakimOlayi] = []
        for r in self.gunluk.kagit_acik():
            df = mum_cache.get(r["sembol"])
            if df is None or df.empty:
                continue
            sonraki = df[df["timestamp"] > int(r["acilis_mum_zamani"])]
            for _, m in sonraki.iterrows():
                cikis, neden = None, None
                if r["yon"] == "LONG":
                    if m["low"] <= r["stop"]:
                        cikis, neden = r["stop"], "STOP"
                    elif m["high"] >= r["kar_al"]:
                        cikis, neden = r["kar_al"], "KAR_AL"
                else:
                    if m["high"] >= r["stop"]:
                        cikis, neden = r["stop"], "STOP"
                    elif m["low"] <= r["kar_al"]:
                        cikis, neden = r["kar_al"], "KAR_AL"
                if cikis is not None:
                    pnl = self._pnl(r["yon"], r["giris"], cikis, r["miktar"])
                    self.gunluk.kagit_kapat(r["id"], cikis, neden, pnl, ms_iso(int(m["timestamp"])))
                    olaylar.append(BakimOlayi(r["sembol"], "kagit_kapandi",
                                              f"{r['sembol']} {r['yon']} {neden} ile kapandı @ {cikis:.6g}, PnL {pnl:+.2f} USDT"))
                    break
        return olaylar

    def pozisyon_ac(self, sinyal: Sinyal, risk: RiskSonucu, kurallar: PiyasaKurallari) -> IslemSonucu:
        stop = adima_yuvarla(sinyal.stop, kurallar.fiyat_adimi)
        kar = adima_yuvarla(sinyal.kar_al, kurallar.fiyat_adimi)
        poz_id = self.gunluk.kagit_ekle(sinyal.sembol, sinyal.yon, risk.miktar, sinyal.giris, stop, kar,
                                        risk.kaldirac, sinyal.mum_zamani)
        return IslemSonucu(True, f"Kağıt pozisyon açıldı (#{poz_id})", giris=sinyal.giris, stop=stop,
                           kar_al=kar, miktar=risk.miktar, emirler={"kagit_id": poz_id})


# ---------------------------------------------------------------------------
# Canlı (demo / gerçek) borsa
# ---------------------------------------------------------------------------
def _emir_turu(o: dict) -> str:
    info = o.get("info") or {}
    return str(info.get("orderType") or info.get("type") or o.get("type") or "").upper()


def _stop_mu(o: dict) -> bool:
    t = _emir_turu(o)
    return "STOP" in t and "TAKE_PROFIT" not in t


def _kar_al_mi(o: dict) -> bool:
    return "TAKE_PROFIT" in _emir_turu(o)


class CanliBorsa:
    """Demo veya gerçek hesapta emir gönderir."""

    def __init__(self, ex, cfg: dict):
        self.ex = ex
        self.mod = cfg["mod"]
        self.cfg = cfg
        self.veri = CcxtVeri(ex)
        self.e = cfg.get("emir", {})
        self._tek_yon_kontrol()

    # ---- hesap ----
    def _tek_yon_kontrol(self) -> None:
        """Hedge modu açıksa uyarır; bot tek yönlü (One-way) mod varsayar."""
        try:
            sonuc = self.ex.fetch_position_mode()
            if sonuc.get("hedged"):
                raise RuntimeError("Hesap Hedge modunda. Binance Futures ayarlarından 'One-way Mode'a geçin.")
        except RuntimeError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("Pozisyon modu okunamadı (devam ediliyor): %s", e)

    def bakiye(self, son_fiyatlar: Optional[dict[str, float]] = None) -> float:
        """Toplam marjin bakiyesi (cüzdan + gerçekleşmemiş PnL), USDT."""
        b = self.ex.fetch_balance()
        info = b.get("info") or {}
        for anahtar in ("totalMarginBalance", "totalWalletBalance"):
            if info.get(anahtar) is not None:
                return float(info[anahtar])
        return float((b.get("USDT") or {}).get("total") or 0.0)

    def acik_pozisyonlar(self) -> dict[str, dict]:
        semboller = [c["sembol"] for c in self.cfg["coinler"]]
        sonuc = {}
        for p in self.ex.fetch_positions(semboller):
            miktar = abs(float(p.get("contracts") or 0.0))
            if miktar <= 0:
                continue
            sonuc[p["symbol"]] = {
                "yon": "LONG" if p.get("side") == "long" else "SHORT",
                "miktar": miktar,
                "giris": float(p.get("entryPrice") or 0.0),
            }
        return sonuc

    def acik_emirler(self, sembol: str) -> list[dict]:
        """Normal + koşullu (algo) açık emirler. Koşullu olanlar '_kosullu' ile işaretlenir."""
        emirler = []
        for o in self.ex.fetch_open_orders(sembol):
            o["_kosullu"] = False
            emirler.append(o)
        try:
            for o in self.ex.fetch_open_orders(sembol, params={"trigger": True}):
                o["_kosullu"] = True
                emirler.append(o)
        except Exception as e:  # noqa: BLE001
            log.warning("%s koşullu emirler okunamadı: %s", sembol, e)
        return emirler

    def _iptal(self, o: dict, sembol: str) -> None:
        self.ex.cancel_order(o["id"], sembol, params={"trigger": True} if o.get("_kosullu") else {})

    # ---- emir yardımcıları ----
    def _kosullu_emir(self, sembol: str, tur: str, taraf: str, miktar: float, tetik: float) -> dict:
        return self.ex.create_order(
            sembol, tur, taraf, miktar, None,
            {"triggerPrice": tetik, "reduceOnly": True, "workingType": self.e.get("calisma_fiyati", "MARK_PRICE")},
        )

    def _stop_koy(self, sembol: str, taraf: str, miktar: float, stop: float) -> Optional[dict]:
        deneme = int(self.e.get("stop_deneme_sayisi", 3))
        for i in range(1, deneme + 1):
            try:
                return self._kosullu_emir(sembol, "STOP_MARKET", taraf, miktar, stop)
            except Exception as e:  # noqa: BLE001
                log.error("%s STOP_MARKET denemesi %d/%d başarısız: %s", sembol, i, deneme, e)
                time.sleep(1.0 * i)
        return None

    def _kar_al_koy(self, sembol: str, taraf: str, miktar: float, fiyat: float) -> Optional[dict]:
        for i in range(1, 3):
            try:
                return self._kosullu_emir(sembol, "TAKE_PROFIT_MARKET", taraf, miktar, fiyat)
            except Exception as e:  # noqa: BLE001
                log.error("%s TAKE_PROFIT_MARKET denemesi %d/2 başarısız: %s", sembol, i, e)
                time.sleep(1.0)
        return None

    def _acil_kapat(self, sembol: str, taraf: str, miktar: float) -> bool:
        for i in range(1, 4):
            try:
                self.ex.create_order(sembol, "market", taraf, miktar, None, {"reduceOnly": True})
                log.warning("%s pozisyonu acil olarak kapatıldı.", sembol)
                return True
            except Exception as e:  # noqa: BLE001
                log.critical("%s ACİL KAPATMA denemesi %d/3 başarısız: %s", sembol, i, e)
                time.sleep(1.0 * i)
        return False

    # ---- bakım: yetim emirler ve stop'suz pozisyonlar ----
    def bakim(self, semboller: list[str], mum_cache: dict[str, pd.DataFrame],
              atr_cache: dict[str, float]) -> list[BakimOlayi]:
        olaylar: list[BakimOlayi] = []
        pozlar = self.acik_pozisyonlar()
        s_cfg = self.cfg["strateji"]
        for sembol in semboller:
            try:
                emirler = self.acik_emirler(sembol)
                poz = pozlar.get(sembol)
                if poz is None:
                    for o in emirler:
                        self._iptal(o, sembol)
                        olaylar.append(BakimOlayi(sembol, "yetim_iptal",
                                                  f"{sembol} yetim emir iptal edildi ({_emir_turu(o)} #{o['id']})"))
                    continue

                ters = "sell" if poz["yon"] == "LONG" else "buy"
                stop_var = any(_stop_mu(o) for o in emirler)
                kar_var = any(_kar_al_mi(o) for o in emirler)
                atr_d = atr_cache.get(sembol)
                if not stop_var:
                    log.critical("%s pozisyonunda STOP YOK! Koruma uygulanıyor.", sembol)
                    stop = None
                    if atr_d:
                        m = float(s_cfg["stop_atr_carpani"]) * atr_d
                        stop = poz["giris"] - m if poz["yon"] == "LONG" else poz["giris"] + m
                        son = float(self.ex.fetch_ticker(sembol).get("last") or 0.0)
                        gecti = son and ((poz["yon"] == "LONG" and son <= stop) or (poz["yon"] == "SHORT" and son >= stop))
                        if gecti:
                            stop = None  # stop seviyesi zaten geçilmiş, kapatmak gerek
                    emir = None
                    if stop:
                        emir = self._stop_koy(sembol, ters, poz["miktar"], float(self.ex.price_to_precision(sembol, stop)))
                    if emir:
                        olaylar.append(BakimOlayi(sembol, "stop_eklendi", f"{sembol} stop'suz pozisyona stop eklendi @ {stop:.6g}"))
                    else:
                        ok = self._acil_kapat(sembol, ters, poz["miktar"])
                        olaylar.append(BakimOlayi(sembol, "acil_kapatildi" if ok else "kritik",
                                                  f"{sembol} stop konulamadı → pozisyon "
                                                  + ("KAPATILDI" if ok else "KAPATILAMADI! ELLE MÜDAHALE EDİN")))
                        continue
                if not kar_var and atr_d:
                    m = float(s_cfg["kar_al_atr_carpani"]) * atr_d
                    tp = poz["giris"] + m if poz["yon"] == "LONG" else poz["giris"] - m
                    if self._kar_al_koy(sembol, ters, poz["miktar"], float(self.ex.price_to_precision(sembol, tp))):
                        olaylar.append(BakimOlayi(sembol, "uyari", f"{sembol} eksik kâr al emri eklendi @ {tp:.6g}"))
            except Exception as e:  # noqa: BLE001
                log.exception("%s bakım hatası", sembol)
                olaylar.append(BakimOlayi(sembol, "uyari", f"{sembol} bakım hatası: {e}"))
        return olaylar

    # ---- pozisyon açma ----
    def pozisyon_ac(self, sinyal: Sinyal, risk: RiskSonucu, kurallar: PiyasaKurallari) -> IslemSonucu:
        sembol = sinyal.sembol
        taraf = "buy" if sinyal.yon == "LONG" else "sell"
        ters = "sell" if taraf == "buy" else "buy"
        emirler: dict[str, Any] = {}

        # 1) Isolated marjin + kaldıraç (pozisyon açılmadan önce; hata varsa işlem yok)
        try:
            try:
                self.ex.set_margin_mode("isolated", sembol)
            except Exception as e:  # noqa: BLE001
                if "No need to change" not in str(e) and "-4046" not in str(e):
                    raise
            self.ex.set_leverage(int(risk.kaldirac), sembol)
        except Exception as e:  # noqa: BLE001
            return IslemSonucu(False, f"Marjin/kaldıraç ayarlanamadı: {e}")

        # 2) Market giriş
        miktar = float(self.ex.amount_to_precision(sembol, risk.miktar))
        try:
            giris_emri = self.ex.create_order(sembol, "market", taraf, miktar)
            emirler["giris"] = giris_emri.get("id")
        except Exception as e:  # noqa: BLE001
            giris_emri = {}
            log.error("%s market giriş hatası: %s — pozisyon oluştu mu kontrol ediliyor", sembol, e)
            try:
                if sembol not in self.acik_pozisyonlar():
                    return IslemSonucu(False, f"Giriş emri başarısız: {e}")
            except Exception:  # noqa: BLE001
                return IslemSonucu(False, f"Giriş emri başarısız ve pozisyon doğrulanamadı: {e}", kritik=True)

        # 3) Gerçekleşen fiyat/miktar
        dolum = float(giris_emri.get("average") or 0.0)
        dolum_miktar = float(giris_emri.get("filled") or miktar)
        try:
            p = self.acik_pozisyonlar().get(sembol)
            if p:
                dolum, dolum_miktar = p["giris"] or dolum, p["miktar"]
        except Exception as e:  # noqa: BLE001
            log.warning("%s pozisyon doğrulanamadı: %s", sembol, e)
        if not dolum:
            dolum = sinyal.giris

        # 4) Stop ve kâr al seviyelerini dolum fiyatına göre (aynı ATR mesafesiyle) yeniden kur
        stop_m = abs(sinyal.giris - sinyal.stop)
        kar_m = abs(sinyal.kar_al - sinyal.giris)
        stop = dolum - stop_m if sinyal.yon == "LONG" else dolum + stop_m
        kar = dolum + kar_m if sinyal.yon == "LONG" else dolum - kar_m
        stop = float(self.ex.price_to_precision(sembol, stop))
        kar = float(self.ex.price_to_precision(sembol, kar))

        # 5) STOP_MARKET — konulamazsa pozisyon HEMEN kapatılır
        stop_emri = self._stop_koy(sembol, ters, dolum_miktar, stop)
        if not stop_emri:
            ok = self._acil_kapat(sembol, ters, dolum_miktar)
            return IslemSonucu(False,
                               "Stop emri konulamadı → pozisyon " + ("kapatıldı" if ok else "KAPATILAMADI! ELLE MÜDAHALE EDİN"),
                               giris=dolum, miktar=dolum_miktar, emirler=emirler, kritik=True)
        emirler["stop"] = stop_emri.get("id")

        # 6) TAKE_PROFIT_MARKET — başarısızsa pozisyon stop'lu kalır, uyarı verilir
        kar_emri = self._kar_al_koy(sembol, ters, dolum_miktar, kar)
        mesaj = "Pozisyon açıldı, stop ve kâr al borsada"
        if kar_emri:
            emirler["kar_al"] = kar_emri.get("id")
        else:
            mesaj = "Pozisyon açıldı, STOP borsada; KÂR AL KONULAMADI (sonraki çalışmada tekrar denenecek)"
        return IslemSonucu(True, mesaj, giris=dolum, stop=stop, kar_al=kar, miktar=dolum_miktar, emirler=emirler)
