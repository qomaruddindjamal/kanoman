# COMPUTER SCIENCE FOUNDATIONS: COMPILERS, LINKERS & BARE-METAL BINARIES

> **Subsystem:** Toolchain Architecture & Binary Anatomy  
> **Target OS:** Rinjani 1.0.0 (Powered by ASL Core Kernel v1.0.0)  
> **Standard:** ELF-64 Specification / Limine Base Protocol v2  

---

## 1. Pipeline Kompilasi Bare-Metal Rust

```
[Rust Source (.rs)] 
        │  (rustc frontend: parsing, type check, borrow check)
        ▼
[High-Level IR (HIR) / Mid-Level IR (MIR)]
        │  (monomorphization & safety transformation)
        ▼
[LLVM Intermediate Representation (LLVM IR)]
        │  (opt-level=3, LTO, dead code elimination, auto-vectorization)
        ▼
[Machine Assembly (.s) / Object Files (.o)]
        │  (rust-lld linker / linker script: page alignment 0x1000)
        ▼
[ELF-64 Executable (asl-kernel.elf)]
        │  (xorriso / limine bios-install)
        ▼
[Hybrid Bootable El Torito ISO (rinjani-1.0.0-x86_64.iso)]
```

---

## 2. Struktur Section Biner Kernel ELF-64

| Section Name | Type | Flags | Tujuan & Alokasi Memori |
| :--- | :--- | :--- | :--- |
| **`.limine_requests`** | `PROGBITS` | `ALLOC` | Magic UUID array request tags yang dibaca Limine bootloader saat handoff. |
| **`.text.entry`** | `PROGBITS` | `ALLOC, EXECINSTR` | Assembly trampoline `_start`: set RSP, luruskan 16-byte, lompat ke `rinjani_kernel_main`. |
| **`.text`** | `PROGBITS` | `ALLOC, EXECINSTR` | Instruksi kode mesin yang dieksekusi CPU. |
| **`.rodata`** | `PROGBITS` | `ALLOC` | Konstanta string, static dispatch tables, banner boot text, lookup masks. |
| **`.data`** | `PROGBITS` | `ALLOC, WRITE` | Variabel global yang diinisialisasi nilai awal. |
| **`.bss`** | `NOBITS` | `ALLOC, WRITE` | Variabel tidak terinisialisasi dan stack statis 512 KB (`_rinjani_stack_bottom`..`top`). Zero-filled saat load. |

---

## 3. Linker Discipline & Alignment Rules
1. **Higher-Half Kernel Mapping:** Kernel dialokasikan pada virtual address higher-half (misal `0xFFFF_8000_0000_0000` atau dipetakan identitas via Limine HHDM).
2. **Page Boundary (`0x1000`):** Setiap segmen `PT_LOAD` wajib diluruskan pada batas kelipatan 4096 byte (`p_align = 0x1000`) agar atribut proteksi MMU (`R`, `W`, `X`) dapat diterapkan per halaman memori tanpa tabrakan.
3. **No Unresolved Symbols:** Pada target freestanding `#![no_std]`, seluruh simbol harus terselesaikan secara statis. Ketiadaan fungsi dasar seperti `memcpy`, `memset`, atau `panic_handler` akan menggagalkan linking.
