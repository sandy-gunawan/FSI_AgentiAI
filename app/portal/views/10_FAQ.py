"""FAQ & Referensi — agentic AI, multi-agent, MCP, A2A, Microsoft Agent Framework.

Halaman edukasi statis (tanpa LLM): tanya-jawab dari pemula sampai pakar,
matriks keputusan, perbandingan MCP vs A2A, perbandingan framework, cara
menghubungkan (kode contoh), skenario FSI, dan peta 8 use case di app ini.
"""
from __future__ import annotations

import streamlit as st

from app.observability.otel_setup import setup_observability

setup_observability()

st.title("📖 FAQ & Referensi — Agentic AI, Multi-Agent, MCP & A2A")
st.caption("Dari pertanyaan pemula sampai pakar · protokol · framework · arsitektur · migrasi · matriks keputusan")

# --------------------------------------------------------------------------- #
# Q&A knowledge base (level, icon, question, answer-markdown)
# --------------------------------------------------------------------------- #
LEVELS = ["Pemula", "Menengah", "Lanjutan", "Pakar"]
LVL_ICON = {"Pemula": "🟢", "Menengah": "🟡", "Lanjutan": "🟠", "Pakar": "🔴"}

ENTRIES: list[dict] = [
    # ---------------- PEMULA — konsep dasar ----------------
    {"level": "Pemula", "q": "Apa itu AI agent? Apa bedanya dengan chatbot atau LLM biasa?",
     "a": "**LLM** = model bahasa yang menghasilkan teks. **Chatbot** = antarmuka tanya-jawab di atas LLM. "
          "**AI agent** = LLM yang diberi **tujuan**, bisa **menalar (reason)**, **memakai tool/API (act)**, "
          "**mengamati hasil (observe)**, lalu mengulang sampai tujuan tercapai.\n\n"
          "> Chatbot menjawab; agent **bertindak** (memanggil sistem, mengambil keputusan multi-langkah)."},
    {"level": "Pemula", "q": "Apa itu Agentic AI?",
     "a": "Sistem AI yang **otonom mengambil keputusan & tindakan multi-langkah** untuk menyelesaikan tugas — "
          "biasanya menggunakan **tools**, **memory**, **planning**, dan loop *reason → act → observe*. "
          "Bukan sekadar satu prompt→satu jawaban."},
    {"level": "Pemula", "q": "Apa itu sistem multi-agent (multi-agent system)?",
     "a": "Beberapa **agen spesialis** yang bekerja sama untuk tugas kompleks — bisa **berurutan** (pipeline), "
          "**paralel** (concurrent), **berdebat** (group chat), **delegasi** (handoff), atau dikoordinasi "
          "**manajer** (magentic). Lihat 8 use case di app ini sebagai contoh nyata."},
    {"level": "Pemula", "q": "Apa itu 'tool' / function calling pada agen?",
     "a": "Kemampuan agen **memanggil fungsi/API eksternal** (mis. `get_account_summary`, `screen_individual`). "
          "Model menghasilkan permintaan terstruktur (nama fungsi + argumen), aplikasi menjalankannya, lalu "
          "hasilnya dikembalikan ke model. Inilah cara agen 'menyentuh' dunia nyata."},
    {"level": "Pemula", "q": "Apa itu orkestrasi agen?",
     "a": "Pola **bagaimana banyak agen dikoordinasikan**: urutan, paralel, delegasi dinamis, debat, atau "
          "manajer + rencana. Microsoft Agent Framework punya 5 orkestrasi resmi: **Sequential, Concurrent, "
          "Handoff, Group Chat, Magentic**."},
    {"level": "Pemula", "q": "Apa itu human-in-the-loop (HITL)?",
     "a": "**Gerbang persetujuan manusia** sebelum tindakan berisiko dieksekusi — mis. petugas kredit menyetujui "
          "term sheet UKM, atau analis AML mengonfirmasi pelaporan SAR. Penting untuk kepatuhan & akuntabilitas."},
    {"level": "Pemula", "q": "Apa itu governance dalam agentic AI?",
     "a": "Kontrol agar agen aman & auditable: **audit log** tiap langkah, **budget token/biaya**, **redaksi "
          "PII**, **content safety**, **policy engine deterministik** (bukan LLM untuk keputusan regulatif), dan "
          "**human gate**. App ini menerapkan semuanya (lihat halaman *Audit & Governance*)."},
    {"level": "Pemula", "q": "Apakah agent selalu memakai LLM di setiap langkah?",
     "a": "Tidak. Praktik yang baik: **keputusan regulatif/hitungan** dibuat **deterministik** (rules engine, "
          "policy OJK/BI) agar reproducible & auditable; **LLM** dipakai untuk menalar data & menulis penjelasan. "
          "Di app ini, compliance/affordability = deterministik; intake/analisis/penjelasan = LLM."},

    # ---------------- PROTOKOL — MCP & A2A ----------------
    {"level": "Pemula", "q": "Apa itu 'protokol' dalam konteks agen, dan kenapa perlu?",
     "a": "Protokol = **standar komunikasi** agar komponen/agen dari sistem, vendor, atau organisasi berbeda "
          "bisa saling bicara **tanpa integrasi bespoke** untuk tiap pasangan. Dua yang utama: **MCP** (agen→tool) "
          "dan **A2A** (agen→agen)."},
    {"level": "Pemula", "q": "Apa itu MCP (Model Context Protocol)?",
     "a": "Protokol terbuka (dari **Anthropic**, 2024) untuk menghubungkan aplikasi LLM/agen ke **tools, data, "
          "dan resources**. Ibarat **'USB-C untuk tools AI'**. Di app ini: **Credit Bureau**, **KYC/AML**, dan "
          "**Policy Rules** di-expose sebagai server MCP."},
    {"level": "Pemula", "q": "Apa itu A2A (Agent2Agent)?",
     "a": "Protokol terbuka (dimulai **Google**, kini di bawah **Linux Foundation**; didukung Microsoft, Google, "
          "dan 50+ mitra) agar **agen berbicara ke agen lain** yang dimiliki/di-deploy pihak berbeda. Di app ini: "
          "use case **Sindikasi** (BNS ↔ Bank Mitra Sejahtera)."},
    {"level": "Pemula", "q": "MCP vs A2A — apa beda mendasarnya?",
     "a": "| | MCP | A2A |\n|---|---|---|\n| Menghubungkan | agen → **tool/data** | agen → **agen lain** |\n"
          "| Sumbu | vertikal | horizontal |\n| Analogi | USB-C untuk tools | telepon antar-agen |\n\n"
          "**Komplementer**, bukan saling menggantikan. Satu agen bisa pakai MCP untuk tools **dan** A2A untuk "
          "berdelegasi ke agen lain."},
    {"level": "Menengah", "q": "Bagaimana cara kerja MCP secara teknis?",
     "a": "Server MCP meng-expose **tools**, **resources**, dan **prompts**. Klien (agen) terhubung via "
          "**stdio** (lokal) atau **Streamable HTTP/SSE** (remote). Model memilih tool; klien menjalankan lalu "
          "mengembalikan hasil. Di app ini kami pakai `MCPStreamableHTTPTool` dari Agent Framework."},
    {"level": "Menengah", "q": "Bagaimana cara kerja A2A secara teknis?",
     "a": "1) Agen server menerbitkan **Agent Card** di `/.well-known/agent-card.json`.\n"
          "2) Klien **menemukan** card (discovery).\n"
          "3) Klien mengirim tugas via **JSON-RPC 2.0 `message/send`** (atau `message/stream` untuk SSE).\n"
          "4) Server memproses (punya **task lifecycle**), membalas **Message/Task**.\n"
          "5) Opsional: **streaming** progres (SSE) & **push notification** (webhook) untuk tugas async."},
    {"level": "Menengah", "q": "Apa itu Agent Card dan apa isinya?",
     "a": "Kartu identitas agen (JSON) di path well-known. Isinya a.l.: `name`, `description`, `version`, "
          "`protocolVersion`, `url` (endpoint), `preferredTransport`, `capabilities` (streaming, push), "
          "`defaultInputModes/OutputModes`, `skills[]` (id, name, tags, examples), `provider`, dan "
          "`securitySchemes`. Klien memakainya untuk tahu **apa yang bisa dilakukan agen & cara memanggilnya**."},
    {"level": "Menengah", "q": "Transport & method apa yang dipakai A2A?",
     "a": "**Transport:** JSON-RPC 2.0 (HTTP), gRPC, dan HTTP+JSON/REST; streaming via **SSE**.\n\n"
          "**Method inti:** `message/send`, `message/stream`, `tasks/get`, `tasks/cancel`, "
          "`tasks/pushNotificationConfig/set|get|list`, `agent/getAuthenticatedExtendedCard`."},
    {"level": "Menengah", "q": "Apa itu 'task lifecycle' di A2A?",
     "a": "Sebuah task melewati status: **submitted → working → (input-required) → completed** — atau berakhir "
          "**failed / canceled / rejected / auth-required**. Ini yang membuat A2A cocok untuk tugas "
          "**long-running & human-gated** lintas layanan (task bisa dipantau/di-resume)."},
    {"level": "Pemula", "q": "Apakah A2A menggantikan MCP?",
     "a": "**Tidak.** Keduanya **komplementer**. Pola umum: agen pakai **MCP** untuk mengambil data/menjalankan "
          "tool internal, dan **A2A** untuk mendelegasikan sub-tugas ke agen lain (tim/vendor/organisasi berbeda)."},

    # ---------------- MICROSOFT AGENT FRAMEWORK ----------------
    {"level": "Pemula", "q": "Apa itu Microsoft Agent Framework?",
     "a": "SDK **open-source** (Python & .NET) untuk membangun **agen & workflow** produksi. Menyatukan "
          "**Semantic Kernel** (enterprise, plugin, stabil) dan **AutoGen** (riset multi-agen) menjadi satu "
          "framework, plus orkestrasi, MCP, A2A, dan observability (OpenTelemetry). App ini dibangun di atasnya."},
    {"level": "Menengah", "q": "Apa hubungan Agent Framework dengan Semantic Kernel & AutoGen?",
     "a": "Microsoft Agent Framework adalah **penerus/penyatuan** keduanya: mengambil kematangan enterprise "
          "**Semantic Kernel** + inovasi orkestrasi multi-agen **AutoGen** (mis. **Magentic-One**). Kode lama "
          "SK/AutoGen bermigrasi ke API terpadu MAF."},
    {"level": "Menengah", "q": "Apa 5 orkestrasi resmi Microsoft Agent Framework?",
     "a": "| Orkestrasi | Untuk | Contoh di app |\n|---|---|---|\n"
          "| **Sequential** | pipeline linear | Kredit Ritel |\n"
          "| **Concurrent** | tugas paralel independen | Pembiayaan UKM |\n"
          "| **Handoff** | delegasi dinamis antar-agen | Layanan Nasabah (versi routing) |\n"
          "| **Group Chat** | debat/kolaborasi termoderasi | Komite Kredit |\n"
          "| **Magentic** | tugas open-ended + manajer/ledger | Investigasi Kompleks |"},
    {"level": "Pemula", "q": "Apa itu Microsoft Foundry dan hubungannya dengan Agent Framework?",
     "a": "**Microsoft Foundry** = platform Azure untuk **model** (mis. gpt-4o-mini) + **agent service** "
          "(hosting, deploy, evaluasi, fine-tune). **Agent Framework** = SDK untuk *menulis* agen; **Foundry** = "
          "tempat *menjalankan model* & meng-*host*/mengelola agen. App ini: MAF (kode) + model di Foundry."},
    {"level": "Menengah", "q": "Bagaimana Agent Framework mendukung MCP dan A2A?",
     "a": "- **MCP (klien):** `MCPStreamableHTTPTool(name=..., url=...)` → agen memakai tool MCP remote.\n"
          "- **A2A (klien):** `A2AAgent(name=..., url=<agent-card-url>)` → panggil agen remote seperti sub-agen.\n"
          "- **A2A (server):** `A2AExecutor(agent)` + handler/routes A2A → expose agen MAF sebagai server A2A.\n\n"
          "*(App ini memakai klien MCP untuk sistem sekitar, dan A2A untuk delegasi ke bank mitra.)*"},

    # ---------------- KAPAN PAKAI APA ----------------
    {"level": "Menengah", "q": "Kapan pakai A2A vs orkestrasi in-process?",
     "a": "**Pakai A2A** bila agen: **di-deploy terpisah**, **dimiliki tim/vendor/organisasi berbeda**, perlu "
          "**interop lintas-framework** (mis. mitra pakai LangGraph), atau **delegasi lintas-institusi**.\n\n"
          "**Pakai orkestrasi in-process** (Sequential/Concurrent/Handoff/Group Chat/Magentic) bila agen **satu "
          "tim, satu framework, satu proses** — lebih cepat, sederhana, mudah diaudit."},
    {"level": "Menengah", "q": "Kapan JANGAN pakai A2A (anti-pattern)?",
     "a": "- Agen **satu proses/tim** → orkestrasi in-process saja.\n"
          "- **Latensi kritis** → hop jaringan A2A menambah delay.\n"
          "- Anda hanya butuh **data/tool**, bukan agen lain → pakai **MCP**.\n"
          "- Tugas **sederhana/deterministik** → cukup fungsi biasa.\n\n"
          "Menambel A2A di sini hanya menambah kompleksitas jaringan/keamanan tanpa manfaat."},
    {"level": "Menengah", "q": "MCP atau A2A untuk kebutuhan saya?",
     "a": "Tanya: **apa yang di ujung sana?**\n"
          "- **Tool/data/sistem** (DB, API, file) → **MCP**.\n"
          "- **Agen lain** yang menalar & punya skill sendiri → **A2A**.\n\n"
          "Sering **keduanya**: agen Anda pakai MCP untuk data, lalu A2A untuk berdelegasi."},
    {"level": "Lanjutan", "q": "A2A vs REST/gRPC integrasi biasa — kenapa A2A?",
     "a": "REST bespoke butuh kontrak khusus tiap integrasi. **A2A menstandardkan**: **discovery** (Agent Card), "
          "**task lifecycle**, **streaming/push**, **modality** (text/data/file), dan **opaqueness** (agen tak "
          "berbagi internal). Untuk **agen↔agen lintas-org**, A2A mengurangi integrasi point-to-point yang rapuh. "
          "Untuk API biasa non-agentic, REST/MCP tetap lebih tepat."},
    {"level": "Lanjutan", "q": "A2A vs message queue (Kafka/Service Bus)?",
     "a": "**Queue** = event/streaming **async, decoupled, fire-and-forget** (fan-out, buffering). **A2A** = "
          "**delegasi tugas** request/response (atau streaming) antar agen dengan **semantik agentic** (task "
          "lifecycle, human-in-loop). Sering dipadu: A2A untuk delegasi, queue untuk event backbone."},

    # ---------------- ARSITEKTUR & DESAIN ----------------
    {"level": "Lanjutan", "q": "Bagaimana keamanan & autentikasi di A2A?",
     "a": "- Agent Card mendeklarasikan **`securitySchemes`** (OAuth 2.0, OIDC, API key, mTLS) & requirement per-skill.\n"
          "- **TLS** wajib untuk transport publik.\n"
          "- **Token exchange / OBO** untuk memanggil atas nama pengguna lintas-tenant.\n"
          "- **Microsoft Entra Agent ID** memberi agen **identitas terkelola** + federasi kredensial.\n"
          "- Praktik: **allowlist** Agent Card tepercaya, verifikasi signature card, DLP/PII, audit lintas-org."},
    {"level": "Lanjutan", "q": "Bagaimana A2A menangani tugas long-running, streaming, & async?",
     "a": "- **Streaming progres:** `message/stream` (Server-Sent Events) mengirim `TaskStatusUpdateEvent` / "
          "`TaskArtifactUpdateEvent`.\n"
          "- **Async/putus-sambung:** **push notifications** (webhook) memberi tahu klien saat task selesai.\n"
          "- **Resume:** server menyimpan task (**TaskStore**), klien `tasks/get` untuk polling status."},
    {"level": "Lanjutan", "q": "Bagaimana observability lintas-agen (termasuk lintas A2A)?",
     "a": "Propagasi **trace context W3C** melewati panggilan A2A/MCP sehingga satu request punya **satu trace** "
          "end-to-end. Agent Framework mengeluarkan **OpenTelemetry** (spans GenAI, token, latency) → **Azure "
          "Application Insights** / Aspire. App ini sudah OTel-instrumented."},
    {"level": "Lanjutan", "q": "Bagaimana error handling & ketahanan lintas-organisasi?",
     "a": "- **JSON-RPC error codes** + task state `failed`.\n"
          "- **Retry idempoten** (pakai id task), **timeout**, **circuit breaker**, **fallback** (mis. cari mitra lain).\n"
          "- **Degradasi anggun**: bila mitra A2A tak menjawab, lanjut dengan porsi sendiri + tandai shortfall "
          "(persis yang dilakukan use case Sindikasi)."},
    {"level": "Lanjutan", "q": "Bagaimana versioning Agent Card & kompatibilitas?",
     "a": "Card punya `version` (agen) & `protocolVersion` (A2A). Praktik: **tambah skill** (jangan hapus), "
          "**negosiasi capability** dari card, dan sediakan **extended card** untuk klien terautentikasi. Klien "
          "harus toleran terhadap field baru."},
    {"level": "Lanjutan", "q": "Apa itu Microsoft Entra Agent ID dan kenapa penting?",
     "a": "Memberi **agen** (bukan hanya manusia/app) **identitas terkelola** di Entra ID: OAuth 2.0, token "
          "exchange (fmi_path/OBO), Workload Identity Federation lintas-tenant. Penting untuk **A2A lintas-org** "
          "agar tiap agen bisa diautentikasi & diberi least-privilege access secara auditable."},
    {"level": "Lanjutan", "q": "Seperti apa arsitektur multi-agent production-grade?",
     "a": "Lapisan yang perlu ada:\n"
          "1. **Model** (Foundry) + **agents/workflows** (Agent Framework).\n"
          "2. **Tools/data** via **MCP**; **agen eksternal** via **A2A**.\n"
          "3. **AI Gateway** (mis. Azure APIM) untuk auth, rate-limit, token metrics, content safety.\n"
          "4. **Governance**: audit, cost budget, PII, policy deterministik, human gates.\n"
          "5. **Observability**: OpenTelemetry → App Insights.\n"
          "6. **Identity**: Entra Agent ID. *(App ini mencontohkan 1, 2, 4, 5.)*"},

    # ---------------- INTEROP & MIGRASI (PAKAR) ----------------
    {"level": "Pakar", "q": "Bagaimana Agent Framework berinteroperasi dengan LangGraph / CrewAI / Google ADK?",
     "a": "Lewat **A2A**: bungkus tiap agen (MAF, LangGraph, CrewAI, Google ADK, OpenAI Agents SDK) sebagai "
          "**server A2A** dengan **Agent Card**, lalu panggil dari sisi lain dengan **klien A2A** "
          "(`A2AAgent`). Tidak perlu berbagi SDK/bahasa — A2A adalah **lingua franca** antar-framework. "
          "Untuk **tool**, gunakan **MCP** sebagai standar bersama."},
    {"level": "Pakar", "q": "Bagaimana migrasi dari orkestrasi in-process (Agent Framework) ke A2A?",
     "a": "Langkah bertahap:\n"
          "1. **Identifikasi** agen yang perlu jadi layanan mandiri (dipakai ulang / lintas-org / lintas-tim).\n"
          "2. **Bungkus** agen dengan `A2AExecutor` + **Agent Card** (skills, security).\n"
          "3. **Deploy terpisah** (mis. Container App sendiri) + identitas (Entra Agent ID).\n"
          "4. **Ganti** pemanggilan lokal menjadi klien **`A2AAgent(url=...)`**.\n"
          "5. Tambah **auth, observability, retry, versioning**.\n"
          "6. **Contract test** terhadap skema Agent Card sebelum go-live.\n\n"
          "*Yang tetap in-process (satu tim/proses) tidak perlu dimigrasi.*"},
    {"level": "Pakar", "q": "Bagaimana meng-expose agen Agent Framework yang ada sebagai server A2A?",
     "a": "Konsep (Python):\n```python\nfrom agent_framework.a2a import A2AExecutor\n# agent = ChatAgent(...) milik Anda\n"
          "executor = A2AExecutor(agent)\n# + DefaultRequestHandler + routes A2A + AgentCard, lalu host via ASGI\n```\n"
          "Executor menangani konversi **A2A message ⇄ agent run** (termasuk streaming). Sediakan Agent Card di "
          "well-known path. *(Di app ini, agen mitra sengaja rule-based & tanpa kredensial untuk demonstrasi.)*"},
    {"level": "Pakar", "q": "Bagaimana mengonsumsi agen A2A eksternal dari Agent Framework?",
     "a": "```python\nfrom agent_framework.a2a import A2AAgent\npartner = A2AAgent(name='partner', url=CARD_URL)\n"
          "resp = await partner.run('…deal summary…')\n```\n"
          "`A2AAgent` mengambil Agent Card, mengirim `message/send`, dan mengembalikan balasan — bisa "
          "diperlakukan sebagai **sub-agen/tool** di dalam orkestrasi Anda."},
    {"level": "Pakar", "q": "Bagaimana mengombinasikan A2A + MCP dalam satu arsitektur enterprise?",
     "a": "- **MCP** untuk tool/data internal tiap domain (core banking, bureau, KYC).\n"
          "- **A2A** untuk delegasi **antar domain/organisasi** (mis. sindikasi antar bank).\n"
          "- **AI Gateway (APIM)** di depan keduanya untuk **auth, rate-limit, token metrics, content safety, "
          "logging** terpusat.\n"
          "- **Entra Agent ID** untuk identitas agen. Pola: *MCP di dalam domain, A2A antar domain.*"},
    {"level": "Pakar", "q": "Bagaimana menangani trust & keamanan A2A lintas-organisasi (multi-tenant)?",
     "a": "- **mTLS / OAuth2 / OIDC**, verifikasi **signature** Agent Card.\n"
          "- **Allowlist** partner tepercaya; **least-privilege** per-skill.\n"
          "- **Contract testing** & **schema validation** payload.\n"
          "- **DLP/PII redaction**, **audit lintas-org**, **rate limiting**, **SLA & fallback**.\n"
          "- Jangan pernah mengirim data lebih dari yang diperlukan skill (minimal disclosure)."},
    {"level": "Pakar", "q": "Bagaimana testing & mocking agen A2A?",
     "a": "- **Mock server** dengan **Agent Card statis** + logika deterministik (persis agen mitra di app ini) "
          "untuk uji end-to-end tanpa biaya LLM.\n"
          "- **Contract tests** terhadap skema Agent Card & envelope JSON-RPC.\n"
          "- **Replay** envelope nyata; uji jalur error (timeout, decline, partial).\n"
          "- Validasi **discovery** (well-known path) & **redirect/HTTPS** (hati-hati 301 http→https pada POST)."},
    {"level": "Pakar", "q": "Kapan A2A menjadi 'overkill'?",
     "a": "Saat agen berada di **satu runtime/tim**, tugas **sinkron & sederhana**, atau ketika kebutuhan "
          "sebenarnya hanyalah **tool** (pakai MCP). A2A menambah **hop jaringan, auth, serialization, dan mode "
          "kegagalan baru** — hanya berharga jika ada **batas layanan/organisasi** yang nyata."},
    {"level": "Pakar", "q": "Apa peran AI Gateway (Azure API Management) untuk MCP/A2A?",
     "a": "APIM sebagai **gateway AI**: **autentikasi**, **rate/token limit**, **semantic caching**, **content "
          "safety/jailbreak detection**, **load balancing** model, **token metrics/biaya**, dan **audit** — "
          "diterapkan seragam di depan endpoint **MCP** maupun **A2A**. Cocok untuk governance skala enterprise."},
]

