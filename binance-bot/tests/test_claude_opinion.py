import json
import subprocess

import pytest

from bot.claude_opinion import (
    BOZUK, ONAYLA, REDDET, ULASILAMADI, CevapHatasi, ClaudeSonucu, ajan_talimati_oku,
    cevabi_coz, claude_gorusu_al, karar_ver,
)
from tests.conftest import KOK


# ---------------- çözücü ----------------
def test_duz_json():
    d = cevabi_coz('{"karar": "ONAYLA", "guven": 0.8, "gerekce": "Trend güçlü"}')
    assert d == {"karar": "ONAYLA", "guven": 0.8, "gerekce": "Trend güçlü"}


def test_kucuk_harf_karar_normallestirilir():
    assert cevabi_coz('{"karar": "reddet", "guven": 1, "gerekce": "x"}')["karar"] == "REDDET"


def test_cli_sarmalayici():
    ic = json.dumps({"karar": "REDDET", "guven": 0.6, "gerekce": "Funding kalabalık"}, ensure_ascii=False)
    sarma = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": ic})
    assert cevabi_coz(sarma)["karar"] == "REDDET"


def test_kod_blogu_ve_metin_icinde():
    assert cevabi_coz('Değerlendirme:\n```json\n{"karar":"ONAYLA","guven":0.7,"gerekce":"ok"}\n```')["guven"] == 0.7
    assert cevabi_coz('Sonuç şu: {"karar":"REDDET","guven":0.4,"gerekce":"a {b} c"} bitti')["gerekce"] == "a {b} c"


def test_sarmalayici_icinde_kod_blogu():
    sarma = json.dumps({"type": "result", "is_error": False,
                        "result": '```json\n{"karar":"ONAYLA","guven":0.9,"gerekce":"t"}\n```'})
    assert cevabi_coz(sarma)["karar"] == "ONAYLA"


@pytest.mark.parametrize("bozuk", [
    "", "   ", "merhaba", "{bozuk json", '{"karar": "BELKI", "guven": 0.5, "gerekce": ""}',
    '{"karar": "ONAYLA", "guven": 1.5, "gerekce": ""}', '{"karar": "ONAYLA", "guven": -0.1}',
    '{"karar": "ONAYLA", "guven": "yüksek"}', '{"karar": "ONAYLA"}', "[1, 2]",
    json.dumps({"type": "result", "is_error": True, "result": "Not logged in"}),
])
def test_bozuk_cevaplar(bozuk):
    with pytest.raises(CevapHatasi):
        cevabi_coz(bozuk)


def test_ajan_dosyasi_frontmatter_atilir():
    t = ajan_talimati_oku(KOK / ".claude/agents/piyasa-analisti.md")
    assert not t.startswith("---")
    assert '"karar"' in t and "ÖNERME" in t


# ---------------- subprocess (sahte) ----------------
C = {"kullanim": "onay", "ulasilamazsa": "bekle", "zaman_asimi_sn": 240, "komut": "claude",
     "ajan_dosyasi": ".claude/agents/piyasa-analisti.md", "min_guven": 0.0}


def _sahte(stdout="", rc=0, hata=None, kayit=None):
    def calistir(args, **kw):
        if kayit is not None:
            kayit.update(args=args, **kw)
        if hata:
            raise hata
        return subprocess.CompletedProcess(args, rc, stdout=stdout, stderr="err")
    return calistir


def test_basarili_cagri_ve_arguman_guvenligi(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ucretli")
    kayit = {}
    out = json.dumps({"type": "result", "is_error": False,
                      "result": '{"karar":"ONAYLA","guven":0.75,"gerekce":"uyumlu"}'})
    s = claude_gorusu_al({"x": 1}, C, KOK, calistir=_sahte(out, kayit=kayit), komut_bul=lambda k: "/usr/bin/claude")
    assert s.durum == ONAYLA and s.guven == 0.75
    assert kayit["timeout"] == 240
    assert "-p" in kayit["args"] and "--system-prompt" in kayit["args"]
    assert "ANTHROPIC_API_KEY" not in kayit["env"]  # ücretli API'ye gidilmez
    assert '"x": 1' in kayit["input"]


def test_zaman_asimi():
    s = claude_gorusu_al({}, C, KOK, calistir=_sahte(hata=subprocess.TimeoutExpired("claude", 240)),
                         komut_bul=lambda k: "claude")
    assert s.durum == ULASILAMADI and "Zaman aşımı" in s.gerekce


def test_komut_yok():
    s = claude_gorusu_al({}, C, KOK, calistir=_sahte(), komut_bul=lambda k: None)
    assert s.durum == ULASILAMADI


def test_cikis_kodu_hatasi():
    s = claude_gorusu_al({}, C, KOK, calistir=_sahte("", rc=1), komut_bul=lambda k: "claude")
    assert s.durum == ULASILAMADI


def test_bozuk_cikti():
    s = claude_gorusu_al({}, C, KOK, calistir=_sahte("Bence alınabilir."), komut_bul=lambda k: "claude")
    assert s.durum == BOZUK


# ---------------- karar politikası ----------------
def test_kapali_ise_kurallar():
    assert karar_ver(None, {**C, "kullanim": "kapali"})[0] is True


def test_onayla_reddet():
    assert karar_ver(ClaudeSonucu(ONAYLA, 0.8, "ok"), C)[0] is True
    assert karar_ver(ClaudeSonucu(REDDET, 0.9, "hayır"), C)[0] is False


def test_min_guven():
    assert karar_ver(ClaudeSonucu(ONAYLA, 0.5, "ok"), {**C, "min_guven": 0.6})[0] is False
    assert karar_ver(ClaudeSonucu(ONAYLA, 0.6, "ok"), {**C, "min_guven": 0.6})[0] is True


@pytest.mark.parametrize("durum", [ULASILAMADI, BOZUK])
def test_ulasilamazsa_politikasi(durum):
    assert karar_ver(ClaudeSonucu(durum, gerekce="x"), {**C, "ulasilamazsa": "bekle"})[0] is False
    assert karar_ver(ClaudeSonucu(durum, gerekce="x"), {**C, "ulasilamazsa": "kurallar"})[0] is True
    assert karar_ver(None, C)[0] is False
