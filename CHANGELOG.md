# Changelog

Semua perubahan penting pada proyek Kanoman AI didokumentasikan dalam berkas ini.

Format berkas ini mengacu pada [Keep a Changelog](https://keepachangelog.com/id/1.0.0/),
dan proyek ini mematuhi [Semantic Versioning](https://semver.org/lang/id/).

---

## [0.1.0] - 2026-10-10

### Ditambahkan
- **Initial Audit & R&D:** Audit menyeluruh terhadap lingkungan dan dokumen riset arsitektur (`docs/audit/INITIAL_AUDIT.md`, `docs/research/RESEARCH_PLAN.md`, `docs/research/TECHNOLOGY_EVALUATION.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/decisions/ADR-0001-initial-architecture.md`).
- **Kanoman Core Engine:**
  - Model domain Pydantic v2 untuk `Task`, `Project`, dan `Checkpoint` dengan penegakan transisi status FSM deterministik.
  - Configuration Engine (`KanomanConfig`) dengan proteksi `SecretStr` dan sanitasi nilai rahasia.
  - Project Registry dengan pembatasan root direktori dan pencegahan duplikasi.
  - Task Orchestrator dengan pipeline terstruktur dan registrasi handler.
  - Atomic Recovery Engine untuk penyimpanan dan pemulihan checkpoint tahan korupsi.
  - Structured, sanitized logging system (`KanomanLogger`).
- **Git Controller & Repository Isolation:**
  - Modul terpusat `GitController` menggunakan subprocess langsung (`shell=False`).
  - 4 mode operasi: `inspect`, `dry-run`, `commit`, dan `push`.
  - Verifikasi identitas repositori (root workspace, remote URL, branch kebijakan).
  - Pemindaian regex secret otomatis sebelum commit pada staged diff.
  - Larangan mutlak flag berbahaya (`--force`, `reset --hard`).
- **Modular AI Providers:**
  - Abstraksi antarmuka `BaseAIProvider` Protocol.
  - `MockAIProvider` dengan response synthesizer deterministik untuk pengujian 100% offline.
  - Adapter Google Gemini AI (`GeminiAIProvider`) via REST ringan.
  - Adapter model lokal Ollama (`OllamaAIProvider`) opsional.
  - `AIRouter` dengan penanganan fallback otomatis dan sanitasi token.
- **Antarmuka & Operasional:**
  - Antarmuka CLI `kanoman` (`status`, `config`, `project`, `task`, `checkpoint`, `git`, `test`).
  - Adapter Model Context Protocol (MCP) Server (`src/kanoman/mcp/`) dengan 4 domain tools terisolasi.
  - GitHub Actions CI workflow (`.github/workflows/ci.yml`) dengan `permissions: contents: read`.
  - Dokumentasi operasional dan keamanan lengkap (`README.md`, `AGENTS.md`, `GEMINI.md`, `KanomanAgents.md`, `docs/SECURITY.md`, `docs/RECOVERY.md`, `docs/DEVELOPMENT.md`, `docs/ONBOARDING.md`).
