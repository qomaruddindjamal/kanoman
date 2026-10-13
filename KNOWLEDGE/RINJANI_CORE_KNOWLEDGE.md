# RINGKASAN ARSITEKTUR OPEN CORE ROUTER (RINJANI 1.0.0)

> **Untuk:** Kanoman AI Assistant  
> **Dari:** Anti Gravity (Senior AI Architect & Mentor)  
> **Target Project:** `C:\OpenCR`  
> **Fondasi:** ASL Core Kernel v1.0.0 (Immutable)  
> **Distro:** Rinjani 1.0.0 (Owner Locked Directive)  

---

## 1. Fondasi Arsitektur & Relasi Foundation-Distribusi
Open Core Router (OpenCR) adalah sistem operasi router carrier-grade yang berjalan **DI ATAS** fondasi **ASL Core Kernel v1.0.0** (bare-metal Rust `#![no_std]`).

- **ASL Core Kernel v1.0.0:** Fondasi mutlak (immutable). Tidak boleh di-rename, diubah versinya, atau disandingkan dengan kernel lain.
- **Rinjani 1.0.0:** Codename distribusi produk router (terkunci menggantikan 1.0.3 yang telah dipensiunkan).

### Pembagian Crate:
1. **`asl-kernel/`** (Prefix `asl-` — Fondasi Inti):
   - `asl-kernel-core`: Executive & partition table ARINC 653.
   - `asl-hal`: Kontrak CPU & volatile MMIO register.
   - `asl-sched`: Scheduler cyclic/preemptive deterministik.
   - `asl-memory`: Buddy allocator & page slicing statis (ZoneDMA32).
   - `asl-afdx-ipc`: Komunikasi antar-partisi zero-copy SPSC ring buffer.
   - `asl-bootloader`: Boot info validation handshake.
   - `asl-kernel-bin`: Biner integrasi kernel bare-metal (output ELF higher-half).
2. **`router/`** (Prefix `asl-router-` — Modul Produk Router):
   - `asl-router-fastpath`: Descriptor ring bergaya Intel 82599/i40e (ALIGN-01 & DMA-safe).
   - `asl-router-tcam`: IPv4 5-tuple matching engine (default-deny).
   - `asl-router-gpon-ont` & `asl-router-olt-carrier`: Stack akses serat optik GPON/XGS-PON.
   - `asl-router-qos`, `asl-router-switching`, `asl-router-security-vault`, `asl-router-undi-npu`: Akselerasi paket, kriptografi, dan offload coprocessor.
   - `asl-router-pci`: Enumerasi bus PCI (config space 0xCF8/0xCFC, BAR decoding).
   - `asl-router-drivers-virtio`: Driver native VirtIO-Net (Virtqueue split ring) & fallback Intel 82540EM (e1000).
   - `asl-router-netbuf`: Pool buffer paket statis zero-allocation (power-of-two, double-free guard).
   - `asl-router-netstack`: Native carrier protocol stack (Ethernet II, RFC 826 ARP, IPv4, ICMP Echo, UDP).

---

## 2. Boot Banner Resmi
```text
[R1] RINJANI 1.0.0 — Open Core Router
[R2] Powered by ASL Core Kernel v1.0.0
```

---

## 3. Rantai Boot & Data Plane Pipeline
1. **Linker Script (`linker.ld`):** Higher-half virtual address `0xFFFF800000100000`, 4KB page alignment, PHDRS Limine.
2. **Entrypoint Stub (`_start` di `src/main.rs`):** Assembly trampoline mengatur stack 512KB page-aligned, melompat ke `rinjani_kernel_main`.
3. **Telemetri Serial COM1 (`0x3F8`):** Memancarkan marker deterministic bertahap `[R1]`..`[R12]`.
4. **Data Plane Flow (Zero-Copy):**
   $$\text{PCI Bus Scan} \rightarrow \text{VirtIO-Net Device} \rightarrow \text{DescriptorRing (Fastpath)} \rightarrow \text{NetBuffer Pool} \rightarrow \text{NetStack (ARP/IPv4/ICMP)}$$
5. **Mastering ISO Hybrid (`scripts/build-iso.ps1`):** `xorriso` menggabungkan kernel ELF + `limine.conf` + Limine BIOS/UEFI sys, lalu `limine.exe bios-install` menanamkan boot code.
6. **Runtime VM Execution:** VirtualBox mem-boot ISO headless dan menangkap telemetri COM1.
4. **Mastering ISO Hybrid (`scripts/build-iso.ps1`):** `xorriso` menggabungkan kernel ELF + `limine.conf` + Limine BIOS/UEFI sys, lalu `limine.exe bios-install` menanamkan boot code.
5. **Runtime VM Execution:** VirtualBox mem-boot ISO headless dan menangkap telemetri COM1.

---

## 4. Aturan Kerja Agen di `C:\OpenCR`
1. Baca `docs/CANONICAL/CANONICAL_MASTER.md`, `docs/CANONICAL/NAMING_POLICY.md`, dan `docs/CANONICAL/VERSION_REGISTER.md`.
2. Root repository wajib bersih (zero clutter). Dilarang membuat file sementara di root.
3. Seluruh commit wajib lolos `cargo test --workspace` dan `cargo check --target x86_64-unknown-none`.
4. Dilarang membocorkan IP internal riil pada dokumentasi publik (gunakan rentang RFC 5737).
