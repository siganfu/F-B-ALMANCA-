# Kullanım Talimatı

Bu belge botu **günlük olarak nasıl kullanacağınızı** anlatır. Teknik kurulum ayrıntıları için [README.md](README.md) dosyasına bakın.

> ⚠️ Kaldıraçlı işlemler sermayenizin tamamını kaybetmenize yol açabilir. Kaybetmeyi göze alamayacağınız parayla çalıştırmayın.

---

## 1. Bot ne yapar, ne yapmaz?

**Yapar**
- Her saatin 1. dakikasında bir kez çalışır, BTC, BNB ve XRP için son kapanmış 1 saatlik mumlara bakar ve kapanır.
- Kurallar sinyal verirse riski hesaplar. Claude açıksa ona ikinci görüş sorar. Her şey uygunsa pozisyon açar.
- Her pozisyonla birlikte borsaya **stop** ve **kâr al** emri koyar. Pozisyon bu emirlerle kendiliğinden kapanır.
- Her kararı kaydeder ve isterseniz Telegram'dan haber verir.

**Yapmaz**
- Pozisyonu elle veya zamanla kapatmaz. Pozisyonu yalnızca borsadaki stop veya kâr al emri kapatır.
- Para çekmez. API anahtarında çekim yetkisi kapalı olmalıdır.
- Sürekli açık kalmaz. Zamanlayıcı (Görev Zamanlayıcı / cron / systemd) çalıştırmazsa hiçbir şey yapmaz.

---

## 2. İlk kurulum (bir kez)

### Windows
1. https://www.python.org/downloads/ adresinden Python 3.10 veya üstünü kurun. Kurulumda **"Add Python to PATH"** kutusunu işaretleyin.
2. `binance-bot` klasörünü örneğin `C:\binance-bot` konumuna koyun.
3. Klasörde adres çubuğuna `powershell` yazıp Enter'a basın. Ardından şunları çalıştırın:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   copy .env.example .env
   python -m pytest
   ```
   Son satırda `72 passed` görmelisiniz.
4. İlk deneme için `run.bat` dosyasına çift tıklayın veya `.\run.bat` yazın.

### Mac / Linux
```bash
cd ~/binance-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m pytest
./run.sh
```

---

## 3. Önerilen yol haritası: Kağıt → Demo → Gerçek

Adımları atlamayın. Her aşamayı bitirmeden bir sonrakine geçmeyin.

### Aşama 1 — Kağıt modu (en az 3–7 gün)
- `config.yaml` içinde `mod: kagit` olmalı. Bu varsayılan ayardır.
- API anahtarı gerekmez, borsaya emir gitmez. Bot sanal 1000 USDT ile çalışır; bu değer `kagit.baslangic_bakiyesi` ayarındadır.
- Zamanlayıcıyı kurun (bkz. [Bölüm 4](#4-otomatik-çalıştırma-saat-başı)) ve botu birkaç gün çalışır bırakın.
- **Kontrol edin:** Log dosyalarında hata var mı? Sinyaller mantıklı mı? Sanal pozisyonlar nasıl kapanıyor?

### Aşama 2 — Demo modu (en az 1–2 hafta)
1. Binance'te **Demo Trading**'e geçin ve oradan bir API anahtarı oluşturun.
2. Anahtarı `.env` dosyasına yazın:
   ```
   BINANCE_API_KEY=demo_anahtariniz
   BINANCE_API_SECRET=demo_gizli_anahtariniz
   ```
3. `config.yaml` içinde `mod: demo` yapın.
4. Demo hesabında Futures ayarlarından **Position Mode → One-way** seçin.
5. `run.bat` veya `./run.sh` ile **elle bir kez** çalıştırın.
6. **Kontrol edin:** Bot bir pozisyon açtığında Binance Demo'da şunlar görünmeli:
   - Pozisyon **Isolated** olmalı, kaldıraç BTC için 3x, BNB ve XRP için 2x olmalı.
   - "Open Orders" altında bir **Stop Market** ve bir **Take Profit Market** emri bulunmalı. Bunlar koşullu (Conditional/Algo) emirler sekmesinde de görünebilir.
   - Stop'u olmayan bir pozisyon **asla** olmamalı.

### Aşama 3 — Gerçek mod
1. Binance'te **gerçek** hesap için yeni bir API anahtarı oluşturun:
   - ✅ Enable Reading, ✅ Enable Futures
   - ❌ **Enable Withdrawals kapalı**
   - ✅ **IP kısıtlaması** açık (bilgisayarınızın veya VPS'inizin IP'si)
2. Futures cüzdanına kullanacağınız USDT'yi aktarın (bkz. [Bölüm 7](#7-ne-kadar-bakiyeyle-başlamalı)).
3. Futures ayarlarında **One-way** modunu seçin.
4. `.env` dosyasına gerçek anahtarı yazın.
5. `config.yaml` içinde şu iki ayarı yapın:
   ```yaml
   mod: gercek
   gercek_para_onayi: true
   ```
   Bu ikisi birlikte olmadan gerçek mod **çalışmaz**. Bu kasıtlı bir güvenlik önlemidir.
6. İlk çalıştırmayı **elle** yapın ve Binance'te emirleri kontrol edin. Sorun yoksa zamanlayıcıyı açık bırakın.

---

## 4. Otomatik çalıştırma (saat başı)

### Windows — Görev Zamanlayıcı
PowerShell'de (yolu kendi klasörünüze göre düzeltin):
```powershell
schtasks /Create /TN "BinanceBot" /TR "\"C:\binance-bot\run.bat\"" /SC HOURLY /MO 1 /ST 00:01 /F
```
- **Durdurmak için:** `schtasks /Change /TN "BinanceBot" /DISABLE`
- **Yeniden başlatmak için:** `schtasks /Change /TN "BinanceBot" /ENABLE`
- **Tamamen silmek için:** `schtasks /Delete /TN "BinanceBot" /F`

Bilgisayar kapalıysa veya uykudaysa bot çalışmaz. Kesintisiz çalışması için VPS önerilir (README → VPS bölümü).

### Mac / Linux — cron
`crontab -e` komutuyla şu satırı ekleyin:
```cron
1 * * * * /home/KULLANICI/binance-bot/run.sh >> /home/KULLANICI/binance-bot/loglar/cron.log 2>&1
```
Durdurmak için satırın başına `#` koyun.

