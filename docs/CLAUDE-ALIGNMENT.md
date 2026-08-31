# MAA AWS Agent × Claude AI — Alignmen Fitur & Kapabilitas (per 31 Agustus 2026)

> Hasil riset keseluruhan fitur Claude AI (claude.ai + Claude Code + API Agent Skills)
> sampai 31 Agustus 2026, dipetakan ke implementasi MAA AWS Agent v3.5 — dengan
> adaptasi positif dari Gemini, ChatGPT, dan chat.z.ai. Sumber riset: web-search
> live (support.claude.com, anthropics/skills, best-practice roundup 2026).

## 1. Matriks Alignmen

| # | Fitur Claude AI (2026) | Status MAA v3.5 | Implementasi MAA (100% AWS native) |
|---|------------------------|-----------------|-------------------------------------|
| 1 | **Agent Skills** (SKILL.md, progressive disclosure, skill-creator) | ✅ v3.5 | Skills Library S3 `skills/<slug>/SKILL.md`; tool `skills_list` / `skills_use` / `skills_save`; UI drawer; seed 100+ skill resmi Anthropic + AWS |
| 2 | **Artifacts** (live preview dokumen/kode) | ✅ sejak v3.4 | Kartu artefak deck HTML + web app (SPA) + gambar, URL publik permanen v3.4.3 |
| 3 | **Projects** (context per-proyek, knowledge) | ✅ sejak v3.3 | Knowledge Base (S3 Vectors) + Dokumentasi site + sesi persistent URL `/c/<id>` |
| 4 | **Memory** (memori lintas sesi) | ✅ sejak v3.3 | AgentCore Memory + recall otomatis di-inject ke prompt |
| 5 | **Web search & research** (berita terkini, sitasi) | ✅ sejak v3.3 | AgentCore Gateway MCP `web_search` + `web_fetch`; model selalu diarahkan jawab terkini |
| 6 | **Analysis tool / code interpreter** (Python, chart) | ✅ +upgrade v3.5 | AgentCore Code Interpreter **networkMode INTERNET** — scraping web & pip install kini aktif |
| 7 | **Image generation & vision** | ✅ sejak v3.4 | Nova Canvas (generate) + lampiran gambar → vision fallback Nova Lite |
| 8 | **File upload & analysis** (PDF/CSV/XLSX) | ✅ sejak v3.4 | presign 200 MB, pypdf/inline budget 60k, CSV/JSON dibaca konteks |
| 9 | **Multi-agent / subagents** (researcher, analyst, coder, reviewer, ops) | ✅ sejak v3.4 | `subagent_run` 6 peran spesialis, loop 5 iter, tool subset aman |
| 10 | **Todo / task planning live** | ✅ sejak v3.4 | `task_plan` → DDB attr → TodoPanel progress bar |
| 11 | **Extended thinking** (mode pikir panjang) | ✅ sejak v3.3 | mode DEEP (budget thinking besar) + LONG (24 iter, 16k token) |
| 12 | **Adaptive model routing** (auto/fast/deep) | ✅ sejak v3.4.2 | mode AUTO/FAST/DEEP/MANUAL + katalog 88 model + agent mode terpisah |
| 13 | **Guardrails & safe autonomy** | ✅+ | Bedrock Guardrail + **konfirmasi destruktif 2 tahap** (lebih ketat dari Claude) + superadmin bypass teraudit |
| 14 | **Live trace / observability** | ✅+ (lebih dari Claude) | Live Trace panel per event (thinking/tool/kb/web/ci/image), CloudWatch `/maa/agent/trace` |
| 15 | **Management user & RBAC** | ✅+ v3.5 | Menu **Management User**: undang (email/instan), enable/disable, **rename**, **ganti role user↔superadmin**, hapus, global sign-out |
| 16 | **KB CRUD dari percakapan** ("buka/ubah/hapus dokumen") | ✅ v3.5 | `kb_list_docs` / `kb_read_doc` / `kb_edit_doc` / `kb_delete_doc` + re-index otomatis + editor di UI |
| 17 | **Canvas / design** (canvas-design, theme-factory) | ✅ v3.5 via skills | skill `anthropic-canvas-design`, `anthropic-theme-factory`, `anthropic-frontend-design` ter-seed |
| 18 | **Office documents** (docx/pptx/xlsx/pdf create-edit) | ✅ v3.5 via skills | skill `anthropic-docx`, `anthropic-pptx`, `anthropic-xlsx`, `anthropic-pdf` ter-seed (panduan eksekusi ahli) |
| 19 | **MCP integrations** | ✅ sejak v3.3 | AgentCore Gateway = MCP server (webtools target); skill `anthropic-mcp-builder` untuk integrasi lanjutan |
| 20 | **Skills marketplace / custom skills** | ✅+ v3.5 | User/agent bisa `skills_save` — skill baru tersimpan permanen & langsung muncul (Claude Code skill-creator pattern) |

