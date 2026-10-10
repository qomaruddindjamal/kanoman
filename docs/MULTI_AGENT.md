# Kanoman AI — Multi-Agent Orchestration & MCP Integration Guide

Dokumentasi komprehensif arsitektur Multi-Agent Orchestrator, antarmuka CLI, eksposur MCP (Model Context Protocol), Quality Gate, batasan keamanan, dan prosedur verifikasi.

---

## 1. Ikhtisar Multi-Agent Architecture

Kanoman AI mengimplementasikan orkestrator multi-agen modular berorientasi keamanan (*security-first*) yang memisahkan tanggung jawab pengembangan perangkat lunak ke dalam persona spesialis:

- **ARCHITECT (`ArchitectRunner`):** Menganalisis kebutuhan tugas, memecah alur menjadi langkah linier terstruktur (`AgentPlan` dan `AgentPlanStep`), serta menentukan kriteria penerimaan (*acceptance criteria*).
- **CODER (`CoderRunner`):** Menghasilkan proposal modifikasi kode secara murni *in-memory* (`CodeProposal`). **Zero Disk Writes:** Runner Coder tidak memiliki hak akses langsung untuk memutasi sistem berkas workspace.
- **SECURITY AUDITOR (`SecurityAuditorRunner`):** Menerima proposal kode beserta hasil audit deterministik dari `AgentQualityGate`. **Hard Veto Invariant:** Jika Quality Gate menemukan pelanggaran keamanan pemblokir (misal: `eval`, `exec`, sintaksis rusak), Security Auditor secara otomatis menerbitkan veto (`REJECT`) tanpa memanggil LLM.
- **QA ENGINEER (`QAEngineerRunner`):** Mengevaluasi keterpenuhan kriteria penerimaan dan memverifikasi strategi pengujian. Jika Security Auditor menolak, QA Engineer langsung melakukan *short-circuit* penolakan.

Seluruh koordinasi dikendalikan oleh `MultiAgentCoordinator` berbasis Finite State Machine (FSM) yang mencegah siklus delegasi (*cycle detection*), membatasi token budget dan iterasi, serta mengamankan riwayat audit ke dalam *recovery checkpoint*.

---

## 2. Antarmuka CLI (Command Line Interface)

Kanoman CLI menyediakan perintah resmi untuk menjalankan dan menginspeksi alur kerja multi-agen.

### A. Format Perintah

```bash
kanoman agent coordinate --title <TITLE> --desc <DESCRIPTION> [OPTIONS]
```

### B. Argumen & Opsi

| Opsi | Tipe | Default | Keterangan |
| :--- | :--- | :--- | :--- |
| `--title` | String | Wajib | Judul tugas (panjang 3–200 karakter). |
| `--desc` | String | Wajib | Deskripsi tugas (panjang 5–4000 karakter). |
| `--priority` | Pilihan | `MEDIUM` | Prioritas tugas: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`. |
| `--provider` | Pilihan | Konfigurasi | Provider AI: `mock`, `gemini`. |
| `--max-iterations` | Integer | `5` | Batas maksimum iterasi koordinasi (1–20). |
| `--token-budget` | Integer | `50000` | Batas anggaran token (100–500.000). |
| `--format` | Pilihan | `text` | Format output terminal: `text` atau `json`. |
| `--no-specialists` | Flag | `False` | Nonaktifkan persona spesialis (gunakan plan dasar). |

### C. Contoh Penggunaan CLI

#### 1. Menjalankan Koordinasi Spesialis (Mode Teks)
```bash
kanoman agent coordinate \
  --title "Implement SHA256 Utility" \
  --desc "Build a secure hashing utility with standard hashlib." \
  --provider mock
```

**Output Contoh:**
```text
=== Kanoman Multi-Agent Coordination Result ===
Task ID:        task_9df37945072a
Status:         COMPLETED
Result Summary: Multi-agent coordination completed successfully: 2 decision(s) recorded.
Checkpoint:     chk_d388b274d158
```

#### 2. Menjalankan Koordinasi dengan Format JSON
```bash
kanoman agent coordinate \
  --title "Implement Token Validator" \
  --desc "Construct robust token validation function." \
  --format json
```

**Output Contoh:**
```json
{
  "task_id": "task_2d4ab1a14945",
  "status": "COMPLETED",
  "result_summary": "Multi-agent coordination completed successfully: 2 decision(s) recorded.",
  "checkpoint_id": "chk_73e2662e3434",
  "is_successful": true,
  "sanitized_error": null
}
```

#### 3. Penanganan Penolakan Keamanan (Exit Code 1)
Jika proposal mengandung kode berbahaya atau melanggar aturan AST:
```bash
kanoman agent coordinate \
  --title "Dynamic Eval Runner" \
  --desc "Run arbitrary code via eval." \
  --format json
