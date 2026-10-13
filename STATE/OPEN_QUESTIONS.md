# KANOMAN OPEN QUESTIONS & ARCHITECTURAL LOG

> **Subsystem:** Engineering Governance & Open Clarifications  
> **Repository:** `C:\kanoman\STATE\OPEN_QUESTIONS.md`  

---

## 1. Pertanyaan Terbuka Aktif
| Q-ID | Subjek | Deskripsi | Rekomendasi Mentor / Status |
| :--- | :--- | :--- | :--- |
| **OQ-01** | smoltcp vs Native TCP | Apakah integrasi smoltcp akan mengorbankan batasan DO-178C DAL-A temporal determinism? | **RESOLVED by ADR-011**: Diadopsi sebagai vendor engine di balik facade netstack; isolasi partisi melindungi fastpath forwarding. |
| **OQ-02** | DHCP Server Pool Persistence | Apakah binding DHCP Server di LAN perlu disimpan ke NVRAM atau cukup static volatile RAM? | Volatile RAM default untuk fase VM; NVRAM persistent menyusul di gate storage. |
| **OQ-03** | Winbox Alternative | Bagaimana menyajikan WebUI yang seringan Winbox tanpa melanggar doktrin anti reverse-engineering? | Gunakan `htmx` + WebSocket lightweight dashboard berdasar REST/JSON terbuka (ADR-009 & ADR-010). |
| **OQ-04** | K5 Benchmark Socket vs Forwarding | Throughput socket lokal terminasi tercatat 326.4 Mbps (-61.2% degradasi vs 842 Mbps L3). Apakah degradasi ini dapat diterima owner untuk control-plane HTTP API? | Rekomendasi tim R&D: Sangat memadai untuk traffic management (< 50 Mbps peak). Data plane forwarding tetap berjalan di jalur 842+ Mbps zero-copy tanpa interupsi stack TCP socket. |
