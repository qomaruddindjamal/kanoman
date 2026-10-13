# TIER-2 DOSSIER: ERLANG / OTP (BEAM RUNTIME & FAULT TOLERANCE)

> **Language ID:** 17 | **Catalog Status:** CURATED  
> **Mentor:** Anti Gravity | **Ingestion Target:** Kanoman AI Curriculum  
> **Lisensi Referensi:** Apache License 2.0 (Erlang/OTP)  

---

## 1. Identitas & Sejarah Singkat
- **Pencipta:** Joe Armstrong, Robert Virding, dan Mike Williams di Ericsson Computer Science Laboratory (1986).
- **Tujuan Asal:** Membangun perangkat lunak switching telekomunikasi carrier-grade generasi baru (AXD301 ATM switch) yang membutuhkan ketersediaan tinggi (*nine nines* / 99.9999999% uptime), konkurensi masif, dan kemampuan hot-code swapping tanpa restart perangkat keras.
- **Evolusi:** Dirilis sebagai open source pada akhir 1998; berkembang menjadi platform OTP (Open Telecom Platform) yang diadopsi industri perpesanan, fintech, distributed database (CouchDB, Riak), dan gateway IoT global.

---

## 2. Paradigma, Model Memori & Type System
- **Paradigma:** Fungsional murni berbasis aktor (*Actor Model*), concurrent, message-passing, distributed.
- **Type System:** Dinamis dengan pengecekan runtime; *Dialyzer* menyediakan verifikasi tipe statis parsial melalui *success typing* tanpa anotasi manual berlebih.
- **Model Memori & Konkurensi:**
  - **Shared-Nothing Memory:** Setiap proses Erlang memiliki ruang memori independen (stack dan heap sendiri). Tidak ada lock atau shared memory antardua proses.
  - **Isolated Garbage Collection:** GC beroperasi per-proses, menghilangkan jeda *stop-the-world* yang sering melumpuhkan runtime JVM/Go.
  - **Lightweight Green Processes:** Mampu menampung jutaan proses bersamaan pada memori beberapa gigabyte dengan biaya alokasi sekitar 300 kata per proses.

---

## 3. Toolchain, Compiler & Runtime Execution
- **Compiler:** `erlc` mengompilasi kode sumber `.erl` menjadi bytecode `.beam`.
- **Virtual Machine:** BEAM (Bogdan's Erlang Abstract Machine), runtime berbasis register yang sangat dioptimasi untuk konkurensi non-blocking, I/O multiplexing, dan penjadwalan preemptif berbasis pengurangan reduksi (*reduction budget* per proses).
- **OTP Architecture:** Standarisasi modul seperti `gen_server`, `gen_statem`, `supervisor`, dan `application`.

---

## 4. Filosofi & Idiom Inti: "Let It Crash" & Supervision Trees
- **"Let It Crash" Doctrine:** Pemrogram tidak dipaksa menulis penanganan error defensif berbelit-belit di setiap fungsi. Jika input anomali atau kondisi abnormal terjadi, proses tersebut dibiarkan mati seketika (*fail-fast*).
- **Supervision Tree:** Proses pengawas (*Supervisor*) bertanggung jawab mendeteksi kematian proses anak dan menjalankan strategi pemulihan terstandarisasi (`one_for_one`, `one_for_all`, `rest_for_one`).
- **Error Kernel Pattern:** Memisahkan logika state yang sangat vital ke proses inti berukuran kecil yang sangat terverifikasi, sementara pekerjaan rentan kegagalan dijalankan oleh proses pekerja sementara.

---

## 5. Contoh Kode Idiomatis Carrier-Grade
```erlang
-module(carrier_nat_worker).
-behaviour(gen_server).

%% API
-export([start_link/0, lookup_translation/2]).
%% gen_server callbacks
-export([init/1, handle_call/3, handle_cast/2, terminate/2]).

start_link() ->
    gen_server:start_link({local, ?MODULE}, ?MODULE, [], []).

lookup_translation(SrcIP, DstIP) ->
    gen_server:call(?MODULE, {translate, SrcIP, DstIP}).

init([]) ->
    %% Table state terisolasi dalam ETS heapless/in-memory
    Table = ets:new(nat_sessions, [set, private]),
    {ok, #{table => Table}}.

handle_call({translate, SrcIP, DstIP}, _From, State = #{table := Table}) ->
    case ets:lookup(Table, {SrcIP, DstIP}) of
        [{_, TransIP}] -> {reply, {ok, TransIP}, State};
        [] ->
            TransIP = {192, 168, 57, 10},
            ets:insert(Table, {{SrcIP, DstIP}, TransIP}),
            {reply, {ok, TransIP}, State}
    end;
handle_call(_Req, _From, State) ->
    {reply, {error, unknown_call}, State}.

handle_cast(_Msg, State) ->
    {noreply, State}.

terminate(_Reason, _State) ->
    ok.
```

---

## 6. Komparasi Kritis: "Let It Crash" vs ARINC 653 IMA Spatial Partitioning
Terdapat perbedaan arsitektural fundamental antara pendekatan Erlang dan pendekatan sistem avionik deterministik:

| Parameter Evaluasi | Erlang / OTP "Let It Crash" | ARINC 653 IMA / ASL Core Kernel |
| :--- | :--- | :--- |
| **Tingkat Keparahan** | Cocok untuk kegagalan transien di telekomunikasi | Memenuhi DO-178C DAL-A (kegagalan fatal adalah malapetaka) |
| **Model Isolasi** | Proses BEAM terisolasi di user-space | Partisi spasial memori (MMU/Paging) & temporal frame statis |
| **Respons Kegagalan**| Matikan proses anak -> Restart via Supervisor | Health Monitoring (HM) invoke fail-safe safe-state / TMR voting |
| **Alokasi Memori** | Alokasi per proses dinamis via allocator VM | Alokasi statis saat boot, nol alokasi dinamis saat runtime |
| **Jaminan Temporal** | Preemption lunak berbasis hitungan reduksi | Penjadwalan deterministik *Major/Minor Frame* ARINC 653 |

---

## 7. Relevansi & Penerapan pada Open Core Router
1. **Control Plane Daemon Pattern:** Pola supervision tree Erlang menjadi cetak biru bagi arsitektur control-plane daemons (seperti routing engine BGP/OSPF dan REST/WebUI daemons) di lapisan userland/distribusi Rinjani.
2. **Watchdog Health Recovery:** Meskipun kernel Rinjani tidak menggunakan BEAM di jalur cepat paket (Fastpath Ring tetap Rust `#![no_std]` bare-metal), konsep pemisahan failure domain (*error kernel*) diadopsi di mana partisi data plane dilindungi secara mutlak agar tidak terpengaruh crash pada antarmuka manajemen atau CLI shell.
3. **Telemetri Tanpa Kunci (Lockless Telemetry):** Model pesan asinkron Erlang menginspirasi komunikasi ring buffer lockless antara driver hardware dan monitor telemetri.

---

## 8. Sumber Otoritatif & Referensi
- Armstrong, Joe. *Programming Erlang: Software for a Concurrent World*. Pragmatic Bookshelf, 2013.
- Virding, Robert, et al. *Concurrent Programming in ERLANG*. Prentice Hall, 1996.
- Ericsson AB. *Erlang/OTP System Documentation (Upstream Reference)*: https://www.erlang.org/doc/
- ADR-009 Open Core Router Language Policy (Multi-Language Curriculum Backlog).
