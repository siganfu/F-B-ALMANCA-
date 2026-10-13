# F&B Deutsch Akademie — Aşama 1 (MVP)

**Ephesia Resort Hotel** F&B personeli için mesleki Almanca uygulaması.
*Almanca Öğren, Güvenle Servis Yap!*

Tek bir web uygulaması iki şekilde kullanılır:

| Sürüm | Nerede | Nasıl çalışır |
|---|---|---|
| **APK (Android WebView)** | `android/` | `web/` klasörü APK'nın içine gömülür, **tamamen internetsiz** açılır. Ses ve mikrofon Android'in yerel servislerine bağlanır. |
| **Web / PWA** | `web/` | Herhangi bir HTTPS sunucusunda yayınlanır, Android ve iPhone'da "Ana ekrana ekle" ile uygulama gibi kurulur, ilk açılıştan sonra internetsiz çalışır. |

## Aşama 1'de çalışan özellikler

- Ana sayfa: karşılama, günlük hedef, öğrenilen ifade sayısı, ilerleme %, günlük seri, günün ifadesi
- **HIZLI ALMANCA** (servis modu): Türkçe/Almanca çevrimdışı arama, Almanca dinle, yavaş dinle, favoriler, sık kullanılanlar üstte, "misafire göster" tam ekranı
- 10 modül × Başlangıç / Orta / İleri seviye, toplam **103 kontrol edilmiş ifade** (her biri Türkçe çeviri, Türkçe okunuş, kullanım yeri, örnek misafir cevabı ile)
- İfade kartları: ileri/geri, kaydırma, 🔊 Dinle, 🐢 Yavaş Dinle, ⏹ Durdur, 🎤 Konuş, favori, "Öğrendim"
- Konuşma değerlendirme: söylenen cümle metne çevrilir, hedefle kelime kelime karşılaştırılır; doğru / eksik / fazladan kelimeler renkli gösterilir (fonetik analiz değildir, ekranda belirtilir)
- Mini test: dinle ve anla, 10 soru
- Göreve göre önerilen modüller (Garson, Komi, Barmen, Bar Kaptanı, Restoran Hostesi, Restoran Kaptanı, Restoran Şefi)
- Alerjen modülünde "doğrulanmamış bilgi verme" uyarısı ve mutfaktan teyit cümleleri
- Aynı telefonda birden fazla personel profili, açık/koyu tema, ses ve mikrofon tanılama ekranı
- PWA: manifest, simgeler, service worker, "Yeni sürüm hazır" güncelleme bildirimi

**DEMO olarak işaretli:** Giriş sistemi yok; profiller ve ilerleme yalnızca o cihazda (localStorage) tutulur. Davetli hesaplar, Supabase, IndexedDB senkronizasyonu ve yönetici paneli Aşama 2–3 kapsamındadır.

## APK nasıl alınır?

### Yol A — GitHub Actions (bilgisayara Android Studio kurmadan)
1. GitHub'da yeni bir repo açın, bu klasörün tamamını yükleyin (`.github` klasörü dahil).
2. **Actions** sekmesi → "APK derle" iş akışı otomatik çalışır (veya *Run workflow*).
3. ~5 dk sonra çalışmanın altındaki **Artifacts** bölümünden `FB-Deutsch-Akademie-APK` zip'ini indirin.
   - `FB-Deutsch-Akademie.apk` → personele dağıtılacak sürüm
   - `FB-Deutsch-Akademie-debug.apk` → test sürümü
4. APK'yı telefona gönderin, "Bilinmeyen kaynaklardan yükleme" iznini verip kurun.

Aynı iş akışı `web/` klasörünü GitHub Pages'te de yayınlar (Settings → Pages → Source: *GitHub Actions*). Bu adres iPhone kullanıcıları için PWA bağlantısıdır.

### Yol B — Android Studio
1. Android Studio ile `android/` klasörünü açın (*Open*).
2. Gradle senkronizasyonu bitince **Build → Build App Bundle(s) / APK(s) → Build APK(s)**.
3. APK: `android/app/build/outputs/apk/`.

Komut satırından: `cd android && ./gradlew assembleRelease` (JDK 17 + Android SDK 35 gerekir).

### İmza
Varsayılan olarak release APK debug anahtarıyla imzalanır (kurum içi dağıtım için kurulabilir). Google Play'e yüklenecekse kendi anahtarınızı üretip şu ortam değişkenlerini verin: `FBDA_KEYSTORE`, `FBDA_KEYSTORE_PASSWORD`, `FBDA_KEY_ALIAS`, `FBDA_KEY_PASSWORD` (GitHub'da *Secrets* olarak).

## Ses mimarisi (modüler)

`web/index.html` içinde sağlayıcılar sırayla denenir:

1. **Bulut TTS** — `CLOUD_TTS.endpoint` doldurulursa (POST `{text, lang:'de-DE', rate}` → `audio/mpeg`). Daha doğal ses için Google Cloud TTS, Azure veya ElevenLabs önüne küçük bir sunucu konabilir; API anahtarı istemcide tutulmamalıdır.
2. **Android yerel TTS** — APK içinde `FBNative` köprüsü (Almanca `de-DE`, en kaliteli yüklü ses seçilir). Almanca ses paketi yoksa uygulama yükleme ekranını açar.
3. **Web Speech API** — tarayıcıda `speechSynthesis`, Almanca ses önceliklidir; bulunamazsa kullanıcı uyarılır.

Konuşma tanıma: APK'da Android `SpeechRecognizer`, tarayıcıda `webkitSpeechRecognition` (Chrome/Safari, HTTPS gerekir). Desteklenmiyorsa açıklama gösterilir.

## Test durumu

Tarayıcıda (Chromium, 390×844 mobil görünüm) denendi: profil oluşturma, ana sayfa, modül listesi, kartlar, öğrenildi işaretleme, konuşma sonucu ekranı, hızlı arama + favoriler, mini test, profil, koyu tema, service worker kaydı — konsol hatası yok, yatay taşma yok.

**Henüz test edilmedi:** APK derlemesi (bu ortamın Android SDK'ya erişimi yoktu), gerçek cihazda ses çıkışı ve mikrofonla konuşma tanıma, iPhone Safari. İlk APK'yı GitHub Actions ile derleyip bir Android telefonda 🔊 ve 🎤 butonlarını deneyin.

## İçerik ekleme

İfadeler `web/index.html` başındaki `MODULES` dizisindedir:
```
['seviye','Almanca','Türkçe','Türkçe okunuş','Örnek cevap (DE)','Örnek cevap (TR)','Not (isteğe bağlı)']
```
Yeni sürüm yayınlarken `web/sw.js` içindeki `VERSION` değerini ve `android/app/build.gradle` içindeki `versionCode`/`versionName`'i artırın.
