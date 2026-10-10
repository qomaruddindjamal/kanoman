# Kanoman AI — Research Plan & Technical Investigation

**Tanggal Dokumen:** 2026-10-10  
**Status:** Disetujui untuk Fondasi Kanoman AI Core  
**Tim Peneliti:** AI Systems Architect & Security Engineering Group  

---

## 1. Topik Penelitian Wajib

Dokumen ini mendokumentasikan investigasi teknis mendalam terhadap 12 area kritis sebelum keputusan arsitektural diimplementasikan.

### Topik 1: Arsitektur AI Orchestrator Modular
- **Pertanyaan Penelitian:** Bagaimana merancang orkestrator tugas yang memisahkan logika orkestrasi dari implementasi model AI sehingga core tetap deterministik dan dapat diuji?
- **Sumber Primer:**
  - Martin Fowler: *Patterns of Enterprise Application Architecture* & *Pipes and Filters*.
  - LangChain / LlamaIndex core architecture teardown (Analisis komparatif keterikatan framework).
- **Temuan yang Dapat Diverifikasi:** Keterikatan langsung pada runtime AI monolitik menyebabkan kerapuhan (brittle integration), sulitnya pengujian unit offline, dan rentan terhadap perubahan API vendor. Pendekatan *Clean Architecture / Hexagonal Architecture* (Ports and Adapters) memungkinkan Core berinteraksi dengan AI melalui antarmuka abstrak (`AIProviderProtocol`).
- **Keputusan:** Terapkan Hexagonal Architecture. Core orchestrator mengelola status task dan dispatching, sedangkan AI Provider bertindak sebagai adapter.

### Topik 2: Desain Interface Provider Multi-Model
- **Pertanyaan Penelitian:** Apa kontrak interface minimal yang cukup fleksibel untuk model komersial (Gemini, Claude, OpenAI) maupun lokal tanpa kompleksitas berlebih?
- **Sumber Primer:**
  - PEP 544 (Python Protocols / Structural Subtyping).
  - Google Gemini API REST/SDK Specification (`gemini-2.5/3.0` streaming & structured outputs).
- **Temuan yang Dapat Diverifikasi:** Unified contract memerlukan 4 method fundamental: `generate_text()`, `generate_structured()`, `health_check()`, dan `get_capabilities()`. Format pesan harus dinormalisasi menjadi schema internal (`AIMessage`, `AIResponse`, `UsageMetadata`).
- **Keputusan:** Definisikan `BaseAIProvider` menggunakan `typing.Protocol` dan Pydantic models. Sediakan `MockProvider` sebagai implementasi referensi untuk testing offline.

### Topik 3: Pola Task Management dan Validasi Input
- **Pertanyaan Penelitian:** Bagaimana memvalidasi status transisi task dan mencegah input injection atau eksekusi yang tidak konsisten?
- **Sumber Primer:**
  - Finite State Machine (FSM) Design Pattern.
  - Pydantic v2 Documentation (Strict Types & Field Validation).
- **Temuan yang Dapat Diverifikasi:** Task lifecycle harus mengikuti FSM deterministik (`PENDING` -> `RUNNING` -> `COMPLETED` / `FAILED` / `BLOCKED`). Transisi ilegal (misal: langsung dari `FAILED` ke `COMPLETED` tanpa `RETRYING`) harus diblokir pada tingkat domain model.
- **Keputusan:** Gunakan `Pydantic` v2 dengan enum status eksplisit dan validator transisi state.

### Topik 4: Strategi Konfigurasi dan Manajemen Secret
- **Pertanyaan Penelitian:** Bagaimana mengelola secret tanpa risiko bocor ke file repository, log, atau exception trace?
- **Sumber Primer:**
  - OWASP Secrets Management Cheat Sheet (2025/2026).
  - 12-Factor App: III. Config (Store config in the environment).
  - CWE-798 (Use of Hard-coded Credentials).
