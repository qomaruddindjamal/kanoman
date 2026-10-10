# ADR-0001: Arsitektur Inti, Packaging, dan Pola Isolasi Kanoman AI

- **Status:** Diterima (Accepted)
- **Tanggal:** 2026-10-10
- **Pengambil Keputusan:** Principal Software Architect, AI Systems Architect, Application Security Engineer

---

## 1. Konteks

Kanoman AI dirancang sebagai fondasi orkestrasi pengembangan perangkat lunak bertenaga AI (*AI Development Orchestrator*). Untuk memastikan keandalan, keamanan eksekusi, serta skalabilitas jangka panjang, Kanoman harus:
1. Menghindari ketergantungan (vendor lock-in) pada satu penyedia model AI tertentu.
2. Memastikan pengujian otomatis dapat dijalankan secara instan di CI tanpa memerlukan kuota API berbayar atau GPU lokal.
3. Mencegah operasi Git destruktif atau eksekusi pada repositori yang keliru.
4. Mencegah kebocoran rahasia (*credentials leak*) ke log maupun Git commit.

---

## 2. Alternatif yang Dipertimbangkan

1. **Monolitik LangChain / LlamaIndex:**
   - *Kelebihan:* Ekosistem library siap pakai.
   - *Kekurangan:* Bobot dependensi sangat besar, API kerap berubah secara breaking, sulit diaudit keamanannya, dan rawan bug transitif.
2. **Framework Microservice Multi-Container (FastAPI + Celery + PostgreSQL + Redis):**
   - *Kelebihan:* Kemampuan skalabilitas horizontal tinggi.
   - *Kekurangan:* Terlalu kompleks untuk fondasi awal (over-engineering), sulit dijalankan di lingkungan lokal developer tanpa Docker, dan memicu overhead operasional yang belum dibutuhkan.
3. **Hexagonal Architecture Berbasis Python Standar & Pydantic v2 (Pilihan yang Diadopsi):**
   - *Kelebihan:* Ringan, cepat, modul terisolasi rapi via *Ports and Adapters*, validasi data ketat via Pydantic v2, pengujian 100% offline via mock adapter, dan eksekusi Git terisolasi menggunakan subprocess langsung.
   - *Kekurangan:* Memerlukan penulisan kontrak adapter sendiri (namun memberikan kendali dan transparansi 100%).

---

## 3. Keputusan

Kami memutuskan untuk:
1. **Menggunakan Python 3.12+ dengan layout `src/kanoman/`** dan packaging deklaratif berbasis `pyproject.toml` (PEP 517/621).
2. **Mengadopsi Hexagonal Architecture:**
   - *Core:* Logika orkestrasi task, project registry, dan checkpoint recovery yang murni tanpa ketergantungan library eksternal selain Pydantic.
   - *Ports/Adapters:* AI Provider (Mock, Gemini, Ollama), Git Controller, dan CLI/MCP.
3. **Mengisolasi Operasi Git via `GitController` Khusus:**
   - Semua perintah Git dijalankan via `subprocess.run(args, shell=False)`.
   - Melarang keras `git reset --hard` dan `--force`.
   - Mengunci target operasi ke repositori Kanoman yang tervalidasi.
4. **Menggunakan Atomic JSON File Storage:**
   - Snapshot checkpoint disimpan menggunakan penulisan atomik untuk menjamin integritas data tanpa memerlukan database engine eksternal.

---

## 4. Konsekuensi

### Positif:
- Sistem dapat diuji 100% offline dan deterministik di lingkungan CI GitHub Actions.
- Risiko keamanan injeksi shell dan kebocoran credential berkurang drastis (*fail-closed security*).
- Core bersih dan tidak terikat pada vendor AI mana pun.
- Zero external database management overhead.

### Negatif / Trade-offs:
- Adapter untuk setiap AI Provider baru harus ditulis dan diuji secara eksplisit mengikuti kontrak `AIProviderProtocol`.
- Penyimpanan file JSON atomik cocok untuk skala lokal/tim kecil; jika skala berkembang menjadi multi-user enterprise terdistribusi, layer storage perlu diekstrak ke SQL database.

---

## 5. Kondisi untuk Meninjau Ulang Keputusan

Keputusan ini akan ditinjau ulang apabila:
1. Kanoman berkembang menjadi sistem multi-user SaaS terpusat yang membutuhkan concurrent transactions tingkat tinggi (di mana PostgreSQL/Spanner menjadi kebutuhan nyata).
2. Tuntutan workflow graf asiklik terarah (DAG) memerlukan engine eksekusi komputasi terdistribusi khusus.