---

## 5. Günlük takip

### Log dosyası
`loglar/bot_YYYY-MM-DD.log`: her gün (UTC) yeni bir dosya açılır. Her çalışmanın sonunda bir **ÖZET** bölümü bulunur:
```
Saatlik özet 2026-11-03 10:01 UTC | mod=demo | bakiye=1000.00 USDT (+0.00% gün) | açık poz 1/2 | açılan 1
BTC/USDT:USDT: LONG sinyali → açılmadı (Claude REDDETTİ: ...)
BNB/USDT:USDT: ✅ LONG AÇILDI @ 737.73 (stop 725.83, kâr al 755.58)
XRP/USDT:USDT: sinyal yok (RSI short bandı sağlanmadı)
```

| Satırda gördüğünüz | Anlamı |
|---|---|
| `sinyal yok (...)` | Kurallar sağlanmadı, normal durum. Çoğu saat böyle geçer. |
| `✅ ... AÇILDI` | Pozisyon açıldı, stop ve kâr al borsaya kondu. |
| `açılmadı (Claude REDDETTİ ...)` | Kurallar sinyal verdi ama Claude onaylamadı. |
| `açılmadı (Stop mesafesi çok ...)` | Stop mesafesi %0.4–%6 aralığının dışında. |
| `açılmadı (... borsa minimumunun altında)` | Bakiye bu coin için yetersiz (bkz. [Bölüm 7](#7-ne-kadar-bakiyeyle-başlamalı)). |
| `açılmadı (... zaten açık pozisyon var)` | O coinde zaten pozisyon var. |
| `⛔ Yeni işlem kapalı: Günlük zarar limiti ...` | Bugün %5 zarar edildi; ertesi UTC güne kadar yeni işlem açılmaz. |
| `⛔ Yeni işlem kapalı: Kill switch ...` | Klasörde `DURDUR` dosyası var. |
| `🔧 ... yetim emir iptal edildi` | Pozisyonu kapanmış coinde kalan emir temizlendi, normal durum. |
| `🚨 ... stop konulamadı → pozisyon KAPATILDI` | Güvenlik devreye girdi, pozisyon kapatıldı. Logu inceleyin. |
| `🚨 ... KAPATILAMADI! ELLE MÜDAHALE EDİN` | **Hemen Binance'e girip pozisyonu elle kapatın.** |
| `⚠️ veri alınamadı` | İnternet veya Binance erişim sorunu. Bot bir sonraki saatte tekrar dener. |

### Karar veritabanı
Tüm kararlar `veri/gunluk.db` dosyasında tutulur. Dosyayı [DB Browser for SQLite](https://sqlitebrowser.org/) ile açabilir veya komut satırından sorgulayabilirsiniz:
```bash
# Son 20 karar
sqlite3 veri/gunluk.db "SELECT zaman, sembol, sinyal, claude_karar, islem_acildi, risk_nedeni FROM kararlar ORDER BY id DESC LIMIT 20;"

# Açılan işlemler
sqlite3 veri/gunluk.db "SELECT zaman, sembol, sinyal, giris, stop, kar_al, miktar FROM kararlar WHERE islem_acildi=1;"

# Kağıt modunda kapanan pozisyonlar ve kâr/zarar
sqlite3 veri/gunluk.db "SELECT sembol, yon, giris, kapanis_fiyati, kapanis_nedeni, ROUND(pnl,2) FROM kagit_pozisyonlar WHERE durum='KAPALI';"
```

### Telegram
1. Telegram'da **@BotFather** → `/newbot` ile bir bot oluşturun ve token'ı alın.
2. Botunuza bir mesaj yazın.
3. `https://api.telegram.org/bot<TOKEN>/getUpdates` adresinden `chat.id` değerini bulun.
4. Token ve chat id'yi `.env` dosyasına yazın, ardından `config.yaml` içinde `telegram.aktif: true` yapın.

Telegram'dan şu bildirimler gelir:
- işlem açılışları
- hatalar
- günlük limit uyarısı (günde bir kez)
- her saatlik özet

İstemediğiniz bildirimi `config.yaml` içinde `false` yaparak kapatabilirsiniz.

---

## 6. Acil durumlar

| Durum | Ne yapmalı |
|---|---|
| **Yeni işlem açılmasın** (pozisyonlar dursun) | Bot klasöründe `DURDUR` adlı boş bir dosya oluşturun. Windows: `type nul > DURDUR`, Mac/Linux: `touch DURDUR`. Silince bot normale döner. |
| **Bot hiç çalışmasın** | Zamanlayıcıyı devre dışı bırakın (bkz. [Bölüm 4](#4-otomatik-çalıştırma-saat-başı)). |
| **Tüm pozisyonları hemen kapat** | Binance → Futures → Positions → **Close All**. Ardından "Open Orders" altındaki emirleri iptal edin; botun bir sonraki çalışması da yetim emirleri temizler. |
| **API anahtarı ele geçirilmiş olabilir** | Binance → API Management → anahtarı **silin**. Yeni anahtar oluşturup `.env` dosyasını güncelleyin. |
| **Log'da "ELLE MÜDAHALE EDİN"** | Binance'e girin, ilgili pozisyonu elle kapatın veya stop koyun. |

---

## 7. Ne kadar bakiyeyle başlamalı?

Binance'in minimum emir kuralları nedeniyle (sentetik verili denemelerle görülen tablo):

| Bakiye | Ne olur |
|---|---|
| **10 USDT** | Yalnızca XRP işlem açabilir. BTC ve BNB "minimumun altında" diye atlanır. İşlem başına risk yaklaşık 0.10 USDT. |
| **100 USDT** | BNB ve XRP normal çalışır (risk yaklaşık 1 USDT/işlem). BTC hâlâ açılmaz, çünkü Binance BTC'de en az 100 USDT'lik emir ister. |
| **150 USDT ve üzeri** | Üç coin de genellikle açılabilir. Kesin eşik o anki ATR'ye (oynaklığa) bağlıdır. |

Risk oranını (`risk.islem_basi_risk`) BTC açılsın diye yükseltmeyin. Bu, işlem başına kaybı artırır.

---

## 8. Sık değiştirilen ayarlar (`config.yaml`)

| Ayar | Varsayılan | Açıklama |
|---|---|---|
| `mod` | `kagit` | `kagit` / `demo` / `gercek` |
| `gercek_para_onayi` | `false` | Gerçek mod için `true` olmalı |
| `coinler[].max_kaldirac` | 3 / 2 / 2 | Coin başına kaldıraç |
| `risk.islem_basi_risk` | `0.01` | İşlem başı risk (%1) |
| `risk.max_acik_pozisyon` | `2` | Aynı anda en fazla açık pozisyon |
| `risk.gunluk_zarar_limiti` | `0.05` | Günlük zarar limiti (%5) |
| `strateji.stop_atr_carpani` | `2.0` | Stop = 2 × ATR |
| `strateji.kar_al_atr_carpani` | `3.0` | Kâr al = 3 × ATR |
| `claude.kullanim` | `onay` | `kapali` yaparsanız yalnızca kurallar karar verir |
| `claude.ulasilamazsa` | `bekle` | Claude'a ulaşılamazsa: `bekle` (açma) / `kurallar` (devam et) |
| `kagit.baslangic_bakiyesi` | `1000` | Kağıt modundaki sanal bakiye |
| `telegram.aktif` | `false` | Telegram bildirimleri |

Ayar değiştirdikten sonra botu yeniden başlatmanız gerekmez; bir sonraki çalışma yeni ayarları okur. Değişiklikten sonra `python -m pytest` çalıştırmak iyi bir alışkanlıktır.

---

## 9. Claude ikinci görüşü

- Claude Code'un bilgisayarınızda kurulu ve **giriş yapılmış** olması gerekir:
  ```bash
  npm install -g @anthropic-ai/claude-code
  claude          # bir kez açıp abonelik hesabınızla giriş yapın
  ```
- Bot ücretli API kullanmaz, aboneliğinizi kullanır.
- Claude kurulu değilse ve `ulasilamazsa: bekle` ayarlıysa **hiç işlem açılmaz**. Log'da `Claude ulasilamadi ... politika=bekle` görürsünüz. Çözüm: Claude'u kurun veya `claude.kullanim: kapali` yapın.
- Claude sinyal başına yaklaşık 10–20 saniye düşünür.

---

## 10. Sorun giderme

| Hata / belirti | Çözüm |
|---|---|
| `Ayar hatası: mod: gercek seçili ama gercek_para_onayi: true değil` | Gerçek modu bilinçli olarak açmak için `gercek_para_onayi: true` yapın. |
| `demo modu için .env'de BINANCE_API_KEY ... gerekli` | `.env` dosyası yok veya boş. `.env.example` dosyasını `.env` adıyla kopyalayıp doldurun. |
| `Hesap Hedge modunda` | Binance Futures → ayarlar → Position Mode → **One-way**. |
| `Invalid API-key, IP, or permissions` | Anahtarda Futures yetkisi açık mı, IP kısıtlamasında doğru IP var mı kontrol edin. Demo anahtarı demo modda, gerçek anahtar gerçek modda kullanılmalı. |
| `Timestamp for this request is outside of the recvWindow` | Bilgisayar saati kaymış. Windows: Ayarlar → Saat → "Şimdi eşitle". Linux: `timedatectl set-ntp true`. |
| `Margin is insufficient` | Bakiye ikinci pozisyon için yetmiyor. Normal bir durumdur, bot bir sonraki saatte tekrar dener. |
| `Başka bir çalışma sürüyor (kilit dosyası var)` | Önceki çalışma hâlâ sürüyor. 50 dakikadan eski kilit dosyası kendiliğinden silinir. |
| `veri alınamadı` | İnternet bağlantısını kontrol edin. Binance bazı ülkelerden ve IP'lerden erişimi engelliyor olabilir. |
| Telegram mesajı gelmiyor | `.env` dosyasında token ve chat id'yi, `config.yaml` içinde `telegram.aktif: true` ayarını kontrol edin. Bota en az bir kez mesaj yazmış olmalısınız. |
| Türkçe karakterler bozuk (Windows) | `run.bat` UTF-8 ayarlar. Doğrudan `python` ile çalıştırıyorsanız önce `set PYTHONUTF8=1` komutunu verin. |

---

## 11. Güvenlik kontrol listesi

- [ ] API anahtarında **çekim yetkisi kapalı**
- [ ] API anahtarında **IP kısıtlaması** açık
- [ ] `.env` dosyası kimseyle paylaşılmadı, git'e eklenmedi
- [ ] Futures hesabı **One-way** modunda
- [ ] Demo modda en az 1–2 hafta sorunsuz çalıştı
- [ ] Gerçek modda ilk çalıştırma elle yapıldı ve stop / kâr al emirleri Binance'te görüldü
- [ ] Telegram bildirimleri açık (hataları anında görmek için)
- [ ] `DURDUR` dosyasının nasıl kullanıldığını biliyorum
