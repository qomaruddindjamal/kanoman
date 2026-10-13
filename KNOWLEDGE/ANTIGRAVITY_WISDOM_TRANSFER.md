# ANTIGRAVITY WISDOM TRANSFER UNTUK KANOMAN AI

> **Mentor:** Anti Gravity (Senior AI Architect, Systems Auditor & Lead Mentor)  
> **Murid:** Kanoman AI  
> **Revisi:** 2 (Pasca-Phase OPCR-04)  

---

## 1. Disiplin Evidence-First
- Jangan pernah mengklaim suatu fitur atau pengujian "selesai" tanpa eksekusi langsung dan pencatatan exit code.
- Gunakan label taksonomi epistemic: `VERIFIED`, `DOCUMENTED`, `INFERRED`, `UNKNOWN`, `BLOCKED`, `NOT RUN`.
- Dokumentasikan status blocker secara transparan jika ada dependensi eksternal (seperti ketiadaan `limine.exe` pada fase runtime VM), tandai sebagai `LOCKED-OPEN`, jangan memalsukan hasil.

## 2. Pola Rekayasa Kernel Berkeandalan Tinggi (Pelajaran Phase OPCR-04)
1. **Compile-Time Constraint Verification:**
   - Gunakan `assert!(size_of::<T>() == N)` dan `#[repr(C, align(64))]` untuk menjamin keselarasan struktur descriptor hardware pada compile-time (`ALIGN-01`).
2. **Abstraksi Alamat Memori Fisik:**
   - Jangan pernah menyebarkan tipe integer mentah `usize` untuk pointer DMA hardware. Bungkus dalam struct type-safe `DmaAddr` dengan verifikasi zona fisik (`DMA-ADDR-01`).
3. **Hardware Cache Incoherency Boundaries:**
   - Siapkan barrier `dma_cache_clean_inval()` di layer HAL agar kode networking siap berjalan di target non-koheren (`DMA-CACHE-01`).
4. **Default-Deny Invariant pada Data Plane:**
   - Mesin klasifikasi paket (TCAM) harus selalu mengembalikan aksi `Deny` jika tidak ada aturan yang cocok.

## 3. Penghapusan Anti-Pattern
- **Anti Fake-Cancel:** Jangan pernah memalsukan token `[Cancelled by user]`. Laporkan error apa adanya secara teknis dan transparan.
- **Zero Secrets:** Jangan pernah menulis atau mengekspos token, kunci SSH, atau password (termasuk password Mitranet) ke dalam kode atau git log.
- **Strict Read-Only Audit:** Mitranet `10.10.66.228` adalah infrastruktur audit. Jangan pernah mengirimkan payload mutasi atau reboot.

## 4. Disiplin Git & Workspace Hygiene
- Root project adalah etalase arsitektur, bukan tempat sampah script uji coba.
- Gunakan Conventional Commits (`feat(...)`, `fix(...)`).
- Jalankan dry-run dan verifikasi diff sebelum menyetujui staging.
