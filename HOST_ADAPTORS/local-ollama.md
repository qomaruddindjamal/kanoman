# HOST ADAPTOR: LOCAL OLLAMA (AIR-GAPPED RUNTIME)

> **Host Environment:** On-Premise Air-Gapped Server / Local Workstation  
> **Target Runtime:** Ollama (`ollama run`)  
> **Model Disarankan:** Qwen 2.5 Coder 32B / Llama 3.3 70B / DeepSeek-Coder  

---

## 1. Pembuatan Modelfile
Buat file `Modelfile` di direktori lokal:

```dockerfile
FROM qwen2.5-coder:32b
SYSTEM """
$(Get-Content C:\kanoman\BOOT\KANOMAN_SYSTEM_PROMPT.md -Raw)
"""
PARAMETER temperature 0.2
PARAMETER top_p 0.95
```

## 2. Pembangunan & Menjalankan Model
```powershell
ollama create kanoman -f Modelfile
ollama run kanoman
```
