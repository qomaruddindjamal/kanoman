# TIER-1 DOSSIER: C (C99 / C11 / C23)

> **Language ID:** 2 | **Catalog Status:** CANONICAL  
> **Mentor:** Anti Gravity | **Ingestion Target:** Kanoman AI Curriculum  

---

## 1. Identitas & Sejarah Singkat
- **Pencipta:** Dennis Ritchie di Bell Labs (1972) untuk mengimplementasikan sistem operasi Unix di PDP-11.
- **Standar:** K&R, ANSI C (C89/C90), ISO C99, C11, C17, dan C23.
- **Filosofi Inti:** *Trust the programmer*, *Don't prevent the programmer from doing what needs to be done*, *Keep the language small and simple*.

---

## 2. Paradigma, Model Memori & Type System
- **Paradigma:** Imperative, procedural, structured programming.
- **Type System:** Static weak, nominal typing, implisit conversion, zero boundary checking pada array.
- **Model Memori:**
  - Flat linear address space, direct pointer arithmetic (`ptr + offset`).
  - Strict Aliasing Rule (C99): Pointer dengan tipe berbeda tidak boleh mereferensikan lokasi memori yang sama (kecuali `char*`).
  - Tiga area memori dasar: Static storage (`.data` / `.bss`), Automatic storage (stack), Dynamic storage (heap `malloc`/`free`).

---

## 3. Toolchain, Compiler & Runtime Execution
- **Compilers:** GCC, Clang (LLVM frontend), MSVC.
- **ABI Standard:** System V AMD64 ABI / Microsoft x64 ABI mendikte register passing conventions (RDI, RSI, RDX, RCX, R8, R9 vs RCX, RDX, R8, R9).
- **Runtime:** Minimal C runtime library (`crt0.o`). Pada bare-metal kernel, fungsi `libc` ditiadakan.

---

## 4. Idiom Utama & Hello World Carrier-Grade
```c
#include <stdint.h>

/* Volatile MMIO device register definition */
typedef struct {
    volatile uint32_t CTRL;
    volatile uint32_t STATUS;
    volatile uint32_t RDBAL;
    volatile uint32_t RDBAH;
    volatile uint32_t RDLEN;
    volatile uint32_t RDH;
    volatile uint32_t RDT;
} __attribute__((packed, aligned(64))) intel_82599_regs_t;

static inline void mmio_write32(volatile uint32_t *addr, uint32_t val) {
    *addr = val;
    __asm__ __volatile__("" : : : "memory");
}
```

---

## 5. Relasi & Penerapan di Open Core Router / ASL Core Kernel
- **Hardware Layout Standard:** Semua struktur descriptor Intel 82599, VirtIO, PCI, dan format frame jaringan di ASL Core didesain mengikuti standar C layout (`#[repr(C)]`).
- **Foreign Function Interface (FFI):** C ABI adalah lingua franca komunikasi lintas bahasa di level biner antar modul avionik.
- **Legacy Parity:** Standar RFC networking dan referensi driver DPDK C dipelajari sebagai spesifikasi arsitektur rujukan.

---

## 6. Anti-Pattern & Jebakan Fatal (Failure Modes)
1. **Undefined Behavior (UB):** Signed integer overflow, null pointer dereference, misaligned memory access.
2. **Buffer Overflow:** Penggunaan fungsi string tak berbatas (`strcpy`, `sprintf`, `gets`) yang membobol stack frame.
3. **Use-After-Free & Double Free:** Mutasi memory pointer setelah dilepas ke heap allocator, membuka celah privilege escalation.

---

## 7. Perbandingan Head-to-Head (Trade-off Matrix)
| Metrik | C | Rust | Zig | Ada |
| :--- | :--- | :--- | :--- | :--- |
| **Portabilitas Arsitektur** | Mutlak Universal (100% CPU) | Luas (Tier 1-3 LLVM) | Luas (LLVM/C emit) | Khusus Aerospace/Defense |
| **Safety Enforcement** | Sangat Rendah | Sangat Tinggi (Compiler) | Menengah (Comptime) | Ekstrem (SPARK formal) |
| **Binary Overhead** | 0% (Paling minimal) | 0% (no_std) | 0% | Sangat Rendah |
| **Kurva Belajar** | Landai diawal, Fatal diujung | Curam (Lifetimes) | Menengah | Sedang (Sintaks Pascal) |

---

## 8. Referensi Standar & RFC Relevan
- **ISO/IEC 9899:2018 (C17):** https://www.iso.org/standard/74528.html
- **SEI CERT C Coding Standard:** https://wiki.sei.cmu.edu/confluence/display/c/
- **MISRA C:2012 Guidelines for Automotive & Aerospace Systems:** https://www.misra.org.uk/