# --------------------------------------------------------------------------- #
# Reference tables
# --------------------------------------------------------------------------- #
MCP_VS_A2A = """
### MCP vs A2A — perbandingan lengkap

| Aspek | **MCP** (Model Context Protocol) | **A2A** (Agent2Agent) |
|---|---|---|
| Menghubungkan | Agen → **tool / data / resource** | Agen → **agen lain** |
| Sumbu | **Vertikal** (agen ke bawah ke sistem) | **Horizontal** (agen ke samping ke agen) |
| Pencetus | Anthropic (2024) | Google → **Linux Foundation** (2025) |
| Analogi | "USB-C untuk tools AI" | "Telepon/kontrak antar-agen" |
| Unit | tools, resources, prompts | tasks, messages, artifacts |
| Discovery | daftar tool dari server | **Agent Card** (`/.well-known/agent-card.json`) |
| Transport | stdio, Streamable HTTP (SSE) | JSON-RPC 2.0 / gRPC / HTTP+JSON, SSE |
| Streaming | ya (SSE) | ya (SSE) + **push notifications** |
| State | umumnya stateless | **task lifecycle** (submitted→working→completed…) |
| Keopakan | tool transparan (skema diketahui) | agen **opaque** (tak berbagi internal) |
| Kapan | butuh **data/tool** | butuh **delegasi ke agen** lain (lintas tim/vendor/org) |
| Di app ini | Credit Bureau, KYC/AML, Policy | Sindikasi (BNS ↔ Bank Mitra) |

> **Komplementer.** Pola umum: **MCP di dalam domain**, **A2A antar domain/organisasi**.
"""

