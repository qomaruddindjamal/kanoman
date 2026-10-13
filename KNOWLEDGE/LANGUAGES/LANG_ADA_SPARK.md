# TIER-2 DOSSIER: ADA / SPARK (ADA 2012 / SPARK 2014)

> **Language ID:** 16 | **Catalog Status:** CURATED  
> **Mentor:** Anti Gravity | **Ingestion Target:** Kanoman AI Curriculum  
> **Lisensi Referensi:** ISO/IEC 8652 (Standard Internasional) / GNAT GPL/FSF  

---

## 1. Identitas & Sejarah Singkat
- **Pencipta:** Jean Ichbiah di CII Honeywell Bull (1980) atas tender Departemen Pertahanan AS (DoD). Dinamai dari Ada Lovelace, programmer komputer pertama di dunia.
- **Evolusi:** Ada 83, Ada 95 (bahasa OOP terstandarisasi pertama di dunia), Ada 2005, Ada 2012 (memperkenalkan aspek *Design by Contract* native), dan Ada 2022.
- **SPARK:** Subset Ada yang dapat dibuktikan secara matematis (*provable subset*) yang dikembangkan oleh Bernard Carré dan Praxis Critical Systems (kini Capgemini/AdaCore).
- **Filosofi Inti:** *Readability over writability*, *Strong typing as a safety barrier*, *Early detection of errors at compile time*, *Formal verification of absence of runtime errors (AoRTE)*.

---

## 2. Paradigma, Model Memori & Type System
- **Paradigma:** Multi-paradigma (structured imperative, object-oriented, task-based concurrent, contracts-driven formal).
- **Type System:** Static strong, nominal typing ekstrem. Tidak ada implicit casting antar tipe numerik (tipe integer dengan range berbeda dianggap tipe yang berbeda secara mutlak). Mendukung *subtype ranges* (misal `subtype Packet_Size is Integer range 64 .. 1518;`).
- **Model Memori & Verifikasi SPARK:**
  - Larangan alokasi dinamis tidak terbatas (*heapless execution*) pada level profil kritis (Ravenscar Profile).
  - SPARK meniadakan pointer aliasing tak terkontrol via aturan kepemilikan terinspirasi linear logic.
  - Theorem prover GNATprove membuktikan secara formal ketiadaan divide-by-zero, buffer overflow, array out-of-bounds, dan unhandled exceptions.

---

## 3. Toolchain, Compiler & Runtime Execution
- **Compiler:** GNAT (GNU Ada Translator, bagian dari GCC upstream).
- **Proof Engine:** GNATprove (menggunakan CVC4, Z3, Alt-Ergo SMT solvers).
- **Runtime Profile:**
  - *Full Runtime:* Mendukung exception handling dan tasking dinamis.
  - *Zero Footprint (ZFP) / Ravenscar:* Ditujukan khusus untuk bare-metal microkernel avionik DO-178C DAL-A dan space onboard software (tanpa libc, footprint memori < 10 KB).

---

## 4. Idiom Utama & Hello World Carrier-Grade
```ada
package Carrier_Packet_Filter with SPARK_Mode is
   type IPv4_Address is array (1 .. 4) of Natural range 0 .. 255;
   type Port_Number is new Natural range 0 .. 65535;

   type Filter_Action is (Permit, Deny);

   -- Design by Contract: Kontrak pra-kondisi dan pasca-kondisi terverifikasi formal
   function Classify_Ingress (
      Src_IP : IPv4_Address;
      Dst_IP : IPv4_Address;
      Port   : Port_Number
   ) return Filter_Action
     with Pre => Dst_IP(1) /= 127, -- Tidak menerima loopback pada ingress publik
          Post => (if Port = 22 then Classify_Ingress'Result = Deny);
end Carrier_Packet_Filter;
```

---

## 5. Relasi & Penerapan di Open Core Router / ASL Core Kernel
- **Saudara Filosofis Avionik:** Standar **DO-178C DAL-A** dan **ARINC 653 IMA** secara historis lahir dari ekosistem Ada/SPARK.
- **Inspirasi Kontrak API Rust:** Desain `asl-router-tcam` (default-deny) dan `asl-router-lpm` (bounded radix search) mengadopsi prinsip verifikasi batas formal yang dipelopori SPARK.
- **Interoperabilitas Biner:** Modul avionik yang ditulis dalam Ada/SPARK dapat saling bertukar frame dengan ASL Core Kernel melalui standar C ABI dan zero-copy AFDX channel (`asl-afdx-ipc`).

---

## 6. Anti-Pattern & Jebakan Fatal (Failure Modes)
1. **Dynamic Memory Leakage di Flight Software:** Menggunakan `new` tanpa unchecked deallocation pada loop penerbangan non-Ravenscar profile.
2. **Constraint_Error pada Range Terbatas:** Terjadi crash runtime jika input eksternal melampaui range subtype tanpa sanitasi defensif di boundary I/O.
3. **Suppressed Checks (`pragma Suppress`):** Mematikan runtime checks demi performa sebelum membuktikan ketiadaan error via GNATprove, yang dapat memicu undefined behavior.

---

## 7. Perbandingan Head-to-Head (Trade-off Matrix)
| Metrik | Ada / SPARK | Rust (#![no_std]) | C (MISRA) | Zig |
| :--- | :--- | :--- | :--- | :--- |
| **Formal Proof (AoRTE)** | Otomatis via SMT (Z3/CVC4) | Kani / Prusti (Experimental) | Frama-C (Kompleks) | Belum ada formal proof |
| **Safety Invariants** | Sangat Tinggi (Nominal + Range) | Sangat Tinggi (Borrow Check) | Manual (Linter dependent) | Menengah (Comptime) |
| **Adopsi Carrier/Modern** | Terbatas (Pertahanan/Avionik) | Sangat Luas (Next-Gen OS) | Standar Lama De Facto | Tumbuh di Toolchain |
| **Kecepatan Development** | Lambat (Verifikasi Ketat) | Menengah | Cepat | Cepat |

---

## 8. Referensi Standar & Sumber Otoritatif
- **ISO/IEC 8652:2023 Ada Reference Manual:** https://www.adaic.org/resources/add_content/standards/22rm/html/RM-TOC.html
- **SPARK 2014 Reference Manual (AdaCore):** https://docs.adacore.com/live/wave/spark2014/html/spark2014_rm/
- **DO-178C / ED-12C Software Considerations in Airborne Systems (RTCA/EUROCAE):** https://www.rtca.org/
