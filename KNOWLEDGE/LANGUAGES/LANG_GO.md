# TIER-2 DOSSIER: GO (GOLANG — CONCURRENCY & CLOUD-NATIVE NETWORKING)

> **Language ID:** 18 | **Catalog Status:** CURATED  
> **Mentor:** Anti Gravity | **Ingestion Target:** Kanoman AI Curriculum  
> **Lisensi Referensi:** BSD-3-Clause (Google Go Open Source License)  

---

## 1. Identitas & Sejarah Singkat
- **Pencipta:** Robert Griesemer, Rob Pike, dan Ken Thompson di Google (2007, rilis publik 2009).
- **Tujuan Asal:** Mengatasi kompleksitas, waktu kompilasi yang lambat pada C++, dan overhead konkurensi di lingkungan sistem terdistribusi berskala masif (Google server backend).
- **Evolusi:** Go 1.0 (2012, janji kompatibilitas mundur mutlak), Go 1.11 (Go Modules), Go 1.18 (Generics / Type Parameters).
- **Filosofi Inti:** *Simplicity over cleverness*, *Orthogonality*, *Fast compilation*, *Composition over inheritance*, *Built-in concurrency primitives*.

---

## 2. Paradigma, Model Memori & Type System
- **Paradigma:** Konkuren imperatif, berorientasi struktur (*structural typing / duck typing via interfaces*), prosedural.
- **Type System:** Static strong, statically typed, tanpa implicit casting. Tipe interface didefinisikan secara implisit (tipe apa pun yang mengimplementasikan method yang cocok secara otomatis memenuhi interface tanpa deklarasi `implements`).
- **Model Memori & Konkurensi:**
  - **CSP (Communicating Sequential Processes):** *"Do not communicate by sharing memory; instead, share memory by communicating"* melalui channels.
  - **Goroutines:** Green thread sangat ringan dengan stack awal 2 KB yang dapat tumbuh dan menyusut secara dinamis.
  - **Go Runtime & Garbage Collection:** Menggunakan concurrent tri-color mark-and-sweep GC dengan target jeda STW (*Stop-the-World*) sub-milidetik (< 1 ms).

---

## 3. Toolchain, Compiler & Runtime Execution
- **Toolchain:** `go build`, `go test`, `go vet`, `go mod`.
- **Compiler:** `gc` (Go compiler standar) menghasilkan biner mandiri (*statically linked single binary*) tanpa dependensi shared library eksternal.
- **Runtime Engine:** Runtime Go terintegrasi di dalam setiap biner berekstensi native, mengelola M:N multiplexing scheduler (G-M-P model: Goroutine, Machine OS thread, Processor logical context).

---

## 4. Idiom Utama & Hello World Carrier Tooling
```go
package main

import (
	"context"
	"fmt"
	"net/http"
	"time"
)

// RouterHealthAgent: Daemon telemetri host-side untuk Open Core Router
func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"system": "OpenCR", "status": "UP", "time": "%s"}`, time.Now().Format(time.RFC3339))
	})

	srv := &http.Server{
		Addr:         ":9090",
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
	}

	fmt.Println("[HOST-AGENT] Telemetry server listening on :9090")
	_ = srv.ListenAndServe()
}
```

---

## 5. DOKTRIN KETAT: LARANGAN GO DI DALAM KERNEL
Sesuai Doktrina Platform ADR-004 dan DECISION_REGISTER.md:
1. **Dilarang Mutlak di Kernel ASL Core & Fastpath:**
   Go memiliki runtime bawaan yang mewajibkan Garbage Collection non-deterministik dan alokasi memori dinamis di heap runtime. Karakteristik ini melanggar secara langsung standar kedirgantaraan **DO-178C DAL-A** dan **ARINC 653 IMA Spatial/Temporal Partitioning** yang menuntut ketiadaan alokasi dinamis pada jalur cepat (*zero dynamic allocation in fastpath*).
2. **Kandidat Sangat Ideal untuk Host-Side Tooling & Orkestrasi:**
   Go adalah kandidat utama untuk perkakas eksternal di sisi host manajemen (seperti runner CI/CD, simulator topologi lab, generator artefak, atau telemetry aggregator di luar microkernel).

---

## 6. Komparasi: Go Runtime vs Rust `#![no_std]` Microkernel

| Parameter Evaluasi | Go Language Runtime | Rust `#![no_std]` (ASL Core / OpenCR) |
| :--- | :--- | :--- |
| **Runtime Overhead** | Membawa runtime 2 MB+ (GC, Scheduler) | Nol runtime (`no_std`), biner ELF murni |
| **Manajemen Memori** | Otomatis via Concurrent Tri-color GC | Statis, kepemilikan kompilasi (Borrow Checker)|
| **Kesesuaian Avionik**| Tidak kompatibel dengan DO-178C DAL-A| Lolos DO-178C DAL-A / ARINC 653 IMA |
| **Kemudahan Konkurensi**| Sangat mudah (goroutine & channel) | Deterministik (lockless ring, interrupt masking)|
| **Keluaran Target** | Userland aplikasi host / cloud | Bare-metal x86_64, aarch64, s390x, RISC-V |

---

## 7. Relevansi & Penerapan pada Ekosistem Open Core Router
1. **Host-Side Test Harness:** Menulis skrip integrasi pengujian jaringan end-to-end (misal simulasi 10,000 klien DHCP atau traffic generator L4) pada PC penguji.
2. **Microservices Telemetri Eksternal:** Layanan pengumpul metrik Prometheus / OpenTelemetry yang mengambil data read-only dari port serial atau REST API Rinjani.
3. **Pemisahan Batas Sistem:** Menjadi contoh kasus pemisahan tanggung jawab yang jelas antara kernel deterministik tinggi dan perkakas cloud-native modern.

---

## 8. Sumber Otoritatif & Referensi
- Donovan, Alan A. A., and Brian W. Kernighan. *The Go Programming Language*. Addison-Wesley, 2015.
- Pike, Rob. *Go Concurrency Patterns*. Google I/O, 2012.
- The Go Authors. *Go Documentation & Language Specification (Upstream)*: https://go.dev/doc/
- ADR-004 Platform Doctrine (ASL Core is NOT Linux).
- ADR-009 Open Core Router Language Policy.
