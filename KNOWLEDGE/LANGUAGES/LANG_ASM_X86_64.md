# TIER-1 DOSSIER: x86_64 ASSEMBLY (AMD64 / INTEL 64)

> **Language ID:** 6 | **Catalog Status:** CANONICAL  
> **Mentor:** Anti Gravity | **Ingestion Target:** Kanoman AI Curriculum  

---

## 1. Identitas & Sejarah Singkat
- **Asal-Usul:** Intel 8086 (1978, 16-bit), 80386 (1985, 32-bit), arsitektur 64-bit AMD64 dirilis oleh AMD (1999) dan diadopsi Intel sebagai EM64T / Intel 64.
- **Sintaksis Utama:** Sintaks AT&T (`mov %rax, %rbx` - source first) vs Sintaks Intel/NASM (`mov rbx, rax` - dest first).
- **Filosofi Inti:** *Direct hardware manipulation*, *Zero abstraction layer*, *Direct control of execution units and registers*.

---

## 2. Paradigma, Model Memori & Type System
- **Paradigma:** Imperative, machine-level instruction dispatch.
- **Type System:** Untyped bit patterns. Makna data ditentukan semata-mata oleh instruksi yang memprosesnya (misal `ADD` vs `FADD` vs `PADDB`).
- **Model Memori & Register:**
  - 16 General Purpose Registers (GPR): `RAX`, `RBX`, `RCX`, `RDX`, `RSI`, `RDI`, `RBP`, `RSP`, `R8`-`R15`.
  - Special Registers: `RIP` (Instruction Pointer), `RFLAGS`, Segment Registers (`CS`, `DS`, `SS`, `FS`, `GS`), Control Registers (`CR0`, `CR3` Paging, `CR4`), MSRs (Model Specific Registers).
  - Memory Segments & Paging: Long Mode (4-level / 5-level page tables, PML4/PML5), virtual-to-physical address translation.

---

## 3. Toolchain, Compiler & Runtime Execution
- **Assemblers:** NASM, Yasm, GNU Assembler (`as`), LLVM Integrated Assembler.
- **Calling Conventions:**
  - **System V AMD64 ABI:** Parameter fungsi dioper via `RDI`, `RSI`, `RDX`, `RCX`, `R8`, `R9`. Return di `RAX`. Callee-saved: `RBX`, `RSP`, `RBP`, `R12`-`R15`.
  - **Microsoft x64:** Parameter fungsi via `RCX`, `RDX`, `R8`, `R9` dengan shadow space wajib 32-byte di stack.

---

## 4. Idiom Utama & Hello World Carrier-Grade
```asm
.section .text.entry, "ax"
.global _start
_start:
    cli                         /* Disable maskable interrupts */
    cld                         /* Clear direction flag for ABI compliance */
    lea rsp, [rip + _stack_top] /* Load higher-half stack pointer */
    and rsp, -16                /* Ensure 16-byte stack alignment for SSE */
    call kernel_entry           /* Transfer control to compiled Rust code */
2:
    hlt                         /* Halt CPU on unexpected return */
    jmp 2b                      /* Indefinite fail-safe loop */
```

---

## 5. Relasi & Penerapan di Open Core Router / ASL Core Kernel
- **Entry Trampoline (`_start`):** Titik pertama eksekusi Limine bootloader menyerahkan kontrol ke kernel di `asl-kernel-bin/src/main.rs`.
- **Interrupt & Trap Dispatchers:** Rutin stub IDT yang menyimpan register context ke stack saat terjadi hardware interrupt atau fault CPU.
- **Hardware Probing (CPUID, Port I/O):** Instruksi `cpuid`, `in`, `out`, `rdmsr`, `wrmsr` dioperasikan langsung via inline assembly.

---

## 6. Anti-Pattern & Jebakan Fatal (Failure Modes)
1. **Misaligned Stack on Call:** Kegagalan meluruskan `RSP` ke batas 16-byte sebelum instruksi `call`, yang memicu crash `#GP` (General Protection Fault) pada instruksi SSE `movaps`.
2. **Clobbered Callee-Saved Registers:** Merusak nilai `RBX`, `RBP`, atau `R12-R15` tanpa menyimpan (`push`/`pop`) di awal fungsi, merusak state pemanggil.
3. **Missing Memory Barriers:** Mengabaikan `sfence`/`lfence`/`mfence` pada penulisan DMA descriptors non-temporal atau register MMIO.

---

## 7. Perbandingan Head-to-Head (Trade-off Matrix)
| Metrik | x86_64 Assembly | ARM64 Assembly | RISC-V Assembly | C Inline Asm |
| :--- | :--- | :--- | :--- | :--- |
| **ISA Architecture** | Variable-length CISC | Fixed 32-bit RISC | Modular open RISC | Compiler dependent |
| **Register Count** | 16 GPR | 31 GPR (`X0-X30`) | 32 GPR (`x0-x31`) | Compiler managed |
| **Hardware Dominance** | Datacenter / PC | Mobile / Apple / Cloud | Open embedded / IoT | All platforms |

---

## 8. Referensi Standar & RFC Relevan
- **Intel 64 and IA-32 Architectures Software Developer Manuals:** https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html
- **AMD64 Architecture Programmer's Manual:** https://www.amd.com/en/resources/support-articles/tech-articles/AMD64-Architecture-Programmers-Manual.html
- **System V Application Binary Interface (AMD64 Architecture Processor Supplement):** https://gitlab.com/x86-psabis/x86-64-ABI