## 2. Adaptasi dari Platform Lain

| Platform | Fitur yang diadaptasi | Di MAA |
|----------|----------------------|--------|
| **chat.z.ai** | Live Trace transparency (visibilitas proses agent real-time) | Trace rail + drawer mobile, 14 tipe event berwarna |
| **Gemini** | Katalog model luas + grounding search | 88 model MANUAL dropdown + web grounding via Gateway |
| **ChatGPT** | Memory ringkas lintas sesi + GPT-style task modes | AgentCore Memory + 6 agent mode (STANDARD/LONG/FULLSTACK/PRESENTATION/TODO/MULTI) |
| **Claude** | Agent Skills, Artifacts, Projects, analysis tool | 100% terimplementasi (lihat matriks) — plus KB CRUD yang Claude tidak punya |

## 3. Yang Lebih Canggih dari Claude (sudah ada di MAA)

1. **Cloud autonomy penuh** — MAA benar-benar mengeksekusi operasi AWS (EC2/EKS/RDS/S3/VPC/Lambda/DynamoDB/CloudFormation) dengan protokol konfirmasi 2 tahap; Claude hanya menyarankan.
2. **Self-healing IaC** — `iac_generate` memvalidasi CloudFormation, membaca error, memperbaiki sendiri, lalu deploy ulang.
3. **Skills yang bertumbuh sendiri** — agent menyimpan pola kerja baru via `skills_save` (organizational memory; Claude Code punya skill-creator, MAA membawanya ke chat web).
4. **Audit & observability enterprise** — CloudTrail, CloudWatch trace group, evaluator LLM-as-judge per sesi, WAF rate-limit.
5. **KB yang bisa dikelola lewat percakapan** — "buka/update/hapus dokumen X" langsung dieksekusi dengan re-index otomatis.

## 4. Skills Library (feedback #8 — "ingatan" agent)

Di-download & di-seed ke `s3://{ART_BUCKET}/skills/` (dibaca agent via progressive disclosure):

| Sumber | Jumlah | Contoh |
|--------|--------|--------|
| anthropics/skills (resmi Anthropic) | 19 | docx, pptx, xlsx, pdf, web-artifacts-builder, frontend-design, canvas-design, mcp-builder, skill-creator, webapp-testing, theme-factory |
| aws-samples/sample-agent-skills-for-builders | 15 | panduan builder AWS |
| aws-samples/sample-aws-solutions-skills | 8 | solusi arsitektur AWS |
| aws-samples/sample-well-architected-skills-and-steering | 6 | Well-Architected review |
| aws-samples/sample-aws-ops-skills-for-agents | 10 | operasi AWS (ops/monitoring) |
| awslabs/agent-plugins | 34 | plugin agent AWS Labs |
| aws-samples/sample-skills-for-AWS-Devops-agent | 12 | DevOps AWS |
| **Total** | **104** | + katalog `_catalog.md` di KB untuk RAG |

Mekanisme: `skills_list` hanya menampilkan nama+deskripsi (hemat konteks) → `skills_use` memuat isi SKILL.md saat tugas cocok → `skills_save` menambah skill baru. Katalog lengkap juga diunggah ke KB (`docs/agent/katalog-skill-library.md`) agar bisa ditemukan via `kb_search`.

## 5. Rencana Lanjutan (Roadmap v3.6+)

- Computer-use style browser automation via AgentCore Browser Tool (saat tersedia GA di region).
- Connector directory ala Claude (Google Drive/Slack) via Gateway target tambahan.
- Skill packages multi-file (script pendukung + resources) — format sudah kompatibel, tinggal vendor loader.
