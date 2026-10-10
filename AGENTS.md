# Kanoman AI — Operational Instructions for AI Agents

Dokumen ini memuat aturan operasional, batasan hak akses, dan protokol kerja bagi AI Agent yang berinteraksi dengan workspace Kanoman.

---

## 1. Batasan Kerja Wajib

1. **Target Repositori:** Satu-satunya repositori target adalah `https://github.com/qomaruddindjamal/kanoman.git`.
2. **Larangan Repositori Luar:** Jangan pernah memodifikasi, meng-commit, atau mem-push ke repositori aplikasi lain (seperti MitraNet) selama sesi ini.
3. **Larangan Destruktif:**
   - DILARANG menjalankan `git reset --hard`.
   - DILARANG menggunakan flag `--force` atau `-f` pada operasi Git.
   - DILARANG menghapus data tanpa konfirmasi atau membuang uncommitted changes pengguna.
4. **Pencegahan Kebocoran Secret:**
   - DILARANG menuliskan API key, PAT token, private key, atau nilai rahasia apa pun ke file commit atau file contoh konfigurasi.
   - Gunakan `.env.example` hanya dengan nilai placeholder kosong atau aman.

---

## 2. Alur Kerja Rekayasa Terverifikasi

Setiap tugas pengembangan harus mengikuti siklus:
1. **Audit & Analisis:** Periksa keadaan riil codebase sebelum berasumsi.
2. **Desain:** Pastikan perubahan selaras dengan Hexagonal Architecture di `docs/ARCHITECTURE.md`.
3. **Implementasi Modular:** Buat kode dengan pengetikan ketat (type hints) dan penanganan error yang jelas.
4. **Pengujian Nyata:** Jalankan pengujian otomatis (`python -m pytest -v`) dan pastikan 100% lulus.
5. **Git Controller:** Seluruh operasi Git wajib melalui `GitController` dengan mode dry-run terlebih dahulu sebelum commit.
