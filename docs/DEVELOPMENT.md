# Kanoman AI — Developer Guide

Panduan pengembangan, pengujian, dan ekstensi untuk tim engineering Kanoman AI.

---

## 1. Prasyarat Lingkungan

- **Python:** 3.12, 3.13, atau 3.14.
- **Git:** Versi 2.40+.
- **Virtualenv (Rekomendasi):**
  ```bash
  python -m venv .venv
  .venv\Scripts\activate   # Windows
  # source .venv/bin/activate # Linux/macOS
  ```

---

## 2. Instalasi & Setup Lokal

Pasang Kanoman dalam mode editable beserta dependensi dev:
```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev,ai,mcp]"
```

Salin template konfigurasi:
```bash
copy .env.example .env
```

---

## 3. Menjalankan Pengujian

Jalankan seluruh test suite secara offline (zero API cost):
```bash
python -m pytest -v
```

Jalankan pengujian modul spesifik:
```bash
python -m pytest tests/test_git_controller.py -v
python -m pytest tests/test_ai_providers.py -v
python -m pytest tests/test_mcp.py -v
```

---

## 4. Penggunaan CLI

Periksa status sistem:
```bash
kanoman status
```

Validasi konfigurasi:
```bash
kanoman config
```

Jalankan task terverifikasi:
```bash
kanoman task run --title "Health Check" --desc "Verify system health" --type ping
```

Periksa repositori Git:
```bash
kanoman git inspect
```

Simulasi commit (dry-run):
```bash
kanoman git dry-run --files README.md pyproject.toml -m "chore: test dry run"
```

---

## 5. Menambahkan Provider AI Baru

1. Buat kelas baru di `src/kanoman/ai/` yang mengimplementasikan `BaseAIProvider` (lihat `src/kanoman/ai/protocol.py`).
2. Sediakan method `generate_text`, `generate_structured`, `health_check`, dan `get_capabilities`.
3. Daftarkan instance provider ke `AIRouter` di `src/kanoman/ai/router.py`.
4. Buat unit test di `tests/test_ai_providers.py`.
