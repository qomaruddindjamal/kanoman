# Kanoman AI — Project Onboarding Template & Guide

Template onboarding ini digunakan untuk mendaftarkan repositori atau proyek software baru di bawah manajemen Kanoman AI Orchestrator tanpa mengubah struktur core.

---

## 1. Spesifikasi Registrasi Proyek

Setiap proyek yang dikelola oleh Kanoman wajib didefinisikan dengan parameter keamanan berikut:

```python
from pathlib import Path
from kanoman.core.models import Project

new_project = Project(
    project_id="example_service",
    name="Example Microservice",
    workspace_root=Path("C:/projects/example_service"),
    allowed_remote_url="https://github.com/organization/example-service.git",
    policy_branch="main",
    test_command="python -m pytest",
    git_dry_run_policy=True,
)
```

---

## 2. Checklist Verifikasi Onboarding

Sebelum proyek diizinkan menerima task otomatis:
- [ ] **Workspace Isolation:** Root workspace bukan merupakan root filesystem OS (`/`, `C:\`, `C:\Windows`).
- [ ] **Remote Whitelist:** URL remote berawalan `https://` atau `git@` yang terdaftar resmi.
- [ ] **Branch Protection:** Kebijakan branch disetel ke branch yang diizinkan (default `main` atau `develop`).
- [ ] **Test Command:** Perintah pengujian terdefinisi dan dapat dieksekusi secara lokal.
- [ ] **Zero Credential:** Tidak ada token atau password yang disertakan dalam definisi proyek.
- [ ] **Git Dry-Run Default:** Proyek diawali dengan `git_dry_run_policy = True`.

---

## 3. Pendaftaran via CLI

```bash
kanoman project add \
  --id "service_auth" \
  --name "Authentication Service" \
  --root "C:/projects/service_auth" \
  --remote "https://github.com/org/service_auth.git"
```

Daftar proyek dapat diverifikasi dengan:
```bash
kanoman project list
```