PROTOCOL_MATRIX = """
### Matriks pemilihan: REST vs MCP vs A2A vs Message Queue

| Kebutuhan | REST/gRPC | **MCP** | **A2A** | Queue (Kafka/Service Bus) |
|---|:---:|:---:|:---:|:---:|
| Panggil API/data biasa | ✅ | ➖ | ➖ | ➖ |
| Agen memakai tool secara standar | ➖ | ✅ | ➖ | ➖ |
| Delegasi tugas **agen→agen** | ➖ | ➖ | ✅ | ➖ |
| Lintas **vendor/framework** agen | ➖ | ➖ | ✅ | ➖ |
| Discovery kemampuan (Agent Card) | ➖ | ➖ | ✅ | ➖ |
| Event async / decoupling / fan-out | ➖ | ➖ | ➖ | ✅ |
| Task lifecycle + human-in-loop | ➖ | ➖ | ✅ | ➖ |
| Latensi paling rendah (in-proc) | in-process call | ➖ | ➖ | ➖ |
"""

ORCH_MATRIX = """
### Matriks pemilihan orkestrasi (Microsoft Agent Framework + pola workflow)

| Karakteristik tugas | Pola yang cocok | Resmi MS? |
|---|---|:---:|
| Langkah **linear & wajib berurutan** | **Sequential** (prompt chaining) | ✅ |
| Beberapa analisis **independen, paralel** | **Concurrent** (orchestrator-workers) | ✅ |
| Perlu **klasifikasi → 1 handler** | **Routing** (≈ Handoff sederhana) | Handoff ✅ |
| **Delegasi dinamis** antar agen (bisa balik) | **Handoff** | ✅ |
| **Debat / konsensus** banyak perspektif | **Group Chat** | ✅ |
| **Open-ended**, perlu manajer + rencana + replan | **Magentic** | ✅ |
| **Kualitas via iterasi** (generate→critique) | **Evaluator–Optimizer** (refleksi) | pola workflow |
| **Investigasi eksploratif**, tool dinamis | **ReAct** (single-agent) | pola workflow |
| Agen **lintas-organisasi / vendor** | **A2A** (bukan orkestrasi in-proc) | protokol |
"""

