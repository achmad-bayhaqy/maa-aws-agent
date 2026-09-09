# Riset AgentCore 2026 — Peta Fitur & Strategi Integrasi MAA-AWS-AGENT

> Tanggal riset: 9 September 2026 (sumber: docs.aws.amazon.com, aws.amazon.com/blogs, re:Invent 2025, publikasi Mei–Jul 2026).
> Hasil: strategi integrasi v3.8 "AgentCore 2026 Superpowers".

## 1. Peta fitur AgentCore per September 2026

| Fitur | Apa itu | Status rilis | Arti untuk MAA |
|---|---|---|---|
| **AgentCore Harness** | Assembly agent config-driven, ditenagai **Strands Agents SDK** (open source): orchestration loop, tool execution, memory management otomatis | GA 2026 (preview Mei 2026) | Pola diserap (reflection loop, task_plan, loop budget); runtime custom terbukti E2E, tidak dirombak |
| **Runtime** | MicroVM per sesi, serverless, ANY framework/model, 8 jam sesi | GA | ✅ Dipakai sejak v3 (otak agent) |
| **Gateway** | MCP runtime: target Lambda/OpenAPI/Smithy/MCP, credential provider outbound (API key/OAuth), inbound JWT | GA | ✅ web_search/web_fetch via MCP + SigV4 |
| **Identity** | Workload identity + resource credential provider (a2p auth) | GA | 🔶 Ekivalen di MAA: STS single-use 900s per eksekusi |
| **Memory** | Short-term + long-term (semantic/preference); **episodic memory** ditambah re:Invent Des 2025 | GA | ✅ Native + v3.8 episodic (goal→outcome→score) |
| **Policy** | Intercept SETIAP tool call via Gateway real-time; batas tool/parameter; cegah agent "memberikan toko" | **GA Mar 2026** | ✅ **v3.8: policy engine in-process** (read bebas / destruktif → konfirmasi ganda / IAM-Org-Account-Billing read-only) |
| **Evaluations** | Rubrik kualitas (helpfulness, accuracy, task success), online + offline | Preview Des 2025 → GA 2026 | ✅ **v3.8: task_evaluate + auto-evaluasi** (goal_met/correctness/efficiency/safety) |
| **Optimization** | Optimasi otomatis system prompt & tool description dari data Observability | Preview Mei 2026 | ✅ **v3.8: self_improve** — analisis error 24 jam → 3 rekomendasi → KB |
| **Payments** | Agentic commerce: **x402 exact**, **x402 upto**, **MPP (Machine Payments Protocol)** | Preview Mei 2026 | ⏳ Menunggu kebutuhan nyata + penyedia pembayaran |
| **Browser** | Browser cloud sesi terisolasi (CAPTCHA-friendly, IP konsisten) | GA | ✅ web_fetch JS-pages |
| **Code Interpreter** | Sandbox kode + internet + matplotlib | GA | ✅ Native |
| **Observability** | Trace/Session metrics dashboards, integrasi CloudWatch | GA | ✅ Live Trace custom + CW |

## 2. Keputusan desain v3.8

1. **Jangan rombak ke Harness/Strands** — runtime custom sudah terbukti 7 round E2E; pola kognisi Strands (reflection, plan-act-verify) diserap lewat prompt + loop budget.
2. **`aws_api` generic tool** = jawaban untuk "bisa melakukan apapun": satu tool membuka ribuan operasi AWS, dengan **policy engine** sebagai rem (AgentCore Policy pattern): read-only bebas, destruktif dipaksa konfirmasi ganda manusia, service identitas/billing read-only. Subagent dibatasi `confirmed=False` sehingga destruktif via subagent mustahil.
3. **Self-evaluasi + self-improvement** membuat agent membaik sendiri: evaluasi rubrik tiap tugas berat (async, tak memperlambat jawaban), episode disimpan ke Memory; error 24 jam dianalisis → rekomendasi → KB (dokumen `self-improvement ...`).
4. **Episodic memory**: `[EPISODE] goal/outcome/score` — sesi berikutnya bisa mengalirkan pengalaman, bukan cuma fakta.
5. **IAM runtime** ditambah `logs:FilterLogEvents` + `logs:GetLogEvents` (read-only) agar self_improve bisa membaca trace sendiri.

## 3. Bukti (E2E 9 Sep 2026, API produksi)

- T1 read: `aws_api ec2 describe_instances` → 2 instance nyata tampil.
- T2 deny: `aws_api iam create_role` → policy DENY + penjelasan elegan ke user.
- T3 confirm: `aws_api ec2 terminate_instances` → confirmation_required (layar konfirmasi ganda; tanpa eksekusi).
- T4 self_improve → pola error 24 jam + 3 rekomendasi → tersimpan ke Knowledge Base.
- Runtime: `maa_agent_runtime-SETSK2FPE4` (v3.8), edge `maa-agent-edge` re-pointed.

## 4. Roadmap lanjutan (opsional)

- Aktifkan **AgentCore Policy native** via Gateway bila migrasi tool call ke Gateway penuh.
- **Evaluations native** (evaluator bawaan AWS) utk benchmark antar-versi agent.
- **Payments** (x402/MPP) saat ada use case commerce.
- Migrasi bertahap komponen ke **Harness** bila butuh multi-agent framework standar.
