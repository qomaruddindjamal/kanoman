# Kanoman AI — Technology Evaluation Matrix

**Tanggal:** 2026-10-10  
**Evaluator:** Principal Software Architect & QA Lead  
**Tujuan:** Memilih teknologi inti berbasis bukti, bukan popularitas atau hype.

---

## 1. Evaluasi Komponen Teknologi

### A. Bahasa Pemrograman & Runtime
- **Kandidat:** Python 3.12+ vs Go vs Node.js / TypeScript.
- **Evaluasi 9 Kriteria:**
  1. *Kematangan:* Python memiliki ekosistem AI/ML terlengkap di dunia (Pydantic, MCP, LLM SDKs).
  2. *Keamanan:* Pydantic v2 dan typing ketat mencegah type mismatch; isolasi subprocess aman dengan `shell=False`.
  3. *Modularitas:* Sangat tinggi dengan Python Protocols (`typing.Protocol`) dan duck typing yang teruji.
  4. *Testability:* `pytest` dan `unittest` bawaan sangat cepat, mendukung mock native (`unittest.mock`).
  5. *Portabilitas:* Lintas platform (Windows, Linux, macOS, GitHub Actions).
  6. *Operasional:* Mudah dijalankan langsung tanpa langkah kompilasi rumit saat pengembangan cepat.
  7. *Biaya:* Open source, gratis.
  8. *Pemeliharaan:* Didukung standar PEP 621 deklaratif.
  9. *Kesesuaian:* Sangat ideal untuk AI Development Orchestrator.
- **Keputusan:** **Python 3.12+ (Terverifikasi di workspace: Python 3.14.7)**.

---

### B. Validasi Data & Model Domain
- **Kandidat:** Pydantic v2 vs Standard Library `dataclasses` + `jsonschema`.
- **Evaluasi:**
  - Pydantic v2 menawarkan parsing super cepat berbasis Rust (`pydantic-core`), validasi runtime yang ketat, serialisasi JSON instan, dan `SecretStr` untuk proteksi credential.
  - Sudah terpasang di environment sistem (`pydantic 2.13.5`).
- **Keputusan:** **Pydantic v2**.

---

### C. Git Execution Engine
- **Kandidat:** Direct Subprocess (`subprocess.run`) vs `GitPython` / `pygit2`.
- **Evaluasi:**
  - `GitPython` memiliki riwayat CVE terkait command injection via argumen yang tidak disanitasi, serta sering kali gagal mendeteksi status Git pada Windows secara akurat.
  - `subprocess.run(args, shell=False)` memberikan kendali penuh terhadap setiap flag Git, waktu timeout yang presisi, sanitasi stdin/stdout, dan pencegahan absolut terhadap shell injection.
- **Keputusan:** **Direct Subprocess (`subprocess.run` dengan `shell=False`)**.

---

### D. Provider AI Abstraction Layer
- **Kandidat:** Custom Protocol (`AIProviderProtocol`) vs LangChain Framework vs LiteLLM.
- **Evaluasi:**
  - Framework monolitik seperti LangChain membawa ratusan dependensi transitif yang sering breaking change dan sulit diaudit keamanannya.
  - Custom Protocol tipis (~150 baris kode) memberikan kendali 100%, performa instan, zero external dependency bloat, dan kemudahan mock testing 100% offline.
- **Keputusan:** **Custom Hexagonal AI Provider Protocol**.

---

### E. Penyimpanan State & Checkpoint
- **Kandidat:** Atomic JSON Files vs PostgreSQL / MongoDB vs SQLite.
- **Evaluasi:**
  - PostgreSQL membutuhkan layanan background daemon / docker container yang berat dan tidak portabel untuk CLI lokal/CI.
  - Atomic JSON files (`tempfile.NamedTemporaryFile` + `os.replace`) menyediakan persistensi tahan korupsi, mudah diinspeksi manusia (human-readable), mudah di-diff, dan tidak memerlukan database engine eksternal.
- **Keputusan:** **Atomic JSON Storage** untuk checkpoint dan metadata task.

---

### F. Antarmuka Pengguna & CLI
- **Kandidat:** Standard Library `argparse` / `Click` vs Web UI / FastAPI.
- **Evaluasi:**
  - Sesuai prinsip *Kesesuaian*, Kanoman pada tahap awal membutuhkan interface developer yang presisi, dapat dipanggil dari script, dan mudah diotomatisasi di CI.
  - CLI berbasis modul Python (`argparse` / `click`) memenuhi semua kebutuhan tanpa overhead HTTP port, TLS, atau CORS.
- **Keputusan:** **CLI Native (Python `argparse`)** sebagai antarmuka utama, dengan adapter MCP opsional untuk integrasi agen.

---

## 2. Ringkasan Matriks Keputusan

| Layer | Pilihan Teknologi | Alasan Utama | Risiko & Mitigasi |
|---|---|---|---|
| **Runtime** | Python 3.12+ (3.14 aktif) | Ekosistem AI terstandar, kompatibilitas MCP | Dependensi versi -> Dikunci di `pyproject.toml` |
| **Model & Config** | Pydantic v2 | Strict validation, `SecretStr`, JSON Schema | Perbedaan v1 vs v2 -> Gunakan sintaks v2 murni |
| **Git Engine** | Python `subprocess` (shell=False) | Keamanan CWE-78, zero CVE bloat | Timeout subprocess -> Enforce `timeout=30s` |
| **AI Layer** | Custom Hexagonal Protocol | Modularitas mutlak, tanpa vendor lock-in | Fitur model baru -> Tambahkan via adapter |
| **Storage** | Atomic JSON + File-based | Tanpa daemon, ACID atomic write | Ukuran file -> Hanya simpan metadata ringkas |
| **Testing** | Pytest + Unittest Mock | Cepat, offline, reproducible di CI | Flakiness -> 100% mock untuk test suite inti |
| **CI** | GitHub Actions | Standard CI, minimal permissions | Token leak -> Set `permissions: contents: read` |
