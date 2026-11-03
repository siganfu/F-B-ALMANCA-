# Binance USDⓈ-M Futures Saatlik Bot

BTC, BNB ve XRP için **kural tabanlı**, kaldıraçlı, saatte bir kez çalışıp kapanan bir trading botu.
İsteğe bağlı olarak her sinyale **Claude Code** (abonelikle, ücretsiz) ikinci görüş verir.

> ⚠️ **Risk uyarısı:** Kaldıraçlı vadeli işlemler sermayenizin tamamını kaybetmenize yol açabilir.
> Bu bot yatırım tavsiyesi değildir. Önce **kağıt**, sonra en az birkaç hafta **demo** modunda deneyin.

---

## İçindekiler
1. [Nasıl çalışır?](#nasıl-çalışır)
2. [Kurulum](#kurulum)
3. [Binance API anahtarı](#binance-api-anahtarı)
4. [Demo hesap](#demo-hesap-binance-futures-demo-trading)
5. [Çalışma modları](#çalışma-modları)
6. [Claude ikinci görüş](#claude-ikinci-görüş)
7. [Saat başı zamanlama (Windows / Mac / Linux)](#saat-başı-zamanlama)
8. [Telegram kurulumu](#telegram-kurulumu)
9. [VPS'e taşıma (systemd timer)](#vpse-taşıma-systemd-timer)
10. [Kayıtlar, kill switch, testler](#kayıtlar)

---

## Nasıl çalışır?

Her çalışmada (saatin 1. dakikası) bot şunları yapar ve kapanır:

1. **Veri:** Her coin için 1 saatlik mumları çeker, **henüz kapanmamış son mumu atar**, funding oranını alır.
2. **Bakım:**
   - Kağıt modunda sanal pozisyonların stop/kâr al seviyelerine değip değmediğini kontrol eder.
   - Demo/gerçekte pozisyonu kapanmış paritelerdeki **yetim emirleri iptal eder**.
   - **Stop emri olmayan pozisyon** bulursa stop koyar; koyamazsa pozisyonu kapatır.
3. **Genel kapılar:** `DURDUR` dosyası, günlük %5 zarar limiti, en fazla 2 açık pozisyon.
4. **Strateji** (her coin ayrı, bir coindeki hata diğerlerini durdurmaz):

   | | LONG | SHORT |
   |---|---|---|
   | Trend | kapanış > EMA200 | kapanış < EMA200 |
   | Momentum | EMA20 > EMA50 | EMA20 < EMA50 |
   | RSI(14) | 50 – 70 | 30 – 50 |
   | Funding | < +%0.05 | > −%0.05 |
   | Stop | giriş − 2×ATR(14) | giriş + 2×ATR(14) |
   | Kâr al | giriş + 3×ATR(14) | giriş − 3×ATR(14) |

5. **Risk motoru** (sabit kurallar):
   - Risk = bakiyenin %1'i.
   - Miktar = risk / stop mesafesi.
   - Nominal değer en fazla bakiye × coin kaldıracı olabilir (BTC 3x, BNB 2x, XRP 2x).
   - Stop mesafesi %0.4'ten küçük veya %6'dan büyükse işlem açılmaz.
   - Miktar borsa hassasiyetine aşağı yuvarlanır, minimum miktar ve minimum emir değeri kontrol edilir.
6. **Claude** (açıksa) ONAYLA demezse işlem açılmaz.
7. **Emir:**
   - Isolated marjin ve kaldıraç ayarlanır, ardından market emirle girilir.
   - Hemen ardından borsaya `STOP_MARKET` (reduceOnly, MARK_PRICE) ve `TAKE_PROFIT_MARKET` konur.
   - **Stop konulamazsa pozisyon hemen kapatılır.**
8. **Kayıt:** Her karar `veri/gunluk.db` (SQLite) dosyasına yazılır, ayrıca `loglar/bot_YYYY-MM-DD.log` tutulur. Açıksa Telegram'a özet gider.

Tüm parametreler `config.yaml` içindedir.

### Proje yapısı
```
binance-bot/
├── bot/
│   ├── indicators.py      EMA, RSI, ATR (pandas)
│   ├── strategy.py        sinyal kuralları, kapanmış mum filtresi
│   ├── risk.py            boyut, limitler, kill switch
│   ├── exchange.py        ccxt (demo/gerçek) + kağıt simülasyonu
│   ├── claude_opinion.py  `claude -p` çağrısı + JSON çözücü
│   ├── notify.py          Telegram
│   ├── journal.py         SQLite + log dosyası
│   ├── sahte_veri.py      internetsiz test verisi
│   ├── config.py          ayar yükleme/doğrulama
│   └── main.py            tek seferlik çalışma
├── .claude/agents/piyasa-analisti.md
├── tests/                 pytest (internetsiz)
├── config.yaml  .env.example  requirements.txt
└── run.sh  run.bat
```

---

## Kurulum

Python **3.10+** gerekir.

**Mac / Linux**
```bash
cd binance-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # demo/gerçek veya Telegram için doldurun
python -m pytest              # testler (internet gerekmez)
./run.sh                      # kağıt modunda bir kez çalıştır
```

**Windows (PowerShell)**
```powershell
cd binance-bot
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m pytest
.\run.bat
```

İnternet olmadan tüm akışı denemek için şu komutu kullanın. Yalnızca kağıt modunda çalışır, sentetik veri kullanır, gerçek karar için değildir:
```bash
./run.sh --sahte-veri
```

---

## Binance API anahtarı

1. Binance → **Profil → API Management → Create API** (System generated / HMAC).
2. İzinler:
   - ✅ **Enable Reading**
   - ✅ **Enable Futures**
   - ❌ **Enable Withdrawals — KESİNLİKLE KAPALI**
   - ❌ Enable Spot & Margin Trading, Universal Transfer vb. — kapalı
3. **Restrict access to trusted IPs only** seçin, evinizin veya VPS'inizin sabit IP'sini yazın.
   IP'nizi öğrenmek için: `curl ifconfig.me`
4. Anahtarları `.env` dosyasına yazın:
   ```
   BINANCE_API_KEY=...
   BINANCE_API_SECRET=...
   ```
5. Futures hesabınızda **Position Mode = One-way** olmalı (Hedge modu desteklenmez; bot hedge modunu görürse durur).
6. `.env` dosyasını kimseyle paylaşmayın, git'e eklemeyin (`.gitignore` zaten dışlar).

---

## Demo hesap (Binance Futures Demo Trading)

1. Binance'e giriş yapın → Futures sayfasında **Demo Trading**'e geçin (veya `https://demo.binance.com`).
2. Demo hesap için ayrı bir API anahtarı oluşturun (Demo Trading → API Management).
3. Bu anahtarı `.env` dosyasına yazın ve `config.yaml` içinde `mod: demo` yapın.
4. Bot, ccxt'nin `enable_demo_trading(True)` özelliğiyle `demo-fapi.binance.com` adresine bağlanır.
   ccxt'nin eski sürümlerinde bu özellik yoksa `set_sandbox_mode` kullanılır.

---

## Çalışma modları

| Mod | Ne yapar | Anahtar |
|---|---|---|
| `kagit` (varsayılan) | Emir göndermez. Sanal pozisyonları SQLite'ta tutar, stop/kâr al'ı sonraki mumlarla simüle eder (aynı mumda ikisi de görülürse muhafazakâr olarak stop sayılır). Başlangıç bakiyesi `kagit.baslangic_bakiyesi`. | Gerekmez |
| `demo` | Binance Demo Trading hesabında gerçek emir, sahte para | Demo API |
| `gercek` | **Gerçek para.** Yalnızca `gercek_para_onayi: true` ise başlar | Gerçek API |

> Not: Risk motoru nominal değeri `bakiye × max_kaldıraç` ile sınırlar. Isolated modda bir pozisyonun
> marjini en fazla bakiyenin tamamı kadar olabilir. Stop çok darsa ilk pozisyon bakiyenin büyük kısmını
> marjin olarak kullanabilir ve ikinci pozisyon "yetersiz marjin" ile reddedilebilir. Bu durum loglanır.

---

## Claude ikinci görüş

- `.claude/agents/piyasa-analisti.md` alt ajanın talimatıdır. Ajan yalnızca şunu döner:
  `{"karar": "ONAYLA"|"REDDET", "guven": 0-1, "gerekce": "..."}`.
  Pozisyon büyüklüğü, kaldıraç veya stop önermez.
- Kurallar sinyal verdiğinde ve risk kontrolü geçtiğinde bot şu komutu çalıştırır:
  `claude -p --output-format json --system-prompt <talimat> --tools ""`.
  Zaman aşımı 240 saniyedir. Veri (sinyal, göstergeler, son 24 mum, diğer coinler, açık pozisyonlar) stdin'den gönderilir.
- **Ücretli API kullanılmaz:** alt sürece `ANTHROPIC_API_KEY` aktarılmaz, Claude Code'da oturum açtığınız Pro/Max aboneliği kullanılır.
  Kurulum için bir kez `npm install -g @anthropic-ai/claude-code`, ardından `claude` komutuyla giriş yapın.
  Botun çalıştığı kullanıcıyla giriş yapılmış olmalı (VPS'te de).
- `config.yaml` ayarları:
  ```yaml
  claude:
    kullanim: onay        # kapali | onay
    ulasilamazsa: bekle   # bekle: işlem açma | kurallar: kural kararıyla devam
    min_guven: 0.0        # ONAYLA dese bile güven bunun altındaysa açma
  ```
- Claude ONAYLA demezse işlem açılmaz. Ulaşılamazsa veya JSON bozuksa ne olacağını `ulasilamazsa` belirler.

---

## Saat başı zamanlama

Bot **her saatin 1. dakikasında** çalışacak şekilde tasarlandı. Saat başında kapanan mumun
borsaya yerleşmesi için bir dakika beklenir. Aynı anda iki kopya çalışmaz (kilit dosyası).

### Windows — Görev Zamanlayıcı

**Komutla** (yönetici olmayan PowerShell yeterli; yolu kendinize göre düzeltin):
```powershell
schtasks /Create /TN "BinanceBot" /TR "\"C:\Users\KULLANICI\binance-bot\run.bat\"" /SC HOURLY /MO 1 /ST 00:01 /F
```

**Arayüzle:**
1. Başlat → *Görev Zamanlayıcı* → **Görev Oluştur**.
2. *Genel*: Ad `BinanceBot`. "Kullanıcı oturum açmış olsun veya olmasın çalıştır" seçeneğini isteğe bağlı işaretleyin.
3. *Tetikleyiciler* → Yeni:
   - Günlük, başlangıç **00:01**
   - "Görevi şu sıklıkla yinele: **1 saat**", süre: **Süresiz**
4. *Eylemler* → Yeni:
   - Program: `C:\Users\KULLANICI\binance-bot\run.bat`
   - Başlangıç konumu: `C:\Users\KULLANICI\binance-bot`
5. *Ayarlar*:
   - "Görev zaten çalışıyorsa: **Yeni örnek başlatma**"
   - "Görevi şu süreden uzun çalışırsa durdur: **30 dakika**"
6. Bilgisayar uykudaysa çalışmaz. *Koşullar* sekmesinde "Görevi çalıştırmak için bilgisayarı uyandır" seçeneğini işaretleyin.

### Mac / Linux — cron
```bash
crontab -e
```
Şu satırı ekleyin (yolu düzeltin):
```cron
1 * * * * /home/KULLANICI/binance-bot/run.sh >> /home/KULLANICI/binance-bot/loglar/cron.log 2>&1
```
Mac'te cron'a **Tam Disk Erişimi** vermeniz gerekebilir: Sistem Ayarları → Gizlilik → Tam Disk Erişimi → `/usr/sbin/cron`.

---

## Telegram kurulumu

1. Telegram'da **@BotFather** → `/newbot` → bir ad verin → **token**'ı kopyalayın.
2. Yeni botunuza bir mesaj yazın (örneğin "merhaba").
3. Tarayıcıda `https://api.telegram.org/bot<TOKEN>/getUpdates` adresini açın, `"chat":{"id":...}` değerini alın.
4. `.env` dosyasına yazın:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_CHAT_ID=123456789
   ```
5. `config.yaml` içinde `telegram.aktif: true` yapın.
   `islem_acilisi`, `hatalar`, `gunluk_limit` ve `ozet` ayrı ayrı açılıp kapatılabilir.
   Telegram'a ulaşılamazsa bot çalışmaya devam eder, yalnızca log'a uyarı yazar.

---

## VPS'e taşıma (systemd timer)

Ubuntu/Debian örneği. Kullanıcı adı `bot`, klasör `/home/bot/binance-bot` varsayılmıştır.

```bash
sudo apt update && sudo apt install -y python3 python3-venv git nodejs npm
git clone <depo-adresi> ~/depo && cp -r ~/depo/binance-bot ~/binance-bot && cd ~/binance-bot
# (veya klasörü bilgisayarınızdan scp ile kopyalayın)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env                          # anahtarlar; Binance'te VPS IP'sini izinli listeye ekleyin
.venv/bin/python -m pytest
# Claude kullanacaksanız:
sudo npm install -g @anthropic-ai/claude-code && claude    # bir kez giriş yapın
```

`/etc/systemd/system/binance-bot.service`:
```ini
[Unit]
Description=Binance saatlik trading botu (tek seferlik)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=bot
WorkingDirectory=/home/bot/binance-bot
ExecStart=/home/bot/binance-bot/run.sh
TimeoutStartSec=1800
Environment=PYTHONUNBUFFERED=1
```

`/etc/systemd/system/binance-bot.timer`:
```ini
[Unit]
Description=Binance botunu her saatin 1. dakikasında çalıştır

[Timer]
OnCalendar=*-*-* *:01:00
Persistent=true
AccuracySec=10s

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now binance-bot.timer
systemctl list-timers binance-bot.timer      # sonraki çalışma zamanı
journalctl -u binance-bot.service -n 100     # son çıktılar
sudo systemctl start binance-bot.service     # elle bir kez çalıştır
```
VPS saatinin doğru olduğundan emin olun (`timedatectl`, NTP açık olmalı).

---

## Kayıtlar

- **`veri/gunluk.db`**: SQLite veritabanı. Tablolar:
  - `kararlar`: her coin için her çalışmada bir satır. Sinyal, gösterge özeti, Claude kararı, risk nedeni, işlem açıldı mı, emir kimlikleri, hata.
  - `gun_basi`: UTC gün başı bakiyesi.
  - `calismalar`: çalışma özetleri.
  - `kagit_pozisyonlar`: kağıt modunun sanal pozisyonları.

  Örnek sorgu:
  ```bash
  sqlite3 veri/gunluk.db "SELECT zaman, sembol, sinyal, claude_karar, risk_nedeni, islem_acildi FROM kararlar ORDER BY id DESC LIMIT 20;"
  ```
- **`loglar/bot_YYYY-MM-DD.log`**: günlük log dosyası (UTC tarih).

### Kill switch
Proje klasöründe **`DURDUR`** adlı bir dosya varsa yeni işlem açılmaz. Bakım adımı yine çalışır: yetim emirler temizlenir, stop koruması sürer.
```bash
touch DURDUR      # Mac/Linux
type nul > DURDUR # Windows
```
Silinince bot normale döner. Açık pozisyonlar kendiliğinden kapanmaz, borsadaki stop ve kâr al emirleri durur.

### Günlük zarar limiti
UTC gün başındaki ilk çalışmada bakiye (gerçekleşmemiş PnL dahil) SQLite'a kaydedilir.
Bakiye bundan %5 düşükse o gün yeni işlem açılmaz ve Telegram'a bir kez bildirim gider.

### Testler
```bash
python -m pytest
```
Testler internetsiz çalışır. Göstergeler, strateji, risk motoru, Claude cevap çözücüsü ve politikası, kağıt simülasyonu, sahte borsayla emir güvenliği (stop konulamazsa kapatma, yetim emir iptali) ve uçtan uca akış test edilir.
