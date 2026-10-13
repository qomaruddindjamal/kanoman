# KANOMAN OPEN QUESTIONS & ARCHITECTURAL LOG

> **Subsystem:** Engineering Governance & Open Clarifications  
> **Repository:** `C:\kanoman\STATE\OPEN_QUESTIONS.md`  

---

## 1. Pertanyaan Terbuka Aktif
| Q-ID | Subjek | Deskripsi | Rekomendasi Mentor / Status |
| :--- | :--- | :--- | :--- |
| **OQ-01** | smoltcp vs Native TCP | Apakah integrasi smoltcp akan mengorbankan batasan DO-178C DAL-A temporal determinism? | Diselesaikan via investigasi mendalam di RND_12 (Sprint berikutnya). |
| **OQ-02** | DHCP Server Pool Persistence | Apakah binding DHCP Server di LAN perlu disimpan ke NVRAM atau cukup static volatile RAM? | Volatile RAM default untuk fase VM; NVRAM persistent menyusul di gate storage. |
| **OQ-03** | Winbox Alternative | Bagaimana menyajikan WebUI yang seringan Winbox tanpa melanggar doktrin anti reverse-engineering? | Gunakan `htmx` + WebSocket lightweight dashboard berdasar REST/JSON terbuka (ADR-009 & ADR-010). |
