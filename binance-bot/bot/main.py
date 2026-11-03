"""Tek seferlik çalışma: veriyi al → bakım → sinyal → risk → Claude → emir → kayıt → çık.

Kullanım:
    python -m bot.main                 # config.yaml'daki modla
    python -m bot.main --sahte-veri    # internetsiz, sentetik veriyle kağıt modu denemesi
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from .claude_opinion import ClaudeSonucu, claude_gorusu_al, karar_ver
from .config import KOK, AyarHatasi, api_anahtarlari, ayarlari_yukle, kok_yolu
from .exchange import CanliBorsa, CcxtVeri, KagitBorsa, ccxt_olustur
from .journal import Gunluk, iso, log_kur, ms_iso, simdi_utc
from .notify import Bildirici
from .risk import durdur_dosyasi_var_mi, genel_kontrol, gunluk_zarar_orani, parite_kontrolu, pozisyon_hesapla
from .sahte_veri import SahteVeri
from .strategy import Sinyal, kapanmis_mumlar, sinyal_uret

log = logging.getLogger("bot")

KILIT_ADI = ".calisiyor.kilit"
KILIT_ESKIME_SN = 50 * 60


# ---------------------------------------------------------------------------
# Kilit: aynı anda iki kopya çalışmasın
# ---------------------------------------------------------------------------
def kilit_al(klasor: Path) -> Optional[Path]:
    klasor.mkdir(parents=True, exist_ok=True)
    yol = klasor / KILIT_ADI
    if yol.exists() and time.time() - yol.stat().st_mtime > KILIT_ESKIME_SN:
        log.warning("Eski kilit dosyası bulundu (önceki çalışma yarıda kalmış olabilir), siliniyor.")
        yol.unlink(missing_ok=True)
    try:
        fd = os.open(str(yol), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return yol
    except FileExistsError:
        return None


# ---------------------------------------------------------------------------
# Borsa seçimi
# ---------------------------------------------------------------------------
def borsa_olustur(cfg: dict, gunluk: Gunluk, sahte_veri: bool):
    mod = cfg["mod"]
    if sahte_veri:
        if mod != "kagit":
            raise AyarHatasi("--sahte-veri yalnızca kagit moduyla kullanılabilir.")
        return KagitBorsa(SahteVeri(), gunluk, cfg)
    if mod == "kagit":
        return KagitBorsa(CcxtVeri(ccxt_olustur("kagit")), gunluk, cfg)
    anahtar, gizli = api_anahtarlari()
    if not anahtar or not gizli:
        raise AyarHatasi(f"{mod} modu için .env'de BINANCE_API_KEY ve BINANCE_API_SECRET gerekli.")
    if mod == "gercek":
        log.warning("⚠️  GERÇEK PARA MODU — emirler gerçek hesaba gönderilecek.")
    return CanliBorsa(ccxt_olustur(mod, anahtar, gizli), cfg)


def _kisalt(x: Any, n: int = 6) -> str:
    try:
        return f"{float(x):.{n}g}"
    except (TypeError, ValueError):
        return str(x)


def claude_verisi(sinyal: Sinyal, df, sinyaller: dict[str, Sinyal], pozlar: dict[str, dict]) -> dict:
    son = df.tail(24)
    return {
        "sinyal": {"parite": sinyal.sembol, "yon": sinyal.yon, "giris": sinyal.giris, "stop": sinyal.stop,
                   "kar_al": sinyal.kar_al, "atr": sinyal.atr, "neden": sinyal.neden,
                   "mum_zamani_utc": ms_iso(sinyal.mum_zamani)},
        "gostergeler": sinyal.ozet,
        "son_mumlar": [[ms_iso(int(r.timestamp)), r.open, r.high, r.low, r.close, round(r.volume, 2)]
                       for r in son.itertuples()],
        "diger_coinler": {s: {"sinyal": x.yon or "YOK", "neden": x.neden, "gostergeler": x.ozet}
                          for s, x in sinyaller.items() if s != sinyal.sembol},
        "acik_pozisyonlar": {s: p.get("yon") for s, p in pozlar.items()},
    }


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def calistir(cfg: dict, sahte_veri: bool = False) -> int:
    mod = cfg["mod"]
    r, s_cfg, c_cfg = cfg["risk"], cfg["strateji"], cfg["claude"]
    calisma_id = simdi_utc().strftime("%Y%m%dT%H%M%S")
    baslangic = iso()
    gunluk = Gunluk(kok_yolu(cfg["kayit"]["veritabani"]))
    bildirici = Bildirici(cfg.get("telegram", {}), mod)
    hatalar: list[str] = []
    satirlar: list[str] = []
    acilan = 0
    bakiye: Optional[float] = None
    pozlar: dict[str, dict] = {}

    log.info("=" * 70)
    log.info("Çalışma başladı | id=%s | mod=%s%s | claude=%s", calisma_id, mod,
             " (SAHTE VERİ)" if sahte_veri else "", c_cfg.get("kullanim"))

    try:
        borsa = borsa_olustur(cfg, gunluk, sahte_veri)
    except Exception as e:  # noqa: BLE001
        log.exception("Borsa bağlantısı kurulamadı")
        bildirici.gonder(f"❌ Borsa bağlantısı kurulamadı: {e}", "hatalar")
        gunluk.calisma_yaz(calisma_id=calisma_id, baslangic=baslangic, bitis=iso(), mod=mod, hata_sayisi=1,
                           ozet=f"Borsa hatası: {e}")
        gunluk.kapat()
        return 1

    coinler = {c["sembol"]: c for c in cfg["coinler"]}
    tf = cfg.get("zaman_dilimi", "1h")

    # 1) Veri ve sinyaller (bir coindeki hata diğerlerini durdurmaz)
    mum_cache, atr_cache, sinyaller = {}, {}, {}
    simdi_ms = int(time.time() * 1000)
    for sembol in coinler:
        try:
            df = borsa.veri.mumlar(sembol, tf, int(cfg.get("mum_sayisi", 1000)))
            df = kapanmis_mumlar(df, tf, simdi_ms)
            funding = borsa.veri.funding(sembol)
            sinyal = sinyal_uret(sembol, df, funding, s_cfg)
            mum_cache[sembol], sinyaller[sembol] = df, sinyal
            if sinyal.ozet.get("atr"):
                atr_cache[sembol] = float(sinyal.ozet["atr"])
            log.info("%-14s kapanış=%s EMA20=%s EMA50=%s EMA200=%s RSI=%s ATR=%s funding=%s → %s",
                     sembol, _kisalt(sinyal.ozet.get("kapanis")), _kisalt(sinyal.ozet.get("ema20")),
                     _kisalt(sinyal.ozet.get("ema50")), _kisalt(sinyal.ozet.get("ema200")),
                     sinyal.ozet.get("rsi"), _kisalt(sinyal.ozet.get("atr")), funding,
                     sinyal.yon or "sinyal yok")
        except Exception as e:  # noqa: BLE001
            log.error("%s veri/sinyal hatası: %s: %s", sembol, type(e).__name__, e)
            hatalar.append(f"{sembol}: veri hatası: {type(e).__name__}: {e}")
            satirlar.append(f"{sembol}: ⚠️ veri alınamadı")
            gunluk.karar_yaz(calisma_id=calisma_id, mod=mod, sembol=sembol, hata=f"Veri/sinyal hatası: {e}",
                             islem_acildi=False)

    # 2) Bakım: kağıt pozisyonlarının kapanışı / yetim emirler / stop'suz pozisyon koruması
    try:
        for olay in borsa.bakim(list(coinler), mum_cache, atr_cache):
            log.warning("[bakım] %s", olay.mesaj) if olay.tur in ("kritik", "acil_kapatildi") else log.info("[bakım] %s", olay.mesaj)
            satirlar.append(f"🔧 {olay.mesaj}")
            if olay.tur in ("kritik", "acil_kapatildi", "stop_eklendi"):
                bildirici.gonder(f"🚨 {olay.mesaj}", "hatalar")
    except Exception as e:  # noqa: BLE001
        log.exception("Bakım adımı hatası")
        hatalar.append(f"Bakım hatası: {e}")

    # 3) Bakiye, gün başı, genel kapılar
    son_fiyatlar = {s: float(df["close"].iloc[-1]) for s, df in mum_cache.items() if not df.empty}
    zarar = 0.0
    genel_izin, genel_neden = False, "Bakiye okunamadı"
    durdur = durdur_dosyasi_var_mi(KOK, r.get("durdur_dosyasi", "DURDUR"))
    try:
        bakiye = borsa.bakiye(son_fiyatlar)
        pozlar = borsa.acik_pozisyonlar()
        tarih = simdi_utc().strftime("%Y-%m-%d")
        gun_basi = gunluk.gun_basi_al(tarih, mod)
        if gun_basi is None:
            gunluk.gun_basi_yaz(tarih, mod, bakiye)
            gun_basi = bakiye
            log.info("UTC gün başı bakiyesi kaydedildi: %.2f USDT", bakiye)
        zarar = gunluk_zarar_orani(gun_basi, bakiye)
        if zarar >= float(r["gunluk_zarar_limiti"]) and not gunluk.limit_bildirildi_mi(tarih, mod):
            bildirici.gonder(f"⛔ Günlük zarar limiti aşıldı: %{zarar * 100:.2f}. Bugün yeni işlem açılmayacak.",
                             "gunluk_limit")
            gunluk.limit_bildirildi_isaretle(tarih, mod)
        genel_izin, genel_neden = genel_kontrol(durdur, zarar, len(pozlar), r)
        log.info("Bakiye=%.2f USDT | gün başı=%.2f | günlük değişim=%+.2f%% | açık pozisyon=%d/%s %s",
                 bakiye, gun_basi, (-zarar * 100) or 0.0, len(pozlar), r["max_acik_pozisyon"],
                 list(pozlar) if pozlar else "")
        if not genel_izin:
            log.warning("Yeni işlem kapalı: %s", genel_neden)
    except Exception as e:  # noqa: BLE001
        log.exception("Bakiye/pozisyon okunamadı")
        hatalar.append(f"Bakiye/pozisyon hatası: {e}")

    # 4) Coin bazında karar
    for sembol, sinyal in sinyaller.items():
        kayit: dict[str, Any] = dict(calisma_id=calisma_id, mod=mod, sembol=sembol,
                                     mum_zamani=ms_iso(sinyal.mum_zamani), sinyal=sinyal.yon or "YOK",
                                     sinyal_nedeni=sinyal.neden, gostergeler=sinyal.ozet,
                                     giris=sinyal.giris or None, stop=sinyal.stop or None,
                                     kar_al=sinyal.kar_al or None, islem_acildi=False)
        try:
            if not sinyal.var_mi:
                gunluk.karar_yaz(**kayit)
                satirlar.append(f"{sembol}: sinyal yok ({sinyal.neden.replace('Sinyal yok: ', '')})")
                continue

            log.info("%s %s sinyali: giriş=%s stop=%s kâr al=%s", sembol, sinyal.yon,
                     _kisalt(sinyal.giris), _kisalt(sinyal.stop), _kisalt(sinyal.kar_al))

            # Risk kapıları
            izin, neden = genel_kontrol(durdur, zarar, len(pozlar), r) if bakiye is not None else (False, genel_neden)
            if izin:
                izin, neden = parite_kontrolu(sembol, set(pozlar), len(pozlar), r)
            if not izin:
                gunluk.karar_yaz(**kayit, risk_nedeni=neden)
                satirlar.append(f"{sembol}: {sinyal.yon} sinyali → açılmadı ({neden})")
                log.info("%s işlem açılmadı: %s", sembol, neden)
                continue

            kurallar = borsa.veri.kurallar(sembol)
            rs = pozisyon_hesapla(bakiye, sinyal.giris, sinyal.stop, int(coinler[sembol]["max_kaldirac"]), kurallar, r)
            kayit.update(miktar=rs.miktar or None, nominal=rs.nominal or None, kaldirac=rs.kaldirac)
            if not rs.izin:
                gunluk.karar_yaz(**kayit, risk_nedeni=rs.neden)
                satirlar.append(f"{sembol}: {sinyal.yon} sinyali → açılmadı ({rs.neden})")
                log.info("%s işlem açılmadı: %s", sembol, rs.neden)
                continue
            log.info("%s risk: miktar=%s nominal=%.2f USDT kaldıraç=%dx risk=%.2f USDT (%s)", sembol, rs.miktar,
                     rs.nominal, rs.kaldirac, rs.risk_tutari, rs.neden)

            # Claude ikinci görüşü
            cs: Optional[ClaudeSonucu] = None
            if c_cfg.get("kullanim") == "onay":
                log.info("%s için Claude ikinci görüşü isteniyor (en fazla %s sn)...", sembol, c_cfg.get("zaman_asimi_sn", 240))
                cs = claude_gorusu_al(claude_verisi(sinyal, mum_cache[sembol], sinyaller, pozlar), c_cfg, KOK)
                kayit.update(claude_karar=cs.durum, claude_guven=cs.guven, claude_gerekce=cs.gerekce)
                log.info("%s Claude: %s (güven=%s) %s", sembol, cs.durum, cs.guven, cs.gerekce)
            izin, c_neden = karar_ver(cs, c_cfg)
            if not izin:
                gunluk.karar_yaz(**kayit, risk_nedeni=c_neden)
                satirlar.append(f"{sembol}: {sinyal.yon} sinyali → açılmadı ({c_neden})")
                log.info("%s işlem açılmadı: %s", sembol, c_neden)
                continue

            # Emir
            sonuc = borsa.pozisyon_ac(sinyal, rs, kurallar)
            kayit.update(giris=sonuc.giris or sinyal.giris, stop=sonuc.stop or sinyal.stop,
                         kar_al=sonuc.kar_al or sinyal.kar_al, miktar=sonuc.miktar or rs.miktar,
                         islem_acildi=sonuc.acildi)
            gunluk.karar_yaz(**kayit, risk_nedeni=f"{rs.neden}; {c_neden}",
                             emir_bilgisi={"mesaj": sonuc.mesaj, **sonuc.emirler},
                             hata=None if sonuc.acildi else sonuc.mesaj)
            if sonuc.acildi:
                acilan += 1
                pozlar[sembol] = {"yon": sinyal.yon, "miktar": sonuc.miktar, "giris": sonuc.giris}
                metin = (f"✅ {sembol} {sinyal.yon} açıldı\nGiriş: {_kisalt(sonuc.giris)}\nStop: {_kisalt(sonuc.stop)}\n"
                         f"Kâr al: {_kisalt(sonuc.kar_al)}\nMiktar: {sonuc.miktar} (~{rs.nominal:.2f} USDT, {rs.kaldirac}x)\n"
                         f"Risk: {rs.risk_tutari:.2f} USDT\n{c_neden}\n{sonuc.mesaj}")
                log.info("%s İŞLEM AÇILDI: %s", sembol, sonuc.mesaj)
                bildirici.gonder(metin, "islem_acilisi")
                satirlar.append(f"{sembol}: ✅ {sinyal.yon} AÇILDI @ {_kisalt(sonuc.giris)} (stop {_kisalt(sonuc.stop)}, "
                                f"kâr al {_kisalt(sonuc.kar_al)})")
            else:
                log.error("%s işlem açılamadı: %s", sembol, sonuc.mesaj)
                hatalar.append(f"{sembol}: {sonuc.mesaj}")
                satirlar.append(f"{sembol}: ❌ {sonuc.mesaj}")
                bildirici.gonder(("🚨 " if sonuc.kritik else "❌ ") + f"{sembol}: {sonuc.mesaj}", "hatalar")
        except Exception as e:  # noqa: BLE001
            log.exception("%s karar adımı hatası", sembol)
            hatalar.append(f"{sembol}: {e}")
            satirlar.append(f"{sembol}: ⚠️ hata: {e}")
            try:
                gunluk.karar_yaz(**kayit, hata=str(e))
            except Exception:  # noqa: BLE001
                pass

    # 5) Özet
    bas = (f"Saatlik özet {simdi_utc():%Y-%m-%d %H:%M} UTC | mod={mod}"
           + (f" | bakiye={bakiye:.2f} USDT ({(-zarar * 100) or 0.0:+.2f}% gün)" if bakiye is not None else "")
           + f" | açık poz {len(pozlar)}/{r['max_acik_pozisyon']} | açılan {acilan}")
    if not genel_izin:
        bas += f"\n⛔ Yeni işlem kapalı: {genel_neden}"
    ozet = bas + "\n" + "\n".join(satirlar)
    log.info("ÖZET\n%s", ozet)
    if hatalar:
        bildirici.gonder("⚠️ Hatalar:\n" + "\n".join(hatalar), "hatalar")
    bildirici.gonder(ozet, "ozet")
    gunluk.calisma_yaz(calisma_id=calisma_id, baslangic=baslangic, bitis=iso(), mod=mod, bakiye=bakiye,
                       acik_pozisyon=len(pozlar), acilan_islem=acilan, hata_sayisi=len(hatalar), ozet=ozet)
    gunluk.kapat()
    log.info("Çalışma bitti | açılan=%d | hata=%d", acilan, len(hatalar))
    return 1 if hatalar else 0


def ana(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Binance USDⓈ-M Futures saatlik bot (tek seferlik çalışma)")
    ap.add_argument("--config", default=None, help="Ayar dosyası (varsayılan: config.yaml)")
    ap.add_argument("--sahte-veri", action="store_true",
                    help="İnternetsiz sentetik veriyle kağıt modunda dene (yalnızca test amaçlı)")
    a = ap.parse_args(argv)

    try:
        cfg = ayarlari_yukle(a.config)
    except AyarHatasi as e:
        log_kur(KOK / "loglar")
        log.error("Ayar hatası: %s", e)
        return 1

    log_kur(kok_yolu(cfg["kayit"].get("log_klasoru", "loglar")))
    kilit_klasoru = kok_yolu(cfg["kayit"]["veritabani"]).parent
    kilit = kilit_al(kilit_klasoru)
    if kilit is None:
        log.warning("Başka bir çalışma sürüyor (kilit dosyası var). Çıkılıyor.")
        return 0
    try:
        return calistir(cfg, sahte_veri=a.sahte_veri)
    except Exception as e:  # noqa: BLE001 — son savunma hattı
        log.exception("Beklenmeyen hata")
        try:
            Bildirici(cfg.get("telegram", {}), cfg.get("mod", "kagit")).gonder(f"💥 Beklenmeyen hata: {e}", "hatalar")
        except Exception:  # noqa: BLE001
            pass
        return 1
    finally:
        kilit.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(ana())
