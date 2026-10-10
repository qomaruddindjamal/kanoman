# Kanoman AI

> **Modular, Secure AI Development Orchestrator**

Kanoman AI adalah sistem orkestrasi rekayasa perangkat lunak berbasis kecerdasan buatan (*AI Development Orchestrator*) yang dibangun dengan prinsip deterministik, modularitas berbasis kontrak, isolasi repositori yang ketat, dan keamanan berlapis (*defense-in-depth*).

---

## Fitur Utama

- **Hexagonal Architecture (Ports and Adapters):** Logika bisnis inti terisolasi secara murni dari vendor model AI dan sistem operasi.
- **Git Controller & Repository Isolation:** Pengendalian terpusat terhadap operasi Git dengan larangan mutlak terhadap force push dan `reset --hard`, serta pemindaian secret otomatis sebelum commit.
- **Modular Multi-Provider AI:** Abstraksi provider independen dengan `MockAIProvider` untuk pengujian 100% offline di CI, adapter Google Gemini API ringan, dan adapter model lokal Ollama opsional.
- **Atomic Checkpoint & Recovery Engine:** Penyimpanan snapshot kerja atomik tahan korupsi dengan kemampuan pemulihan (*resumption*) dari kegagalan.
- **Structured Sanitized Logging:** Pembersihan otomatis terhadap API key, PAT token, dan password pada seluruh log output.
- **Model Context Protocol (MCP) Adapter:** Antarmuka adapter terstandarisasi untuk agen AI eksternal dengan pembatasan hak akses yang ketat (tanpa akses raw shell).

---

## Quickstart

### 1. Instalasi
```bash
git clone https://github.com/qomaruddindjamal/kanoman.git
cd kanoman
python -m pip install -e ".[dev,ai,mcp]"
```

### 2. Pengujian (100% Offline)
```bash
python -m pytest -v
```

### 3. Penggunaan CLI
```bash
# Periksa status sistem
kanoman status

# Validasi konfigurasi
kanoman config

# Jalankan task pengujian
kanoman task run --title "System Health" --desc "Verify orchestrator" --type ping

# Periksa status Git aman
kanoman git inspect
```

---

## Dokumentasi Teknis

- [Arsitektur Sistem](docs/ARCHITECTURE.md)
- [Roadmap Eksekusi](docs/ROADMAP.md)
- [Spesifikasi Keamanan](docs/SECURITY.md)
- [Mesin Pemulihan & Checkpoint](docs/RECOVERY.md)
- [Panduan Developer](docs/DEVELOPMENT.md)
- [Template Onboarding Proyek Baru](docs/ONBOARDING.md)
- [Catatan Keputusan Arsitektur (ADR-0001)](docs/decisions/ADR-0001-initial-architecture.md)

---

## Lisensi

Didistribusikan di bawah lisensi MIT.