- **Temuan yang Dapat Diverifikasi:** Secret tidak boleh didefinisikan dengan nilai default non-kosong. Pydantic `SecretStr` menyamarkan nilai saat dipanggil dengan `str()` atau `repr()`. Logging harus memiliki sanitizer otomatis untuk memotong token berformat sensitif (`gho_*`, `sk-*`, `AIza*`).
- **Keputusan:** `KanomanConfig` berbasis Pydantic `BaseSettings`/`BaseModel` membaca env var. Sediakan `.env.example` tanpa nilai rahasia dan enforce proteksi via `.gitignore`.

### Topik 5: Isolasi Workspace dan Keamanan Operasi Git
- **Pertanyaan Penelitian:** Bagaimana mencegah agen atau orkestrator menjalankan operasi destruktif terhadap repository (`git reset --hard`, force push, salah target remote)?
- **Sumber Primer:**
  - Git Reference Documentation (Safe directory & hooks mechanics).
  - POSIX Subprocess Safety Guidelines (CWE-78 OS Command Injection).
- **Temuan yang Dapat Diverifikasi:** Library wrapper tingkat tinggi (seperti GitPython) kerap memiliki kerentanan command injection pada nama file yang tidak disanitasi. Eksekusi `git` CLI langsung via `subprocess.run(list_of_args, shell=False)` jauh lebih aman, deterministik, dan mudah diaudit.
- **Keputusan:** Bangun `GitController` independen dengan aturan:
  1. `shell=False` selalu digunakan.
  2. Verifikasi root repository, URL remote yang diizinkan, dan branch aktif sebelum eksekusi.
  3. Larangan keras terhadap flag `--force`, `-f`, `reset --hard`.
  4. Mode `dry-run` wajib tersedia.

### Topik 6: Strategi Checkpoint, Recovery, dan Audit Trail
- **Pertanyaan Penelitian:** Bagaimana menyimpan snapshot pekerjaan agar eksekusi dapat dilanjutkan (resumed) tanpa merusak konsistensi data jika terjadi crash?
- **Sumber Primer:**
  - Write-Ahead Logging & Saga Pattern in Distributed Systems.
  - Atomic File Replacement Pattern (Write to temporary file, then `os.replace`).
- **Temuan yang Dapat Diverifikasi:** Checkpoint harus atomic dan immutable per ID checkpoint. Menyimpan seluruh filesystem tidak efisien; simpan state task, diff ringkas, hash git HEAD, dan metadata eksekusi.
- **Keputusan:** Checkpoint disimpan dalam format JSON tervalidasi skema ke direktori `.kanoman_checkpoints/` menggunakan atomic write (`tempfile` + `os.replace`).

### Topik 7: Metode Pengujian Komponen AI Menggunakan Mock
- **Pertanyaan Penelitian:** Bagaimana menguji orkestrator dan logika bisnis tanpa memanggil API pihak ketiga atau mengeluarkan biaya token?
- **Sumber Primer:**
  - Martin Fowler: *Mocks Aren't Stubs*.
  - Pytest Documentation (Fixtures and Parameterization).
- **Temuan yang Dapat Diverifikasi:** Pengujian AI berbasis network eksternal di CI bersifat *flaky*, lambat, dan memboroskan kuota. `MockAIProvider` dengan respons terdefinisi (deterministik, error simulation, latency simulation) memungkinkan 100% coverage alur logika tanpa ketergantungan internet.
- **Keputusan:** Seluruh automated test suite di repo menggunakan `MockAIProvider`. Integrasi API nyata diuji hanya secara opt-in melalui manual integration suite.

### Topik 8: GitHub Actions dan Pembatasan Permission
- **Pertanyaan Penelitian:** Bagaimana menyusun GitHub Actions workflow yang aman dan tahan serangan supply-chain?
- **Sumber Primer:**
  - GitHub Actions Security Hardening Guide (Least Privilege Principle).
  - OpenSSF (Open Source Security Foundation) Scorecard Guidelines.
- **Temuan yang Dapat Diverifikasi:** Workflow default dengan `permissions: write-all` berisiko membocorkan token jika terjadi eksploitasi dependency. Setiap workflow harus secara eksplisit membatasi permission ke `contents: read`.
- **Keputusan:** Workflow CI Kanoman disetel ke `permissions: contents: read`, dependensi dipin, dan job terisolasi.

