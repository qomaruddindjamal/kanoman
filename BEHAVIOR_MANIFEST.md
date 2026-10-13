# BEHAVIOR MANIFEST — KANOMAN AI

Manifesto ini mengikat perilaku otonom Kanoman saat beroperasi di dalam workspace `C:\OpenCR`.

---

## 1. Siklus Kerja Standar (Standard Operating Procedure)
1. **Preflight Audit:**
   - Jalankan `git status` via GitController.
   - Baca `AGENTS.md` dan `GEMINI.md` di root OpenCR.
2. **Konteks & Desain:**
   - Baca dokumen `docs/CANONICAL/CANONICAL_MASTER.md`.
   - Pastikan perubahan selaras dengan prinsip `#![no_std]` dan ARINC 653 IMA.
3. **Implementasi & Verifikasi Lokal:**
   - Tulis kode modular dengan type safety ketat.
   - Jalankan `cargo test --workspace` dan catat hasilnya.
   - Jalankan `cargo check --target x86_64-unknown-none`.
4. **Kebersihan & Pelaporan:**
   - Pastikan tidak ada file scratch di root.
   - Susun laporan handoff dengan taksonomi bukti lengkap.

---

## 2. Contoh Alur Kerja End-to-End (Sample Task)
- **Tugas:** Menambahkan validasi kapasitas pada queue SPSC `opcr-afdx-ipc`.
- **Langkah 1:** Buka `opcr-kernel/opcr-afdx-ipc/src/lib.rs`.
- **Langkah 2:** Tambahkan unit test baru `test_spsc_ring_buffer_full()`.
- **Langkah 3:** Jalankan `cargo test -p opcr-afdx-ipc`.
- **Langkah 4:** Verifikasi 2 tests lulus (exit code 0).
- **Langkah 5:** Commit dengan pesan `test(afdx-ipc): add ring buffer boundary saturation test`.
