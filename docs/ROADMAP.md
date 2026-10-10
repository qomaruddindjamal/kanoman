# Kanoman AI — Roadmap & Execution Plan

**Status:** Aktif  
**Target Delivery:** Fondasi AI Development Orchestrator Siap Produksi  

---

## Rincian Enam Fase Implementasi

### FASE 1: Audit Repository & Technical R&D (Status: COMPLETED)
- [x] Verifikasi kondisi lingkungan fisik, Git, Python 3.14, dan GitHub CLI.
- [x] Inisialisasi Git repository lokal bersih dengan remote `origin` (`qomaruddindjamal/kanoman`).
- [x] Inventaris keadaan aktual dan audit matrix (P0–P3).
- [x] R&D teknis mendalam terhadap 12 area kunci (Clean architecture, Pydantic v2, subprocess safety, MCP, AI mock).
- [x] Matriks evaluasi teknologi 9 kriteria.
- [x] Dokumen arsitektur definitif (`docs/ARCHITECTURE.md`) dan ADR-0001.

### FASE 2: Fondasi Kanoman Core (Status: READY TO EXECUTE)
- [ ] Packaging standar modern `pyproject.toml` dengan build layout `src/`.
- [ ] Model domain Pydantic v2 (`Task`, `Project`, `Checkpoint`) dengan validasi transisi FSM ketat.
- [ ] Configuration Engine dengan Pydantic BaseSettings & `SecretStr`.
- [ ] Project Registry dengan validasi root workspace dan kebijakan Git.
- [ ] Task Orchestrator deterministik dengan logging terstruktur dan tersanitasi.
- [ ] Recovery Engine dengan atomic write JSON snapshot.
- [ ] Unit test komprehensif untuk seluruh komponen Core.

### FASE 3: Git Controller & Repository Isolation (Status: PLANNED)
- [ ] Modul `GitController` terpusat menggunakan subprocess `shell=False`.
- [ ] 4 mode operasi: `inspect`, `dry-run`, `commit`, dan `push`.
- [ ] Repository identity verification (root workspace, remote URL, branch aktif).
- [ ] Secret scanning pra-commit dan diff verification.
- [ ] Larangan keras flag berbahaya (`--force`, `reset --hard`).
- [ ] Test suite isolasi repository menggunakan repository temporary lokal.

### FASE 4: Integrasi AI Modular (Status: PLANNED)
- [ ] Kontrak antarmuka `AIProviderProtocol`.
- [ ] `MockAIProvider` dengan response synthesizer deterministik untuk unit & CI tests.
- [ ] `GeminiProvider` (REST/SDK) untuk model Google Gemini.
- [ ] `OllamaProvider` (opsional, decoupled) untuk model lokal.
- [ ] Router provider dengan penanganan timeout, rate limit, dan fallback transparan.
- [ ] Fixture dan skenario pengujian kualitas model AI.

### FASE 5: Operasional, CLI, Security, dan CI (Status: PLANNED)
- [ ] Antarmuka CLI interaktif (`kanoman status`, `kanoman task`, `kanoman project`, dll.).
- [ ] Adapter MCP opsional (`src/kanoman/mcp/`) dengan tool schema aman.
- [ ] GitHub Actions CI workflow (`.github/workflows/ci.yml`) dengan `permissions: contents: read`.
- [ ] Security review mendalam dan dokumen operasional lengkap (`README.md`, `docs/SECURITY.md`, `docs/RECOVERY.md`, `docs/DEVELOPMENT.md`).

### FASE 6: Validasi End-to-End & Kesiapan Ekspansi (Status: PLANNED)
- [ ] E2E integration test mencakup seluruh siklus (load config -> task -> mock AI -> checkpoint -> git inspect).
- [ ] Failure recovery & edge-case stress test.
- [ ] Template onboarding proyek baru (`docs/ONBOARDING.md`).
- [ ] Final security scan & diff review.
- [ ] Commit dan push terverifikasi ke remote repository Kanoman (`qomaruddindjamal/kanoman`).
- [ ] Final readiness report.

---

## Kriteria Penerimaan Tiap Fase

Setiap fase wajib diverifikasi dengan perintah nyata dan unit test sebelum fase berikutnya dijalankan. Keputusan fase dilaporkan secara transparan (`PASS`, `PASS WITH EXCEPTIONS`, `BLOCKED`, `FAIL`).
