# TIER-1 DOSSIER: RUST

> **Language ID:** 1 | **Catalog Status:** CANONICAL  
> **Mentor:** Anti Gravity | **Ingestion Target:** Kanoman AI Curriculum  

---

## 1. Identitas & Sejarah Singkat
- **Pencipta:** Graydon Hoare (Mozilla Research), pertama muncul 2010, rilis 1.0 pada Mei 2015.
- **Tujuan Asli:** Menghadirkan performa sistem sekelas C/C++ tanpa kerentanan memory corruption (use-after-free, double free, null pointer dereference) dan race condition.
- **Filosofi Inti:** *Zero-cost abstractions*, *Memory safety without garbage collection*, *Fearless concurrency*.

---

## 2. Paradigma, Model Memori & Type System
- **Paradigma:** Multi-paradigma (imperative, functional traits, concurrent actor/channels).
- **Type System:** Static strong, affine type system (linear ownership model), algebraic data types (`enum`, `struct`), trait-based polymorphism (monomorphization/static dispatch default, dynamic dispatch via `dyn Trait`).
- **Model Memori:**
  - **Ownership & Move Semantics:** Setiap nilai memiliki tepat satu pemilik (owner). Saat binding dipindahkan, hak akses nilai lama menjadi invalid.
  - **Borrow Checker:** Mendukung *aliasing XOR mutability* — banyak pembaca immutable (`&T`) ATAU tepat satu penulis mutable (`&mut T`), tidak pernah keduanya secara bersamaan.
  - **Lifetimes (`'a`):** Anotasi waktu hidup compile-time yang menjamin tidak ada reference yang menggantung (dangling pointers).

---

## 3. Toolchain, Compiler & Runtime Execution
- **Compiler:** `rustc` menggunakan LLVM sebagai code generator backend.
- **Build System & Package Manager:** `cargo`.
- **Target Kompilasi:** Mendukung bare-metal freestanding `target = x86_64-unknown-none`, WASM, hingga platform POSIX/Windows.
- **Runtime Cost:** Zero-runtime default. Pada mode `#![no_std]`, runtime hanya terdiri atas stack initialization dan panic handler minimal.

---

## 4. Idiom Utama & Hello World Carrier-Grade
```rust
#![no_std]

#[repr(C, align(64))]
pub struct FastpathRing<T, const N: usize> {
    head: core::sync::atomic::AtomicUsize,
    tail: core::sync::atomic::AtomicUsize,
    buffer: [T; N],
}

impl<T: Copy + Default, const N: usize> FastpathRing<T, N> {
    pub const fn new(init: T) -> Self {
        Self {
            head: core::sync::atomic::AtomicUsize::new(0),
            tail: core::sync::atomic::AtomicUsize::new(0),
            buffer: [init; N],
        }
    }
}
```

---

## 5. Relasi & Penerapan di Open Core Router / ASL Core Kernel
- **Fondasi Mutlak:** Seluruh kernel (`asl-kernel/*`) dan seluruh subsistem router (`router/*`) ditulis 100% dalam Rust `#![no_std]`.
- **Determinisme DO-178C DAL-A:** Zero heap allocation pada fastpath (semua buffer statis via BSS/DMA rings).
- **Safety Invariants:** Menghilangkan buffer overflow pada pemrosesan frame jaringan (VirtIO, Ethernet, IPv4, TCAM).

---

## 6. Anti-Pattern & Jebakan Fatal (Failure Modes)
1. **Unsound Unsafe Transmute:** Melakukan transmute byte slice ke referensi struct packed tanpa validasi alignment.
2. **Hidden Stack Allocation Overflow:** Mengalokasikan array jumbo di frame fungsi stack (misal `let buf = [0u8; 2097152]`) yang menyebabkan stack overflow pada stack bare-metal 512KB.
3. **Spinlock Deadlock under Interrupt:** Mengambil `spin::Mutex` di thread context lalu diakses kembali dalam Interrupt Service Routine (ISR) pada core yang sama.

---

## 7. Perbandingan Head-to-Head (Trade-off Matrix)
| Metrik | Rust | C | C++ | Zig |
| :--- | :--- | :--- | :--- | :--- |
| **Memory Safety** | Compile-time guaranteed | Manual (raw pointers) | RAII + smart pointers | Comptime checks (manual memory) |
| **Garbage Collector** | None | None | None | None |
| **Compile Speed** | Sedang - Lambat (Borrow check) | Sangat Cepat | Lambat (Templates) | Sangat Cepat |
| **Expressiveness** | Pattern matching, Traits | Primitif, Makro | Ekstrem, Kompleks | Minimalis, Comptime |

---

## 8. Referensi Standar & RFC Relevan
- **The Rust Reference:** https://doc.rust-lang.org/reference/
- **Rust Nomicon (Unsafe Rust):** https://doc.rust-lang.org/nomicon/
- **Embedded Rust Book (no_std):** https://docs.rust-embedded.org/book/
