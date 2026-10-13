# TIER-1 DOSSIER: PYTHON (3.10 - 3.12+)

> **Language ID:** 3 | **Catalog Status:** CANONICAL  
> **Mentor:** Anti Gravity | **Ingestion Target:** Kanoman AI Curriculum  

---

## 1. Identitas & Sejarah Singkat
- **Pencipta:** Guido van Rossum di CWI Belanda (1989), rilis publik 1991.
- **Evolusi:** Python 2.0 (2000), transisi Python 3.0 (2008), Python modern (3.11+ zero-cost exceptions, faster CPython, specialization).
- **Filosofi Inti (PEP 20 - Zen of Python):** *Beautiful is better than ugly*, *Explicit is better than implicit*, *Simple is better than complex*, *Readability counts*.

---

## 2. Paradigma, Model Memori & Type System
- **Paradigma:** Multi-paradigma (object-oriented, imperative, functional primitives, asynchronous coroutines).
- **Type System:** Dynamic strong typing, duck typing, type hints gradual via `typing` module (PEP 484) diperiksa statis via `mypy` atau `pyright`.
- **Model Memori:**
  - Semua entitas adalah object (`PyObject`) di heap.
  - Reference counting sebagai mekanisme manajemen memori primer didukung cyclic garbage collector heuristik (Generations 0, 1, 2).
  - Global Interpreter Lock (GIL) di CPython mencegah multithreading native simultan di shared heap (meskipun PEP 703 mulai memperkenalkan free-threaded build).

---

## 3. Toolchain, Compiler & Runtime Execution
- **Implementasi Primer:** CPython (bytecode interpreter dan stack machine).
- **Implementasi Alternatif:** PyPy (JIT tracing), GraalPy, RustPython.
- **Packaging Modern:** `uv`, `pip`, `poetry`, `wheel`, PEP 517/518 build backends (`flit`, `hatchling`).
- **Ekosistem AI/ML:** NumPy/SciPy/PyTorch/TensorFlow (wrapper C/C++/CUDA berkinerja tinggi).

---

## 4. Idiom Utama & Hello World Carrier-Grade
```python
import socket
import struct
from typing import Final

ETH_P_ALL: Final[int] = 0x0003

def capture_carrier_frame(interface: str) -> None:
    """Capture raw ethernet frames on carrier test interface."""
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL)) as s:
        s.bind((interface, 0))
        raw_data, _ = s.recvfrom(2048)
        dest_mac, src_mac, ethertype = struct.unpack("!6s6sH", raw_data[:14])
        print(f"Captured EtherType 0x{ethertype:04X} from {src_mac.hex(':')} to {dest_mac.hex(':')}")
```

---

## 5. Relasi & Penerapan di Open Core Router / ASL Core Kernel
- **Arsitektur Agen Kanoman:** Kanoman AI runtime, MCP tools server, dan modul quality-gate (`src/kanoman/*`) dibangun di atas Python.
- **Skrip Verifikasi & Otomasi:** Skrip evaluasi hygiene, linting, integrasi ISO, dan test harness eksternal dijalankan via skrip Python di `tools/`.
- **Bukan Kode Kernel:** Dilarang mengimpor runtime Python ke dalam kernel binary `#![no_std]` atau fastpath router.

---

## 6. Anti-Pattern & Jebakan Fatal (Failure Modes)
1. **Mutable Default Arguments:** `def append_to(val, lst=[])` menyebabkan state disharing antar pemanggilan fungsi.
2. **Hidden Latency Spikes (GC Stop-The-World):** Koleksi cycle GC yang memicu latency tak terduga pada telemetry pipeline real-time.
3. **Implicit Type Coercion / AttributeError in Production:** Mengabaikan static type checking (`mypy`) sehingga error `NoneType has no attribute` lolos ke runtime.

---

## 7. Perbandingan Head-to-Head (Trade-off Matrix)
| Metrik | Python | Go | Rust | TypeScript |
| :--- | :--- | :--- | :--- | :--- |
| **Kecepatan Development** | Sangat Tinggi | Tinggi | Menengah | Tinggi |
| **Kecepatan Eksekusi** | Rendah (Kecuali C-bindings) | Sangat Tinggi | Maksimal (Native) | Menengah (V8 JIT) |
| **Concurrency Native** | GIL bottleneck (kecuali async/mp) | Goroutines (CSP M:N) | Fearless native OS threads | Single-threaded Event Loop |
| **Ekosistem AI/Data** | Tak tertandingi (Leader) | Berkembang | Tumbuh pesat | Kuat di UI/Viz |

---

## 8. Referensi Standar & RFC Relevan
- **PEP 8 (Style Guide for Python Code):** https://peps.python.org/pep-0008/
- **PEP 484 (Type Hints):** https://peps.python.org/pep-0484/
- **Python C API Reference Manual:** https://docs.python.org/3/c-api/