WHEN_A2A = """
### Checklist: perlu A2A atau tidak?

**Pakai A2A bila menjawab "ya" pada ≥1:**
- Agen tujuan **di-deploy terpisah** (layanan/kontainer lain)?
- Dimiliki **tim / vendor / organisasi berbeda**?
- Dibangun di **framework berbeda** (LangGraph, CrewAI, Google ADK)?
- Perlu **delegasi lintas-institusi** dengan logika tetap **opaque**?
- Tugas **long-running / streaming / human-gated** melewati batas layanan?

**Cukup orkestrasi in-process (tanpa A2A) bila:**
- Semua agen **satu tim, satu framework, satu proses**.
- **Latensi kritis**; hop jaringan tak dapat ditoleransi.
- Kebutuhan sebenarnya hanya **tool/data** → gunakan **MCP**.
"""

FRAMEWORK_TABLE = """
### Perbandingan framework agen (tingkat tinggi — cek dokumentasi resmi untuk detail terbaru)

| Framework | Bahasa | Fokus | MCP | A2A | Catatan |
|---|---|---|:---:|:---:|---|
| **Microsoft Agent Framework** | Python, .NET | Enterprise, Azure/Foundry, orkestrasi + workflow | ✅ | ✅ | Menyatukan Semantic Kernel + AutoGen |
| **Semantic Kernel** | Python, .NET, Java | Plugin/skills, enterprise | ✅ | ✅ | Basis MAF |
| **AutoGen** | Python | Riset multi-agen, Magentic-One | ✅ | ✅ | Bergabung ke MAF |
| **LangGraph** (LangChain) | Python, JS | Workflow graph stateful | ✅ | ✅ | Ekosistem besar |
| **CrewAI** | Python | "Crew" berbasis peran, sederhana | ✅ | ✅ | Cepat dipakai |
| **Google ADK** | Python, Java | Agent Development Kit | ✅ | ✅ (native) | Kuat di A2A |
| **OpenAI Agents SDK** | Python | Ringan, handoffs | ✅ | ✅ | Minimalis |

> **Interop:** framework berbeda **berbicara via A2A** (agen↔agen) dan **berbagi tool via MCP** (agen↔tool).
"""

