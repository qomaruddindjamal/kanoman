# RINGKASAN ARSITEKTUR OPEN CORE ROUTER (RINJANI 1.0.3)

> **Untuk:** Kanoman AI Assistant  
> **Dari:** Anti Gravity (Senior AI Architect & Mentor)  
> **Target Project:** `C:\OpenCR`  
> **Fondasi:** ASL Core Kernel v1.0.0 (Immutable)  

---

## 1. Fondasi Arsitektur & Relasi Foundation-Distribusi
Open Core Router (OpenCR) adalah sistem operasi router carrier-grade yang berjalan **DI ATAS** fondasi **ASL Core Kernel v1.0.0** (bare-metal Rust `#![no_std]`).

- **ASL Core Kernel v1.0.0:** Fondasi mutlak (immutable). Tidak boleh di-rename, diubah versinya, atau disandingkan dengan kernel lain.
- **Rinjani 1.0.3:** Codename distribusi produk router.

### Pembagian Crate:
1. **`asl-kernel/`** (Prefix `asl-` — Fondasi Inti):
   - `asl-kernel-core`: Executive & partition table ARINC 653.
   - `asl-hal`: Kontrak CPU & volatile MMIO register.
   - `asl-sched`: Scheduler cyclic/preemptive deterministik.
   - `asl-memory`: Buddy allocator & page slicing statis (ZoneDMA32).
   - `asl-afdx-ipc`: Komunikasi antar-partisi zero-copy SPSC ring buffer.
   - `asl-bootloader`: Boot info validation handshake.
   - `asl-kernel-bin`: Biner integrasi kernel bare-metal.
2. **`router/`** (Prefix `asl-router-` — Modul Produk Router):
   - `asl-router-fastpath`: Descriptor ring bergaya Intel 82599/i40e (ALIGN-01 & DMA-safe).
   - `asl-router-tcam`: IPv4 5-tuple matching engine (default-deny).
   - `asl-router-gpon-ont` & `asl-router-olt-carrier`: Stack akses serat optik GPON/XGS-PON.
   - `asl-router-qos`, `asl-router-switching`, `asl-router-security-vault`, `asl-router-undi-npu`: Akselerasi paket, kriptografi, dan offload coprocessor.

---

## 2. Boot Banner Resmi
```text
[R1] RINJANI 1.0.3 — Open Core Router
[R2] Powered by ASL Core Kernel v1.0.0
```

---

## 3. Aturan Kerja Agen di `C:\OpenCR`
1. Baca `docs/CANONICAL/CANONICAL_MASTER.md` dan `docs/CANONICAL/NAMING_POLICY.md` sebelum menyentuh kode.
2. Root repository wajib bersih (zero clutter). Dilarang membuat file sementara di root.
3. Seluruh commit wajib lolos `cargo test --workspace` dan `cargo check --target x86_64-unknown-none`.
4. Dilarang membocorkan IP internal riil pada dokumentasi publik (gunakan rentang RFC 5737).
