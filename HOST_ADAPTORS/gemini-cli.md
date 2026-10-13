# HOST ADAPTOR: GEMINI CLI (PRIORITAS HOST NYATA)

> **Host Environment:** Windows PowerShell / Developer Terminal  
> **Target Runtime:** Google Gemini CLI (`gemini`)  
> **Model:** Gemini 1.5 Pro / Flash / 2.0  

---

## 1. Pemasangan & Persyaratan
1. Pasang Gemini CLI atau ekstensi Python google-genai:
   ```powershell
   pip install google-genai
   ```
2. Pastikan API key tersimpan di environment variable aman (bukan di git commit):
   ```powershell
   $env:GEMINI_API_KEY = "your-api-key-here"
   ```

---

## 2. Inisiasi Sesi Kanoman Portabel
Untuk memuat kepribadian dan doktrin Kanoman secara utuh dalam satu perintah:

```powershell
# Jalankan sesi Kanoman dengan prompt sistem mandiri
gemini --system-file "C:\kanoman\BOOT\KANOMAN_SYSTEM_PROMPT.md"
```

Atau menggunakan skrip Python wrapper interaktif:
```powershell
python C:\kanoman\src\kanoman\cli\main.py --system "C:\kanoman\BOOT\KANOMAN_SYSTEM_PROMPT.md"
```
