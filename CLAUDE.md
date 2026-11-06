# Çalışma Kuralları

Aksi belirtilmedikçe bu projede (ve kullanıcının tüm projelerinde) geçerlidir.

0. **Dil:** cevap ve kullanıcı dokümanları Türkçe; kod, tanımlayıcı, yorum, commit İngilizce. Önce cevap, sonra kanıt; hatalar birebir. Verilen kararlar kesin, `project_state.md`'ye yazılır.
1. **Teslimat:** büyük iş = araştırma (`docs/research/`) → `plan.md` → `project_state.md` → tüm fazlar otonom. Faz bitti = typecheck+lint+unit+E2E, 390/1440 px ekran görüntüsü sıfır hata, commit+push, state güncel, görüntüler gönderildi. Sürüm = tam regresyon + CHANGELOG/package.json/tag uyumu.
2. **Yığın:** SvelteKit + Svelte 5 runes + TS strict + Tailwind v4, Drizzle/SQLite, adapter-node, zod, Vitest+Playwright, pino, paraglide; pm2 ve `ecosystem.config.cjs` (.env yok); migration boot'ta; `setup|start|stop|update|backup|restore|doctor|logs` komutları; PWA; admin: sol kenar çubuğu, "Panel".
3. **Mimari:** önce bileşen, tekrar yok; paylaşılan bileşen varken ham `<input>`/`<button>` vb. yasak (dup-check lint'te); şema tabanlı formlar; DataTable/Pagination/FilterBar; yıkıcı işlem yalnız `confirmDialog.ask()`; tek Select; Prettier+ESLint temiz, `any` yok.
4. **URL/ad:** rotalar ve query İngilizce; dosya adları kebab-case, bileşenler PascalCase.
5. **Güvenlik:** sınırda zod, çıktı kaçışı, argon2, HttpOnly/SameSite, CSRF, hız sınırı, 2FA, denetim günlüğü, sırlar şifreli ve loglanmaz, CSP inline'sız, SSRF allowlist, imza sabit zamanlı, upload sniff; sürüm öncesi `npm audit --omit=dev`.
6. **Performans:** JS ≤120 KB gzip (en büyük parça ≤90), Lighthouse ≥90, p95 ≤800 ms; tek SSR load; tek Picture hattı; fontlar self-host; sayfalı ve indeksli listeler; `bumpCache()`.
7. **Veri/ops:** forward-only migration, idempotent seed, gece yedek + `restore --verify`, `/api/health`, bakım modu, döner log, sıfır kesinti update.
8. **Test:** saf mantığa unit, faz başına E2E, görsel taban, axe, PWA güncelleme, install smoke, soak, bütçe; her bug'a regresyon testi; sürümde düzen taraması (her rota: <400, tek h1, yatay kaydırma yok, pageerror yok); rate-limit hijyeni; tam sunucu yeniden başlatma.
9. **Svelte 5:** `$effect` tuzakları (`untrack`, `$derived`), yalnız bilinen `+page.server.ts` export'ları, server modülleri istemciye girmez, her `.svelte` değişikliğinde MCP autofixer.
10. **Bilinen tuzaklar:** sr-only/absolute için `relative` ata, `min-w-0`, `flex-1` + `h-*`, `truncate`, Playwright timeout'ları, sticky `z-10`, `role=status` çakışması, `pattern={'...'}`, CSP ile `<style>`, `/_app/immutable/`, Node stream → `toWebStream()`, zsh `[id]` tırnak.
11. **Git/port:** commit/push kullanıcı adına, AI izi yok (Co-Authored-By vb. trailer eklenmez), İngilizce emir kipi tek satır; meşgul port öldürülmez, boş porta geçilir ve söylenir.
12. **Token:** önce grep, aralık oku, mekanik düzenlemeleri betikle, tek uzun ömürlü ajan, faz başına tam regresyon, notifikasyonlar arasında poll yok, hafıza/plan/state dosyaları gerçek kaynağı.
