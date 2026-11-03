"""Claude ikinci görüşü — Claude Code CLI (`claude -p`) üzerinden, abonelikle.

Ücretli Anthropic API KULLANILMAZ: alt sürece ANTHROPIC_API_KEY aktarılmaz,
böylece Claude Code oturum açılmış abonelik hesabını kullanır.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("bot.claude")

ONAYLA, REDDET = "ONAYLA", "REDDET"
ULASILAMADI, BOZUK = "ULASILAMADI", "BOZUK"


class CevapHatasi(ValueError):
    """Claude cevabı beklenen JSON biçiminde değil."""


@dataclass
class ClaudeSonucu:
    durum: str                     # ONAYLA | REDDET | ULASILAMADI | BOZUK
    guven: Optional[float] = None
    gerekce: str = ""
    ham: str = ""


def ajan_talimati_oku(yol: Path) -> str:
    """Alt ajan dosyasını okur, YAML frontmatter'ı atar, gövdeyi döner."""
    metin = Path(yol).read_text(encoding="utf-8")
    if metin.startswith("---"):
        parcalar = metin.split("---", 2)
        if len(parcalar) == 3:
            metin = parcalar[2]
    return metin.strip()


def _json_adaylari(metin: str) -> list[str]:
    """Metin içindeki dengeli {...} bloklarını sırayla çıkarır."""
    adaylar, derinlik, bas, tirnakta, kacis = [], 0, None, False, False
    for i, ch in enumerate(metin):
        if tirnakta:
            if kacis:
                kacis = False
            elif ch == "\\":
                kacis = True
            elif ch == '"':
                tirnakta = False
            continue
        if ch == '"':
            tirnakta = True
        elif ch == "{":
            if derinlik == 0:
                bas = i
            derinlik += 1
        elif ch == "}" and derinlik > 0:
            derinlik -= 1
            if derinlik == 0 and bas is not None:
                adaylar.append(metin[bas:i + 1])
                bas = None
    return adaylar


def karar_sozlugunu_dogrula(d: Any) -> dict:
    """{"karar","guven","gerekce"} sözlüğünü doğrular ve normalleştirir."""
    if not isinstance(d, dict):
        raise CevapHatasi("JSON bir nesne değil")
    karar = str(d.get("karar", "")).strip().upper()
    if karar not in (ONAYLA, REDDET):
        raise CevapHatasi(f"Geçersiz karar: {d.get('karar')!r}")
    try:
        guven = float(d.get("guven"))
    except (TypeError, ValueError):
        raise CevapHatasi(f"Geçersiz güven: {d.get('guven')!r}") from None
    if not (0.0 <= guven <= 1.0):
        raise CevapHatasi(f"Güven 0-1 aralığında değil: {guven}")
    gerekce = d.get("gerekce", "")
    if not isinstance(gerekce, str):
        gerekce = str(gerekce)
    return {"karar": karar, "guven": guven, "gerekce": gerekce.strip()[:1000]}


def cevabi_coz(cikti: str) -> dict:
    """Claude çıktısından karar sözlüğünü çıkarır.

    Desteklenen biçimler:
      - Doğrudan karar JSON'u
      - `--output-format json` sarmalayıcısı ({"type":"result","result":"..."})
      - Kod bloğu (```json ... ```) veya metin içine gömülü JSON
    """
    if cikti is None or not str(cikti).strip():
        raise CevapHatasi("Boş cevap")
    metin = str(cikti).strip()

    # 1) CLI sarmalayıcısı mı?
    try:
        ust = json.loads(metin)
    except json.JSONDecodeError:
        ust = None
    if isinstance(ust, dict):
        if "karar" in ust:
            return karar_sozlugunu_dogrula(ust)
        if "result" in ust or ust.get("type") == "result":
            if ust.get("is_error"):
                raise CevapHatasi(f"Claude hata döndü: {str(ust.get('result'))[:200]}")
            ic = ust.get("result")
            if isinstance(ic, dict):
                return karar_sozlugunu_dogrula(ic)
            return cevabi_coz(str(ic or ""))

    # 2) Kod bloğu
    blok = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", metin, re.DOTALL)
    if blok:
        try:
            return karar_sozlugunu_dogrula(json.loads(blok.group(1)))
        except json.JSONDecodeError:
            pass

    # 3) Metin içindeki ilk geçerli karar nesnesi
    son_hata: Optional[Exception] = None
    for aday in _json_adaylari(metin):
        try:
            return karar_sozlugunu_dogrula(json.loads(aday))
        except (json.JSONDecodeError, CevapHatasi) as e:
            son_hata = e
    raise CevapHatasi(f"Geçerli karar JSON'u bulunamadı ({son_hata})")


