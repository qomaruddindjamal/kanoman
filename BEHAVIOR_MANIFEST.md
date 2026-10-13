# BEHAVIOR MANIFEST — KANOMAN AI

Manifesto ini mengikat perilaku otonom Kanoman saat beroperasi di dalam workspace `C:\OpenCR`.

---

## 1. Doktrin Fondasi & Anti Dual-Kernel
1. **ASL Core Kernel adalah Fondasi Mutlak:** Nama "ASL Core Kernel" bersifat immutable. Kanoman dilarang membuat kernel paralel atau mengubah nama fondasi.
2. **Aturan "Dilarang Menemukan Versi":** Prinsip evidence-first berlaku mutlak pada penomoran versi. Versi resmi kernel adalah **v1.0.0** (berdasarkan git tag `v1.0.0` commit `8ff19c3f` & `RELEASE_NOTES.md`). Dilarang mengarang nomor versi lain.
3. **Pemisahan Crate Prefix:** Crate fondasi wajib prefix `asl-` di `asl-kernel/`; crate router wajib prefix `asl-router-` di `router/`.

---

## 2. Siklus Kerja Standar (Standard Operating Procedure)
1. **Preflight Audit:**
   - Jalankan `git status` via GitController.
   - Baca `AGENTS.md`, `GEMINI.md`, dan `docs/CANONICAL/NAMING_POLICY.md` di root OpenCR.
2. **Konteks & Desain:**
   - Baca dokumen `docs/CANONICAL/CANONICAL_MASTER.md`.
   - Pastikan perubahan selaras dengan prinsip `#![no_std]` dan ARINC 653 IMA.
3. **Implementasi & Verifikasi Lokal:**
   - Tulis kode modular dengan type safety ketat.
   - Jalankan `cargo test --workspace` dan catat hasilnya.
   - Jalankan `cargo check --target x86_64-unknown-none`.
4. **Kebersihan & Pelaporan:**
   - Pastikan tidak ada file scratch di root.
   - Jangan menyertakan IP internal riil pada dokumentasi publik (patuhi RFC 5737).
   - Susun laporan handoff dengan taksonomi bukti lengkap.
