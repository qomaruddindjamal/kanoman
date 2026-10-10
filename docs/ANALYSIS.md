# Kanoman AI — Automated Static Analysis & Document Validation

Dokumen ini menjelaskan arsitektur, katalog aturan, dan penggunaan mesin analisis statis otomatis yang dibangun pada Tahap 8 Kanoman AI.

---

## 1. Arsitektur dan Prinsip Keamanan

Sistem analisis statis Kanoman dirancang dengan prinsip keselamatan tinggi:
1. **Zero Code Execution:** Analisis kode Python dilakukan murni melalui Abstract Syntax Tree (AST) menggunakan standard library `ast.parse`. Target kode tidak pernah di-import, di-eval, atau dieksekusi.
2. **Zero Third-Party AST Bloat:** Mengandalkan standard library Python (`ast`, `re`, `pathlib`) tanpa dependensi parser pihak ketiga yang berat.
3. **Workspace Path Containment:** Semua jalur target divalidasi terhadap `workspace_root` untuk mencegah serangan path traversal (`../`).
4. **Deterministic Structured Reporting:** Hasil analisis dikemas dalam model Pydantic (`Finding`, `AnalysisReport`) dengan level keparahan (`INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) dan format output teks atau JSON terstruktur.

---

## 2. Python AST Analyzer (`kanoman.analysis.python_analyzer`)

### Katalog Aturan Python

| Rule ID | Severity | Deskripsi | Rekomendasi Perbaikan |
|---|---|---|---|
| `PY_SYNTAX_ERROR` | `HIGH` | File sumber memiliki kesalahan sintaksis Python sehingga tidak dapat di-parse. | Perbaiki sintaksis kode sesuai spesifikasi bahasa Python. |
| `PY_EVAL_EXEC` | `HIGH` | Pemanggilan `eval()` atau `exec()` membuka risiko eksekusi kode dinamis tak terpercaya. | Ganti dengan tabel dispatch aman atau `ast.literal_eval`. |
| `PY_SUBPROCESS_SHELL` | `HIGH` | Eksekusi subprocess dengan `shell=True` rentan terhadap OS Command Injection (CWE-78). | Berikan argumen perintah sebagai list of strings dengan `shell=False`. |
| `PY_INSECURE_PICKLE` | `MEDIUM` | Deserialisasi data tidak aman via `pickle.load()` / `pickle.loads()` (CWE-502). | Gunakan format serialisasi aman seperti JSON atau Pydantic models. |
| `PY_HARDCODED_SECRET` | `HIGH` | Penugasan variabel credential/token/key dengan string bernilai statis sensitif. | Pindahkan secret ke environment variables atau vault rahasia. |
| `PY_FILE_READ_ERROR` | `MEDIUM` | File tidak ditemukan atau terjadi kesalahan decoding/I/O saat pembacaan file. | Pastikan file ada, memiliki permission baca, dan berenkoding UTF-8. |

---

## 3. Markdown Validator (`kanoman.analysis.markdown_validator`)

### Katalog Aturan Markdown

| Rule ID | Severity | Deskripsi | Rekomendasi Perbaikan |
|---|---|---|---|
| `MD_EMPTY_FILE` | `LOW` | File dokumentasi Markdown kosong atau hanya berisi whitespace. | Lengkapi isi dokumentasi atau hapus file kosong tersebut. |
| `MD_EMPTY_HEADING` | `LOW` | Marker heading (`#`) ditemukan tanpa teks judul. | Berikan teks judul deskriptif atau hapus marker heading kosong. |
| `MD_UNCLOSED_FENCE` | `MEDIUM` | Blok kode (` ``` ` atau `~~~`) dibuka tetapi tidak pernah ditutup sampai akhir file. | Tutup blok kode dengan tanda fence yang sesuai. |
| `MD_BROKEN_LINK` | `MEDIUM` | Format link rusak atau target link kosong `[text]()`. | Lengkapi URL atau path tujuan link yang valid. |
| `MD_MALFORMED_CHECKLIST` | `LOW` | Format checkbox checklist tidak standar (misal `- [?]` atau `-[x]`). | Gunakan format `- [ ]` atau `- [x]`. |
| `MD_MISSING_LOCAL_REF` | `MEDIUM` | Link relatif mengarah ke file lokal yang tidak ditemukan di disk. | Verifikasi dan perbaiki jalur file tujuan relatif. |
| `MD_FILE_READ_ERROR` | `MEDIUM` | Gagal membaca file Markdown akibat masalah I/O atau encoding. | Pastikan file ada dan berenkoding UTF-8 valid. |

---

## 4. Antarmuka CLI

Analisis statis dapat dipanggil langsung melalui CLI `kanoman`:

### Analisis Python
```bash
# Analisis seluruh direktori sumber
kanoman analyze python src

# Analisis satu file tertentu dengan output JSON
kanoman analyze python src/kanoman/core/models.py --format json

# Tentukan workspace root khusus
kanoman analyze python . --root C:\kanoman
```

### Validasi Markdown
```bash
# Validasi dokumentasi
kanoman analyze markdown docs

# Validasi file tunggal
kanoman analyze markdown README.md --format json
```

---

## 5. Integrasi Task Orchestrator

Dua handler bawaan telah terdaftar di `TaskOrchestrator`:
- `analyze_python`: Menjalankan pemeriksaan Python AST pada target dan menyimpan ringkasan temuan ke checkpoint.
- `validate_markdown`: Menjalankan validasi struktur Markdown pada target dokumentasi dan membuat checkpoint hasil verifikasi.

Contoh eksekusi melalui API:
```python
from kanoman.core.models import Task, TaskPriority
from kanoman.core.orchestrator import TaskOrchestrator

orchestrator = TaskOrchestrator()
task = Task(
    title="Pemeriksaan Statis Kode",
    description="Scan codebase dengan Python AST Analyzer",
    priority=TaskPriority.HIGH,
    metadata={"target_path": "src"},
)
result = orchestrator.execute_task(task, task_type="analyze_python")
print(result.status)  # COMPLETED
```
