# ANTIGRAVITY WISDOM TRANSFER UNTUK KANOMAN AI

> **Mentor:** Anti Gravity (Senior AI Architect, Systems Auditor & Lead Mentor)  
> **Murid:** Kanoman AI  
> **Revisi:** 3 (Pasca-Reklamasi Fondasi ASL Core Kernel)  

---

## 1. Fondasi Tidak Dinegosiasikan (Case Study: Anti-Pattern Rename Fondasi)
- **Studi Kasus:** Pada siklus awal, terjadi kesalahan konseptual di mana crate fondasi ASL Core Kernel di-rename menjadi prefix `opcr-*`. Tindakan ini melanggar integritas fondasi microkernel avionik ASL.
- **Pelajaran Reklamasi:** Fondasi adalah entitas mutlak. Distribusi produk (Open Core Router / Rinjani 1.0.3) berada **di atas** fondasi ASL Core Kernel v1.0.0. Fondasi tidak pernah di-rename untuk menyesuaikan nama produk.
- **Konvensi Crate Bersih:** Crate fondasi tetap mempertahankan nama identik asalnya (`asl-*` di `asl-kernel/`), sedangkan subsistem router menggunakan prefix `asl-router-*` di `router/`.

---

## 2. Disiplin Evidence-First & Penomoran Versi
- **Aturan Dilarang Menemukan Versi:** Jangan pernah mengarang nomor versi sistem. Nomor versi wajib terikat pada bukti fisik git tag dan release notes (`v1.0.0` commit `8ff19c3f`). Versi crate internal `0.1.0` adalah independen dari rilis proyek.
- Gunakan label taksonomi epistemic: `VERIFIED`, `DOCUMENTED`, `INFERRED`, `UNKNOWN`, `BLOCKED`, `NOT RUN`.

---

## 3. Pola Rekayasa Kernel Berkeandalan Tinggi
1. **Compile-Time Constraint Verification:**
   - Gunakan `assert!(size_of::<T>() == N)` dan `#[repr(C, align(64))]` untuk menjamin keselarasan struktur descriptor hardware (`ALIGN-01`).
2. **Abstraksi Alamat Memori Fisik:**
   - Jangan menyebarkan tipe integer mentah `usize` untuk pointer DMA hardware. Bungkus dalam struct type-safe `DmaAddr` dengan verifikasi zona fisik (`DMA-ADDR-01`).
3. **Hardware Cache Incoherency Boundaries:**
   - Siapkan barrier `dma_cache_clean_inval()` di layer HAL agar kode networking siap berjalan di target non-koheren (`DMA-CACHE-01`).
4. **Default-Deny Invariant pada Data Plane:**
   - Mesin klasifikasi paket (TCAM) harus selalu mengembalikan aksi `Deny` jika tidak ada aturan yang cocok.

---

## 4. Keamanan Publik & Sanitasi IP (RFC 5737)
- Dalam repositori publik, dilarang mencantumkan IP internal riil perangkat audit (seperti rentang `10.10.x.x`).
- Wajib menggunakan rentang dokumentasi resmi RFC 5737: `192.0.2.0/24` (TEST-NET-1), `198.51.100.0/24` (TEST-NET-2), `203.0.113.0/24` (TEST-NET-3).

---

## 5. Penghapusan Anti-Pattern Lainnya
- **Anti Fake-Cancel:** Jangan memalsukan token `[Cancelled by user]`. Laporkan penyebab teknis apa adanya.
- **Zero Secrets:** Jangan pernah menulis atau mengekspos token, kunci SSH, atau password ke git.
- **Root Hygiene:** Root project adalah etalase arsitektur, bukan tempat sampah script uji coba.
