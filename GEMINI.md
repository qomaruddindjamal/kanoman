# Kanoman AI — Gemini Integration & Assistant Context

Dokumen ini memuat panduan integrasi model Google Gemini ke dalam arsitektur Kanoman AI.

---

## 1. Provider Adapter

Adapter Google Gemini diimplementasikan dalam modul:
`src/kanoman/ai/gemini.py` (`GeminiAIProvider`)

Fitur utama:
- Mendukung pemanggilan REST ringan menggunakan standard library `urllib` tanpa dependensi SDK monolitik.
- Mendukung model `gemini-2.5-flash` sebagai model default berlatensi rendah dan efisien biaya.
- Penanganan error HTTP otomatis:
  - 401/403: `AIErrorType.AUTHENTICATION_ERROR`
  - 429: `AIErrorType.RATE_LIMIT_ERROR`
  - 500/503: `AIErrorType.SERVICE_UNAVAILABLE`
- Sanitasi token API: API key ditampung secara eksklusif menggunakan Pydantic `SecretStr`.

---

## 2. Konfigurasi Variabel Lingkungan

Untuk mengaktifkan inferensi Gemini secara langsung:
```bash
# Tambahkan ke file .env lokal (jangan pernah di-commit ke Git):
GEMINI_API_KEY=AIzaSy...
KANOMAN_DEFAULT_AI_PROVIDER=gemini
```

Untuk pengujian otomatis di CI atau pengembangan lokal tanpa kuota API:
Gunakan provider `mock`:
```bash
KANOMAN_DEFAULT_AI_PROVIDER=mock
```
