# TIER-1 DOSSIER: TYPESCRIPT & JAVASCRIPT (ECMASCRIPT 2024+)

> **Language IDs:** 4, 5 | **Catalog Status:** CANONICAL  
> **Mentor:** Anti Gravity | **Ingestion Target:** Kanoman AI Curriculum  

---

## 1. Identitas & Sejarah Singkat
- **JavaScript (ECMAScript):** Diciptakan Brendan Eich di Netscape dalam 10 hari (1995). Distandarisasi oleh Ecma International (ECMA-262). Revolusi via V8 engine (2008) dan Node.js (2009).
- **TypeScript:** Diciptakan Anders Hejlsberg di Microsoft (2012) sebagai superset dengan tipe statis untuk skala enterprise.
- **Filosofi Inti:** *JavaScript everywhere*, *Gradual typing*, *Structural subtyping*.

---

## 2. Paradigma, Model Memori & Type System
- **Paradigma:** Multi-paradigma (event-driven, asynchronous I/O, prototype-based OOP, functional composition).
- **Type System:**
  - **JavaScript:** Dynamic weak typing, type coercion agresif (`"1" + 1 === "11"`).
  - **TypeScript:** Static structural typing ("duck typing" di compile time), union/intersection types, generics, mapped types, compile-time type erasure (menghasilkan JS murni).
- **Model Memori & Concurrency:**
  - Single-threaded event loop dengan asynchronous non-blocking task queue (Microtasks `Promises` dan Macrotasks `setTimeout`/`I/O`).
  - Heap-allocated objects dikelola oleh generational mark-and-sweep garbage collector (misal V8 Orinoco/Scavenger).

---

## 3. Toolchain, Compiler & Runtime Execution
- **Runtimes:** V8 (Chrome, Node.js), JavaScriptCore (Safari, Bun), SpiderMonkey (Firefox).
- **Transpilers & Bundlers:** `tsc`, `esbuild`, `swc`, `vite`, `turbopack`.
- **Runtimes Modern Server:** Node.js, Deno (built with Rust/V8), Bun (built with Zig/JSC).

---

## 4. Idiom Utama & Hello World Carrier-Grade
```typescript
interface PacketTelemetry {
  readonly interfaceId: string;
  readonly rxPackets: bigint;
  readonly txPackets: bigint;
  readonly drops: number;
}

export class TelemetryAggregator {
  private readonly records: Map<string, PacketTelemetry> = new Map();

  public recordMetrics(metrics: PacketTelemetry): void {
    if (metrics.drops > 0) {
      console.warn(`[ROUTER-ALERT] Interface ${metrics.interfaceId} experiencing drops: ${metrics.drops}`);
    }
    this.records.set(metrics.interfaceId, metrics);
  }
}
```

---

## 5. Relasi & Penerapan di Open Core Router / ASL Core Kernel
- **Web Dashboard & Visualizer:** Dashboard monitoring real-time OpenCR Rinjani di sisi operator NOC (Next.js/React/Vite).
- **REST/JSON Telemetry Gateway:** Antarmuka pengambil status router untuk integrasi ke OSS/BSS carrier telekomunikasi.
- **Strict Boundary:** Tidak digunakan dalam kernel bare-metal maupun ring buffer pemrosesan paket fisik.

---

## 6. Anti-Pattern & Jebakan Fatal (Failure Modes)
1. **Event Loop Blocking:** Menjalankan algoritma synchronous berat di main thread yang membekukan pemrosesan I/O socket.
2. **Abuse of `any` Type:** Menggunakan tipe `any` yang melumpuhkan kemampuan static type checker TypeScript.
3. **Floating Promise (Unhandled Rejection):** Memanggil fungsi async tanpa `await` atau `.catch()` yang menyebabkan error diam-diam terkubur.

---

## 7. Perbandingan Head-to-Head (Trade-off Matrix)
| Metrik | TypeScript | Dart | Python | Rust (Wasm) |
| :--- | :--- | :--- | :--- | :--- |
| **Integrasi Web Browser** | Standar De Facto (100%) | Via Flutter Web | Via Pyodide (Berat) | Native WebAssembly |
| **Type Rigor** | Struktural Kompilasi | Sound Static Type | Gradual (Hints) | Nominal Mutlak Statis |
| **Throughput Web I/O** | Sangat Tinggi (Async Event) | Tinggi | Menengah (FastAPI) | Sangat Tinggi (Actix) |

---

## 8. Referensi Standar & RFC Relevan
- **ECMA-262 ECMAScript Language Specification:** https://tc39.es/ecma262/
- **TypeScript Handbook:** https://www.typescriptlang.org/docs/handbook/
- **Node.js Diagnostics & Event Loop Guidelines:** https://nodejs.org/en/docs/guides/event-loop-timers-and-nexttick/