### Topik 9: Persyaratan Teknis Integrasi MCP (Model Context Protocol)
- **Pertanyaan Penelitian:** Bagaimana mengintegrasikan MCP ke Kanoman Core tanpa membahayakan keamanan host?
- **Sumber Primer:**
  - Anthropic / Model Context Protocol Specification (v1.0 / 2024-2025).
  - SDK Python `mcp` (Model Context Protocol SDK).
- **Temuan yang Dapat Diverifikasi:** Server MCP yang mengekspos raw bash/shell command membuka celah eskalasi hak akses penuh bagi model. Tool yang diekspos harus berupa fungsi domain-spesifik bergranulasi tinggi (`get_task_status`, `list_projects`, `run_kanoman_dryrun`) dengan validasi argumen JSON Schema ketat.
- **Keputusan:** Sediakan adapter MCP opsional yang hanya mengekspos tools terverifikasi dan read-only / dry-run secara default.

### Topik 10: Kelayakan Model Lokal Dibandingkan Provider API
- **Pertanyaan Penelitian:** Apakah model lokal (Ollama / Llama.cpp) layak dijadikan dependensi wajib pada tahap awal?
- **Sumber Primer:**
  - Ollama API Specification & Python SDK.
  - Profil resource VRAM/RAM untuk LLM (7B/8B model memerlukan minimal 8-16 GB RAM).
- **Temuan yang Dapat Diverifikasi:** Menjadikan model lokal sebagai dependensi wajib akan menggagalkan CI (lingkungan GitHub Actions runners gratis hanya memiliki RAM 7GB dan tanpa GPU) serta mempersulit developer dengan mesin terbatas.
- **Keputusan:** Model lokal diperlakukan sebagai provider sekunder/opsional via adapter Ollama, sedangkan MockProvider dan API Provider ringan menjadi jalur utama.

### Topik 11: Pilihan Penyimpanan Metadata untuk Tahap Awal
- **Pertanyaan Penelitian:** Apakah Kanoman membutuhkan PostgreSQL, Vector DB, atau cukup File-based / SQLite?
- **Sumber Primer:**
  - SQLite Documentation (WAL mode & transactional safety).
  - Python Standard Library `json` and `pathlib`.
- **Temuan yang Dapat Diverifikasi:** Database eksternal menambah beban orkestrasi (Docker, credential, network port). Untuk tahap awal (fondasi core dan local orchestrator), file JSON atomic dan SQLite embedded di Python standard library memberikan keandalan ACID tanpa dependensi eksternal.
- **Keputusan:** Gunakan penyimpanan berbasis file JSON terstruktur untuk checkpoint dan in-memory / JSON store untuk Project Registry.

### Topik 12: Strategi Packaging, Instalasi, dan Pengalaman Developer
- **Pertanyaan Penelitian:** Format packaging apa yang sesuai standar Python modern?
- **Sumber Primer:**
  - PEP 517, PEP 518, PEP 621.
  - Python Packaging Authority (PyPA) Guide.
- **Temuan yang Dapat Diverifikasi:** `setup.py` sudah usang (deprecated). Konfigurasi deklaratif dalam `pyproject.toml` dengan backend `setuptools` atau `hatchling` adalah standar industri terkini yang didukung penuh oleh `pip`.
- **Keputusan:** Gunakan `pyproject.toml` dengan layout `src/` standar (`src/kanoman/`). Entry point CLI didaftarkan melalui `[project.scripts]`.

---

## 2. Kesimpulan Riset

Riset di atas menegaskan bahwa:
1. Kanoman AI harus dibangun dengan **arsitektur modular berbasis kontrak/protokol**.
2. **Tidak ada ketergantungan wajib pada API berbayar atau model lokal berat** untuk fungsionalitas inti dan pengujian.
3. **Keamanan Git dan Secret Management** diterapkan secara *fail-closed* di tingkat controller.
