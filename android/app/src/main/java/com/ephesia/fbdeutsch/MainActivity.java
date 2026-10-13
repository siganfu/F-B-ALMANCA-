package com.ephesia.fbdeutsch;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Locale;
import java.util.Set;

/**
 * F&B Deutsch Akademie — WebView kabuğu.
 *
 * Web uygulaması (assets/index.html) WebView içinde çevrimdışı çalışır.
 * Android WebView, Web Speech API'nin konuşma tanıma kısmını desteklemediği ve
 * speechSynthesis desteği cihaza göre değiştiği için, ses özellikleri yerel
 * Android servislerine "FBNative" JavaScript köprüsüyle bağlanır:
 *   - TextToSpeech (Almanca, de-DE)
 *   - SpeechRecognizer (Almanca konuşma tanıma)
 */
public class MainActivity extends Activity implements TextToSpeech.OnInitListener {

    private static final String START_URL = "file:///android_asset/index.html";
    private static final int REQ_MIC = 4201;

    private WebView web;
    private TextToSpeech tts;
    private volatile String ttsStatus = "init";   // init | ready | missing | error
    private SpeechRecognizer recognizer;
    private boolean listenPending = false;
    private String listenLang = "de-DE";

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#0F1F3D"));
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);

        // Android 15+ uçtan uca çizim: içerik durum/gezinme çubuklarının altına girmesin
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            int top, bottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets i = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
                top = i.top; bottom = i.bottom;
            } else {
                top = insets.getSystemWindowInsetTop(); bottom = insets.getSystemWindowInsetBottom();
            }
            v.setPadding(0, top, 0, bottom);
            return insets;
        });

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);           // localStorage: personel ilerlemesi
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(true);
        s.setTextZoom(100);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);

        web.addJavascriptInterface(new Bridge(), "FBNative");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                if ("file".equals(u.getScheme())) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (ActivityNotFoundException ignored) {}
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                runOnUiThread(() -> request.grant(request.getResources()));
            }
        });

        if (savedInstanceState != null) web.restoreState(savedInstanceState);
        else web.loadUrl(START_URL);

        tts = new TextToSpeech(this, this);
    }

    /* ------------------------- TextToSpeech ------------------------- */

    @Override
    public void onInit(int status) {
        if (status != TextToSpeech.SUCCESS) { ttsStatus = "error"; notifyTtsStatus(); return; }
        int r = tts.setLanguage(Locale.GERMANY);
        if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) {
            ttsStatus = "missing";
        } else {
            ttsStatus = "ready";
            pickBestGermanVoice();
        }
        tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
            @Override public void onStart(String id) { js("window.__fbNative.onTtsStart(" + JSONObject.quote(id) + ")"); }
            @Override public void onDone(String id) { js("window.__fbNative.onTtsDone(" + JSONObject.quote(id) + ")"); }
            @Override public void onStop(String id, boolean interrupted) { js("window.__fbNative.onTtsDone(" + JSONObject.quote(id) + ")"); }
            @Override @Deprecated public void onError(String id) { js("window.__fbNative.onTtsError(" + JSONObject.quote(id) + ",'tts')"); }
            @Override public void onError(String id, int code) { js("window.__fbNative.onTtsError(" + JSONObject.quote(id) + "," + JSONObject.quote("kod " + code) + ")"); }
        });
        notifyTtsStatus();
    }

    /** Yüklü Almanca sesler içinden en kaliteli ve internet gerektirmeyeni seçer. */
    private void pickBestGermanVoice() {
        try {
            Set<Voice> voices = tts.getVoices();
            if (voices == null) return;
            Voice best = null; int bestScore = -1;
            for (Voice v : voices) {
                Locale l = v.getLocale();
                if (l == null || !"de".equals(l.getLanguage())) continue;
                Set<String> f = v.getFeatures();
                if (f != null && f.contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED)) continue;
                int score = v.getQuality();
                if ("DE".equals(l.getCountry())) score += 1000;
                if (!v.isNetworkConnectionRequired()) score += 200;
                if (score > bestScore) { bestScore = score; best = v; }
            }
            if (best != null) tts.setVoice(best);
        } catch (Exception ignored) {}
    }

    private void notifyTtsStatus() {
        js("window.__fbNative.onTtsStatus && window.__fbNative.onTtsStatus(" + JSONObject.quote(ttsStatus) + ")");
    }

    /* ------------------------- Konuşma tanıma ------------------------- */

    private void startListeningInternal() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            js("window.__fbNative.onSttError(5,'Konuşma tanıma servisi bulunamadı')");
            return;
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            listenPending = true;
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
            return;
        }
        if (tts != null) tts.stop();
        if (recognizer != null) { recognizer.destroy(); recognizer = null; }
        recognizer = SpeechRecognizer.createSpeechRecognizer(this);
        recognizer.setRecognitionListener(new RecognitionListener() {
            @Override public void onReadyForSpeech(Bundle params) { js("window.__fbNative.onSttState('listening')"); }
            @Override public void onBeginningOfSpeech() {}
            @Override public void onRmsChanged(float rmsdB) {}
            @Override public void onBufferReceived(byte[] buffer) {}
            @Override public void onEndOfSpeech() { js("window.__fbNative.onSttState('processing')"); }
            @Override public void onError(int error) { js("window.__fbNative.onSttError(" + error + ",'')"); }
            @Override public void onResults(Bundle results) {
                ArrayList<String> list = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                JSONArray arr = new JSONArray();
                if (list != null) for (String t : list) arr.put(t);
                if (arr.length() == 0) js("window.__fbNative.onSttError(7,'')");
                else js("window.__fbNative.onSttResult(" + arr.toString() + ")");
            }
            @Override public void onPartialResults(Bundle partialResults) {}
            @Override public void onEvent(int eventType, Bundle params) {}
        });
        Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, listenLang);
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, listenLang);
        i.putExtra("android.speech.extra.EXTRA_ADDITIONAL_LANGUAGES", new String[]{listenLang});
        i.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3);
        i.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false);
        i.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, getPackageName());
        recognizer.startListening(i);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQ_MIC) return;
        boolean granted = grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED;
        if (granted && listenPending) startListeningInternal();
        else js("window.__fbNative.onSttError(-1,'')");
        listenPending = false;
    }

    /* ------------------------- JavaScript köprüsü ------------------------- */

    private class Bridge {
        @JavascriptInterface
        public boolean speak(String id, String text, float rate) {
            if (tts == null || !"ready".equals(ttsStatus)) return false;
            tts.setSpeechRate(Math.max(0.3f, Math.min(rate, 1.5f)));
            Bundle p = new Bundle();
            p.putString(TextToSpeech.Engine.KEY_PARAM_UTTERANCE_ID, id);
            return tts.speak(text, TextToSpeech.QUEUE_FLUSH, p, id) == TextToSpeech.SUCCESS;
        }

        @JavascriptInterface
        public void stop() { if (tts != null) tts.stop(); }

        @JavascriptInterface
        public String ttsStatus() { return ttsStatus; }

        @JavascriptInterface
        public boolean sttAvailable() { return SpeechRecognizer.isRecognitionAvailable(MainActivity.this); }

        @JavascriptInterface
        public void startListening(String lang) {
            listenLang = (lang == null || lang.isEmpty()) ? "de-DE" : lang;
            runOnUiThread(MainActivity.this::startListeningInternal);
        }

        @JavascriptInterface
        public void stopListening() {
            runOnUiThread(() -> { if (recognizer != null) recognizer.stopListening(); });
        }

        @JavascriptInterface
        public void installTtsData() {
            runOnUiThread(() -> {
                try { startActivity(new Intent(TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA)); }
                catch (ActivityNotFoundException e) { openTtsSettingsInternal(); }
            });
        }

        @JavascriptInterface
        public void openTtsSettings() { runOnUiThread(MainActivity.this::openTtsSettingsInternal); }

        @JavascriptInterface
        public String appVersion() { return BuildConfig.VERSION_NAME; }
    }

    private void openTtsSettingsInternal() {
        try { startActivity(new Intent("com.android.settings.TTS_SETTINGS")); }
        catch (ActivityNotFoundException e) {
            Toast.makeText(this, "Ayarlar > Erişilebilirlik > Metin okuma bölümünden Almanca sesi yükleyin.", Toast.LENGTH_LONG).show();
        }
    }

    /* ------------------------- Yardımcılar ------------------------- */

    private void js(final String code) {
        if (web == null) return;
        web.post(() -> web.evaluateJavascript("try{" + code + "}catch(e){}", null));
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Kullanıcı ses paketini yükleyip geri döndüyse dili tekrar dene
        if (tts != null && !"ready".equals(ttsStatus) && !"init".equals(ttsStatus)) {
            int r = tts.setLanguage(Locale.GERMANY);
            if (r != TextToSpeech.LANG_MISSING_DATA && r != TextToSpeech.LANG_NOT_SUPPORTED) {
                ttsStatus = "ready"; pickBestGermanVoice(); notifyTtsStatus();
            }
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (tts != null) tts.stop();
        if (recognizer != null) recognizer.cancel();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        web.saveState(outState);
    }

    @SuppressWarnings("deprecation")
    @Override
    public void onBackPressed() {
        web.evaluateJavascript("(window.__fbNative && window.__fbNative.onBack) ? window.__fbNative.onBack() : false", value -> {
            if (!"true".equals(value)) MainActivity.super.onBackPressed();
        });
    }

    @Override
    protected void onDestroy() {
        if (tts != null) { tts.stop(); tts.shutdown(); }
        if (recognizer != null) recognizer.destroy();
        if (web != null) { web.removeJavascriptInterface("FBNative"); web.destroy(); }
        super.onDestroy();
    }
}