def _alt_surec_ortami() -> dict:
    """Ücretli API'ye kazara gitmemek için API anahtarlarını ortamdan çıkarır."""
    ortam = dict(os.environ)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        ortam.pop(k, None)
    return ortam


def claude_gorusu_al(
    veri: dict,
    c: dict,
    kok: Path,
    calistir: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    komut_bul: Callable[[str], Optional[str]] = shutil.which,
) -> ClaudeSonucu:
    """Alt ajan talimatı + veriyle `claude -p` çalıştırır, sonucu çözer."""
    komut = komut_bul(c.get("komut", "claude"))
    if not komut:
        return ClaudeSonucu(ULASILAMADI, gerekce=f"'{c.get('komut', 'claude')}' komutu PATH'te bulunamadı")

    ajan_yolu = Path(c.get("ajan_dosyasi", ".claude/agents/piyasa-analisti.md"))
    if not ajan_yolu.is_absolute():
        ajan_yolu = kok / ajan_yolu
    try:
        talimat = ajan_talimati_oku(ajan_yolu)
    except OSError as e:
        return ClaudeSonucu(ULASILAMADI, gerekce=f"Ajan dosyası okunamadı: {e}")

    arglar = [komut, "-p", "--output-format", "json", "--system-prompt", talimat,
              "--tools", "", "--no-session-persistence"]
    if c.get("model"):
        arglar += ["--model", str(c["model"])]
    istem = ("Aşağıdaki sinyali değerlendir ve YALNIZCA karar JSON'unu döndür.\n\n"
             + json.dumps(veri, ensure_ascii=False, indent=1, default=str))

    try:
        sonuc = calistir(
            arglar, input=istem, capture_output=True, text=True, encoding="utf-8",
            timeout=int(c.get("zaman_asimi_sn", 240)), cwd=str(kok), env=_alt_surec_ortami(),
        )
    except subprocess.TimeoutExpired:
        return ClaudeSonucu(ULASILAMADI, gerekce=f"Zaman aşımı ({c.get('zaman_asimi_sn', 240)} sn)")
    except OSError as e:
        return ClaudeSonucu(ULASILAMADI, gerekce=f"Claude çalıştırılamadı: {e}")

    if sonuc.returncode != 0:
        hata = (sonuc.stderr or sonuc.stdout or "").strip()[:300]
        return ClaudeSonucu(ULASILAMADI, gerekce=f"Claude çıkış kodu {sonuc.returncode}: {hata}", ham=sonuc.stdout or "")

    try:
        d = cevabi_coz(sonuc.stdout)
    except CevapHatasi as e:
        return ClaudeSonucu(BOZUK, gerekce=str(e), ham=(sonuc.stdout or "")[:2000])
    return ClaudeSonucu(d["karar"], d["guven"], d["gerekce"], ham=(sonuc.stdout or "")[:2000])


def karar_ver(sonuc: Optional[ClaudeSonucu], c: dict) -> tuple[bool, str]:
    """Claude sonucuna ve politikaya göre işlemin açılıp açılmayacağını belirler."""
    if c.get("kullanim", "kapali") == "kapali":
        return True, "Claude kapalı, yalnızca kurallar"
    if sonuc is None:
        sonuc = ClaudeSonucu(ULASILAMADI, gerekce="Sonuç yok")

    if sonuc.durum == ONAYLA:
        esik = float(c.get("min_guven", 0.0) or 0.0)
        if sonuc.guven is not None and sonuc.guven < esik:
            return False, f"Claude onayladı ama güven düşük ({sonuc.guven:.2f} < {esik:.2f})"
        return True, f"Claude ONAYLADI (güven {sonuc.guven:.2f})"
    if sonuc.durum == REDDET:
        return False, f"Claude REDDETTİ: {sonuc.gerekce}"

    # Ulaşılamadı veya bozuk cevap
    if c.get("ulasilamazsa", "bekle") == "kurallar":
        return True, f"Claude {sonuc.durum.lower()} ({sonuc.gerekce}); politika=kurallar, devam"
    return False, f"Claude {sonuc.durum.lower()} ({sonuc.gerekce}); politika=bekle, işlem açılmadı"
