# Kanoman AI — Recovery & Checkpoint Architecture

**Versi:** 1.0.0  
**Tanggal:** 2026-10-10  

---

## 1. Ikhtisar Mesin Pemulihan (Recovery Engine)

Untuk mencegah kehilangan status kerja atau ketidakkonsistenan state akibat kegagalan jaringan, timeout AI, atau penghentian proses tak terduga, Kanoman AI mengimplementasikan **Atomic Checkpoint Engine**.

Setiap checkpoint merepresentasikan rekaman snapshot titik waktu yang berisi:
- `checkpoint_id`: Identifier unik format `chk_<hex12>`.
- `task_id`: Tautan ke task yang sedang dikerjakan.
- `status`: Status eksekusi (`COMPLETED`, `FAILED`, dll.).
- `change_summary`: Ringkasan tindakan yang dilakukan (dengan sanitasi credential).
- `test_results`: Hasil pengujian otomatis (bila ada).
- `next_steps`: Rekomendasi langkah pemulihan berikutnya.
- `created_at`: Timestamp standar UTC ISO-8601.

---

## 2. Jaminan Atomic File Write

Menulis langsung ke file tujuan berisiko menghasilkan file korup jika proses mati di tengah operasi tulis (*torn write*). Kanoman menjamin integritas file dengan pola:
1. File ditulis ke temporary file di direktori yang sama (`tempfile.NamedTemporaryFile`).
2. Data diflush dan ditutup.
3. Operasi penggantian file atomik (`temp_path.replace(dest_path)`) dijalankan. Pada Windows dan POSIX, ini merupakan operasi atomik di tingkat sistem berkas selama berada pada filesystem yang sama.
4. Jika terjadi kegagalan, file sementara segera dihapus dan pesan error dicatat.

---

## 3. Prosedur Melanjutkan Pekerjaan (Resuming)

Jika task terhenti atau berstatus `FAILED`:
1. Baca checkpoint terakhir menggunakan:
   ```bash
   kanoman checkpoint list
   kanoman checkpoint show chk_<id>
   ```
2. Validasi integritas JSON skema.
3. Jalankan pemulihan programatik melalui `RecoveryEngine.resume_task(task, checkpoint)`:
   - State `FAILED` ditransisikan secara aman ke `RETRYING` lalu `RUNNING`.
   - State terminal (`COMPLETED`, `CANCELLED`) ditolak untuk mencegah eksekusi ganda non-idempoten.
