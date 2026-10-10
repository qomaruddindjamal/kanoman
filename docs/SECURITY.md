# Kanoman AI — Security Architecture & Threat Model

**Versi:** 1.0.0  
**Tanggal:** 2026-10-10  
**Klasifikasi:** Internal Security Specification & Guidelines  

---

## 1. Prinsip Keamanan Utama

1. **Defense in Depth (Pertahanan Berlapis):** Setiap input divalidasi pada batas terluar (CLI, MCP, API) dan di tingkat domain model (Pydantic).
2. **Least Privilege (Hak Akses Minimum):** Operasi Git default dalam mode `dry-run`. GitHub Actions disetel secara ketat ke `permissions: contents: read`.
3. **Fail-Closed Security:** Kegagalan verifikasi identitas repositori atau terdeteksinya token rahasia membatalkan seluruh operasi secara instan.
4. **Zero Untrusted Execution:** Tidak ada eksekusi shell dinamis (`shell=False` pada seluruh pemanggilan `subprocess`).

---

## 2. Mitigasi Ancaman Spesifik

### A. OS Command Injection (CWE-78)
- **Vektor Serangan:** Agen atau pengguna menyisipkan karakter pemisah perintah shell (`;`, `&&`, `|`) ke dalam argumen Git atau nama file.
- **Mitigasi:** `GitController` menggunakan `subprocess.run(list_of_args, shell=False)` secara absolut. Tidak ada string concatenation ke shell prompt.

### B. Hardcoded & Leaked Credentials (CWE-798 / OWASP A07)
- **Vektor Serangan:** API key (`AIza...`, `sk-...`) atau GitHub PAT (`gho_...`) tertulis ke file konfigurasi atau tercetak di log output / commit diff.
- **Mitigasi:**
  - `Pydantic.SecretStr` mengaburkan token dari `repr()` dan serialisasi biasa.
  - `KanomanLogger` menjalankan regex redaction otomatis terhadap semua stream logging.
  - `GitController` memindai baris tambahan (`+`) pada staged diff sebelum commit dibuat; jika pola rahasia ditemukan, staging dibatalkan secara otomatis (`git reset HEAD`).
  - `.gitignore` secara agresif mengecualikan `.env*`, `*.pem`, `*.key`, `*.token`.

### C. Path Traversal & Unauthorized Workspace Access (CWE-22)
- **Vektor Serangan:** Manipulasi workspace root dengan `../` atau mendaftarkan direktori sistem OS (`C:\`, `C:\Windows`).
- **Mitigasi:** `ProjectRegistry` dan `KanomanConfig` menormalisasi path dengan `.resolve()` dan menolak direktori root OS atau path di luar workspace yang diizinkan.

### D. Untrusted AI Prompt Output & Injection
- **Vektor Serangan:** Output teks model AI mencoba mengeksekusi instruksi arbitrer atau memicu self-modification pada codebase.
- **Mitigasi:** Output model diperlakukan murni sebagai data, bukan instruksi yang langsung dieksekusi. Tidak ada fungsi `eval()` atau `exec()` dalam codebase Kanoman.

---

## 3. Matriks Tanggung Jawab Keamanan Komponen

| Komponen | Proteksi yang Ditegakkan |
|---|---|
| `GitController` | Melarang `--force`, `reset --hard`, mengunci remote URL dan branch |
| `ConfigEngine` | Secret masking, validasi remote URL, validasi tipe nilai |
| `ProjectRegistry` | Menolak root direktori OS dan registrasi ganda |
| `RecoveryEngine` | Penulisan atomik tahan korupsi, validasi integritas skema |
| `MCPServer` | Hanya mengekspos tools terverifikasi, zero direct bash/shell tools |