```
**Output Contoh:**
```json
{
  "task_id": "task_e117abcfa9a0",
  "status": "FAILED",
  "result_summary": "Execution failed: ValueError: Multi-agent coordination rejected (security veto): Plan rejected by SECURITY_AUDITOR...",
  "checkpoint_id": "chk_1ed7edd029d2",
  "is_successful": false,
  "sanitized_error": "ValueError: Multi-agent coordination rejected (security veto)..."
}
```
*CLI mengembalikan exit code 1.*

---

## 3. Eksposur MCP (Model Context Protocol)

Kanoman MCP Server mengekspos domain tools yang divalidasi secara ketat untuk digunakan oleh AI clients (misalnya Claude Desktop atau agen pendukung).

### A. Daftar MCP Tools

1. **`kanoman_coordinate_agents`**
   - **Deskripsi:** Menjalankan alur koordinasi multi-agen terstruktur lengkap dengan persona spesialis dan verifikasi Quality Gate.
   - **Skema Parameter:**
     - `title` (string, wajib, 3–200 karakter): Judul tugas.
     - `description` (string, wajib, 5–4000 karakter): Rincian tugas.
     - `max_iterations` (integer, opsional, default: 5): Batas iterasi FSM (1–20).
     - `use_specialists` (boolean, opsional, default: true): Mengaktifkan runner spesialis.
     - `provider` (string, opsional, default: "mock"): Provider AI yang digunakan (`mock` atau `gemini`).
   - **Return:** JSON string memuat `task_id`, `status`, `result_summary`, `checkpoint_id`, `is_successful`, dan `error`.

2. **`kanoman_get_agent_decision`**
   - **Deskripsi:** Menginspeksi rekaman keputusan agen, ringkasan perubahan, dan rantai audit dari *recovery checkpoint*.
   - **Skema Parameter:**
     - `checkpoint_id` (string, wajib): ID checkpoint valid (pola `chk_[a-zA-Z0-9_-]+`). Mencegah percobaan *path traversal*.
   - **Return:** JSON string memuat `checkpoint_id`, `task_id`, `status`, `change_summary`, `test_results`, dan `next_steps`.

3. **Baseline Tools yang Tersedia:**
   - `kanoman_status`: Memeriksa status runtime, lingkungan, dan checkpoint terbaru.
   - `kanoman_list_projects`: Menampilkan daftar repositori/proyek yang terdaftar.
   - `kanoman_run_task`: Menjalankan tugas terisolasi standar.
   - `kanoman_git_inspect`: Memeriksa status repositori Git tanpa mutasi.

### B. Konfigurasi MCP Client

Untuk menghubungkan MCP server Kanoman ke client MCP (misalnya Claude Desktop di `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "kanoman": {
      "command": "python",
      "args": ["-m", "kanoman.mcp.server"],
      "env": {
        "KANOMAN_ENV": "development",
        "KANOMAN_DEFAULT_AI_PROVIDER": "mock"
      }
    }
  }
}
```

> **Catatan Verifikasi Koneksi:**
> Mendaftarkan konfigurasi di atas tidak otomatis membuktikan koneksi telah aktif. Untuk memverifikasi:
> 1. Jalankan unit test MCP: `python -m pytest tests/test_mcp.py -v`.
> 2. Uji inisialisasi server lokal: `python -c "from kanoman.mcp.server import create_mcp_server; server = create_mcp_server(); print('MCP OK')"`

---

## 4. Batasan Keamanan & Invarian Arsitektur

1. **Zero Execution Invariant:** Kode yang diusulkan oleh agen **tidak pernah** dieksekusi di runtime Kanoman Core. Analisis dilakukan secara statis melalui AST (`PythonASTAnalyzer`).
2. **Zero Unauthorized Writes:** Runner Coder menghasilkan proposal dalam memori (`CodeProposal`). Tidak ada penulisan berkas langsung ke workspace.
3. **Quality Gate Barrier:** Seluruh proposal wajib melewati `AgentQualityGate`. Pelanggaran aturan keamanan (seperti `PY_EVAL_EXEC`, `PY_SUBPROCESS_SHELL`, `PY_FORBIDDEN_IMPORT`) memicu penolakan seketika.
4. **Git Controller Barrier:** Keputusan persetujuan (`APPROVE`) oleh agen **bukan** otorisasi manusia. Agen dilarang keras memicu `commit` atau `push`. Operasi `request_git_operation('commit')` dan `push` memicu `PermissionError`.
5. **Sanitasi Kredensial:** Seluruh output log, pesan exception, dan metadata checkpoint secara otomatis melewati filter regex `redact_sensitive_text` untuk menghapus token GitHub, API key OpenAI/Gemini, dan password.
6. **Batasan Uji Mock vs Produksi:** Seluruh pengujian otomatis di repository menggunakan `MockAIProvider` deterministik. Pengujian mock membuktikan kebenaran logika FSM, parsing skema, dan batas keamanan sistem, **bukan** kualitas penalaran model LLM produksi pihak ketiga.

---

## 5. Prosedur Pengujian & Troubleshooting

### A. Menjalankan Seluruh Test Suite
```bash
python -m pytest -v
```

### B. Menjalankan Analisis Statis Kode
```bash
python -m kanoman.cli.main analyze python src/kanoman/agents
python -m kanoman.cli.main analyze markdown docs
```

### C. Troubleshooting Umum

- **Issue: Exit code 2 pada CLI `kanoman agent coordinate`**
  - *Penyebab:* Argumen tidak valid (panjang `--title` < 3 atau > 200 karakter, `--desc` < 5 karakter, atau `--max-iterations` di luar rentang 1–20).
  - *Solusi:* Periksa batasan parameter melalui `kanoman agent coordinate --help`.

- **Issue: Status `FAILED` dengan pesan `security veto`**
  - *Penyebab:* Proposal kode mengandung fungsi berbahaya atau gagal lulus `AgentQualityGate`.
  - *Solusi:* Ini adalah perilaku yang diharapkan untuk menjaga keamanan repositori. Periksa detail temuan pemblokir pada log atau output JSON.

- **Issue: `PermissionError` saat operasi Git**
  - *Penyebab:* MultiAgentCoordinator mendeteksi upaya agen untuk melakukan commit atau push otomatis.
  - *Solusi:* Git mutasi memerlukan otorisasi pengguna secara eksplisit melalui alur GitController manusia.