FSI_SCENARIOS = """
### Skenario A2A di FSI (Financial Services) — kapan agen perlu bicara ke agen lain

| Skenario | Agen A | Agen B (remote) | Kenapa A2A |
|---|---|---|---|
| **Sindikasi / co-financing** *(ada di app ini)* | Lead Arranger (bank kita) | Agen underwriting bank peserta | Institusi berbeda, logika opaque |
| **Correspondent / cross-border payment** | Agen bank pengirim | Agen bank penerima | Skrining sanksi/AML lintas-bank |
| **Trade finance (LC)** | Agen bank importir | Agen bank eksportir | Penerbitan/verifikasi Letter of Credit |
| **Verifikasi lintas-lembaga** | Agen bank | Agen otoritas pajak / Dukcapil / biro kredit | Data dari otoritas pihak-3 |
| **Bancassurance / klaim** | Agen bank | Agen perusahaan asuransi | Proses klaim lintas-entitas |
| **Onboarding korporasi (KYB)** | Agen bank | Agen penyedia registrasi/KYB | Verifikasi badan usaha |
| **Debt syndication secondary** | Agen originator | Agen investor institusi | Distribusi risiko antar pemodal |
"""

APP_MAP = """
### Peta 8 use case di app ini → pola → protokol

| # | Use case | Pola agentic | Protokol/sistem |
|---|---|---|---|
| 1 | Kredit Ritel | **Sequential** | MCP (Bureau/KYC/Policy) + REST |
| 2 | Pembiayaan UKM | **Concurrent** + HITL | MCP + REST |
| 3 | Layanan Nasabah | **Routing** (≈Handoff) | REST + MCP |
| 4 | Restrukturisasi | **Evaluator–Optimizer** | MCP + REST + rules engine |
| 5 | Investigasi AML | **ReAct** + HITL | MCP + REST |
| 6 | Komite Kredit | **Group Chat** | MCP (policy) |
| 7 | Investigasi Kompleks | **Magentic** | MCP + REST |
| 8 | **Sindikasi** | **A2A** (Agent2Agent) | **A2A** + MCP + REST |

**Governance di semua use case:** audit log, budget token, redaksi PII, content safety, policy deterministik OJK/BI, human gate.
"""

