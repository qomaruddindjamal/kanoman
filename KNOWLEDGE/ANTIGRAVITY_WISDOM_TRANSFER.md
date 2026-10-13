# ANTIGRAVITY WISDOM TRANSFER UNTUK KANOMAN AI

> **Mentor:** Anti Gravity (Senior AI Architect, Systems Auditor & Lead Mentor)  
> **Murid:** Kanoman AI  
> **Revisi:** 4 (Sprint Boot Rinjani 1.0.0: Version Lock, Anti-Linux Doctrine & Boot Pipeline)  

---

## 1. Fondasi Tidak Dinegosiasikan & Version Lock
- **Studi Kasus:** Kesalahan konseptual awal mengubah fondasi ASL Core Kernel menjadi `opcr-*` dan ambiguitas versi diselesaikan secara permanen.
- **Pelajaran Reklamasi:** Fondasi **ASL Core Kernel v1.0.0** adalah mutlak (immutable). Produk distribusi **Rinjani 1.0.0** (dikunci owner, menggantikan 1.0.3) berada di atas fondasi tersebut.
- **Konvensi Crate Bersih:** Crate fondasi tetap `asl-*` di `asl-kernel/`; subsistem router ber-prefix `asl-router-*` di `router/`.

---

## 2. Doktrina Mutlak: ASL Core Bukan Linux
- **No Linux Artifacts:** ASL Core adalah bare-metal `#![no_std]` avionik microkernel. Dilarang mengimpor atau berasumsi ketersediaan libc, glibc, musl, systemd, busybox, syscall Linux (epoll, netlink), `/proc`, atau `/sys`.
- **Pure Native Implementation:** Netstack dan driver ditulis native mengejar paritas fungsi carrier, bukan hasil porting Linux. Dilarang meng-copy paste kode GPL/Linux.

---

## 3. Disiplin Evidence-First & Penomoran Versi
- **Aturan Dilarang Menemukan Versi:** Nomor versi wajib terikat pada bukti fisik git tag dan release notes (`v1.0.0` commit `8ff19c3f`). Versi crate internal `0.1.0` adalah independen dari rilis proyek.
- **Disiplin Bukti Hex-Dump ELF:** Setiap klaim executable binary bootable wajib dibuktikan dengan hex-dump 4 byte pertama (`7F 45 4C 46`), bukan sekadar file biner tanpa validasi magic.
- **Pola Isolasi Entrypoint via `#[cfg(target_os = "none")]`:** Untuk mencegah benturan antara binary bare-metal `_start` / panic handler dan harness pengujian host (`cargo test`), seluruh entrypoint bare-metal wajib diisolasi dengan atribut `cfg(target_os = "none")`. Ini memungkinkan 45 unit test host tetap berjalan 100% mulus bersamaan dengan binary ELF bare-metal.
- Gunakan label taksonomi epistemic: `VERIFIED`, `DOCUMENTED`, `INFERRED`, `UNKNOWN`, `BLOCKED`, `NOT RUN`.

---

## 4. Pola Rekayasa Kernel Berkeandalan Tinggi
1. **Compile-Time Constraint Verification:**
   - Gunakan `assert!(size_of::<T>() == N)` dan `#[repr(C, align(64))]` untuk menjamin keselarasan struktur descriptor hardware (`ALIGN-01`).
2. **Abstraksi Alamat Memori Fisik:**
   - Jangan menyebarkan tipe integer mentah `usize` untuk pointer DMA hardware. Bungkus dalam struct type-safe `DmaAddr` dengan verifikasi zona fisik (`DMA-ADDR-01`).
3. **Hardware Cache Incoherency Boundaries:**
   - Siapkan barrier `dma_cache_clean_inval()` di layer HAL agar kode networking siap berjalan di target non-koheren (`DMA-CACHE-01`).
4. **Default-Deny Invariant pada Data Plane:**
   - Mesin klasifikasi paket (TCAM) harus selalu mengembalikan aksi `Deny` jika tidak ada aturan yang cocok.

---

## 5. Keamanan Publik & Sanitasi IP (RFC 5737)
- Dalam repositori publik, dilarang mencantumkan IP internal riil perangkat audit (seperti rentang `10.10.x.x`).
- Wajib menggunakan rentang dokumentasi resmi RFC 5737: `192.0.2.0/24` (TEST-NET-1), `198.51.100.0/24` (TEST-NET-2), `203.0.113.0/24` (TEST-NET-3).

---

## 6. Penghapusan Anti-Pattern Lainnya
- **Anti Fake-Cancel:** Jangan memalsukan token `[Cancelled by user]`. Laporkan penyebab teknis apa adanya.
- **Zero Secrets:** Jangan pernah menulis atau mengekspos token, kunci SSH, atau password ke git.
- **Root Hygiene:** Root project adalah etalase arsitektur, bukan tempat sampah script uji coba. Binary eksternal (seperti Limine) wajib di-git-ignore.