HOW_TO_CONNECT = """
### Cara menghubungkan — contoh kode (Microsoft Agent Framework, Python)

**1) Agen memakai tool via MCP (klien MCP):**
```python
from agent_framework import MCPStreamableHTTPTool
kyc = MCPStreamableHTTPTool(name="kyc_aml", url=f"{BASE}/mcp/kyc-aml/")
async with kyc as tool:
    result = await agent.run("Screen NIK ...", tools=[tool])
```

**2) Memanggil agen remote via A2A (klien A2A):**
```python
from agent_framework.a2a import A2AAgent
partner = A2AAgent(name="partner", url=PARTNER_AGENT_CARD_URL)
reply = await partner.run("…ringkasan deal sindikasi…")
```

**3) Meng-expose agen Anda sebagai server A2A (server A2A):**
```python
from agent_framework.a2a import A2AExecutor
executor = A2AExecutor(my_agent)   # + request handler + routes + Agent Card
# host via ASGI (Starlette/FastAPI); publish Agent Card di /.well-known/agent-card.json
```

**4) Protokol A2A langsung (tanpa SDK) — untuk memahami wire format:**
- **Discovery:** `GET https://partner/.well-known/agent-card.json`
- **Kirim tugas:** `POST https://partner/a2a` dengan JSON-RPC:
```json
{ "jsonrpc":"2.0","id":"1","method":"message/send",
  "params": { "message": { "role":"user",
    "parts":[{"kind":"text","text":"<deal JSON>"}], "messageId":"m1" } } }
```
> ⚠️ **Pitfall nyata:** di belakang ingress HTTPS, Agent Card harus meng-*advertise* URL **https** (hormati
> `X-Forwarded-Proto`); kalau tidak, `POST` ke http kena **301 → https** dan body JSON-RPC bisa hilang.
"""

# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
tab_qa, tab_matrix, tab_compare, tab_howto, tab_fsi = st.tabs(
    ["❓ Tanya-Jawab", "📊 Matriks Keputusan", "🔀 MCP vs A2A & Framework",
     "🔧 Cara Menghubungkan", "🏦 Skenario FSI & Peta App"]
)

with tab_qa:
    st.markdown(f"**{len(ENTRIES)} pertanyaan** — dari pemula sampai pakar. Cari atau saring per tingkat.")
    c1, c2 = st.columns([3, 2])
    query = c1.text_input("🔎 Cari (mis. 'A2A', 'MCP', 'migrasi', 'keamanan', 'LangGraph')", "")
    lvl = c2.selectbox("Tingkat", ["(semua)"] + LEVELS)
    q = query.strip().lower()

    def _match(e: dict) -> bool:
        if lvl != "(semua)" and e["level"] != lvl:
            return False
        if q and q not in e["q"].lower() and q not in e["a"].lower() and q not in e["level"].lower():
            return False
        return True

    shown = [e for e in ENTRIES if _match(e)]
    st.caption(f"Menampilkan {len(shown)} dari {len(ENTRIES)} pertanyaan.")
    for level in LEVELS:
        group = [e for e in shown if e["level"] == level]
        if not group:
            continue
        st.markdown(f"#### {LVL_ICON[level]} {level}")
        for e in group:
            with st.expander(f"{LVL_ICON[e['level']]} {e['q']}"):
                st.markdown(e["a"])

with tab_matrix:
    st.markdown(WHEN_A2A)
    st.divider()
    st.markdown(PROTOCOL_MATRIX)
    st.divider()
    st.markdown(ORCH_MATRIX)

with tab_compare:
    st.markdown(MCP_VS_A2A)
    st.divider()
    st.markdown(FRAMEWORK_TABLE)

with tab_howto:
    st.markdown(HOW_TO_CONNECT)

with tab_fsi:
    st.markdown(FSI_SCENARIOS)
    st.divider()
    st.markdown(APP_MAP)

st.divider()
st.caption("Rujuk dokumentasi resmi untuk detail terbaru: Microsoft Agent Framework, Model Context Protocol "
           "(MCP), dan Agent2Agent (A2A) di Linux Foundation.")
