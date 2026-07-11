"""Live animated agent-flow visualization for the portal.

Each agent node shows the MCP/API systems it calls (badges inside the node).
Behavior:
  * an agent node PULSES only while actively processing (idle = no blink);
  * its system badges GLOW while it is calling them;
  * connector lines FLOW only on the active path.

The page re-renders this HTML on each real workflow event.
"""
from __future__ import annotations

# id, emoji, name, role, [system ids]
RETAIL_CATALOG = [
    ("intake", "🧾", "Intake & Verifikasi", "Verifikasi identitas & penghasilan", ["kyc", "corebank"]),
    ("credit", "📊", "Credit Risk", "Skor & kapasitas bayar (DBR)", ["bureau"]),
    ("compliance", "⚖️", "Compliance OJK/BI", "Aturan kelayakan deterministik", ["policy"]),
    ("decision", "✅", "Decision & Offer", "Keputusan + penawaran", ["pricing"]),
]

SME_CATALOG = [
    ("orchestrator", "🧭", "Orchestrator", "Menyebar & menggabungkan tugas", []),
    ("financial", "📊", "Analis Keuangan", "Rasio keuangan & arus kas", ["financials"]),
    ("collateral", "🏠", "Penilai Agunan", "Nilai wajar & LTV", ["collateral"]),
    ("aml", "🛡️", "AML / Fraud", "DTTOT · PPATK · PEP", ["kyc"]),
    ("market", "🌐", "Risiko Pasar", "Risiko sektor & makro", []),
    ("aggregate", "🧮", "Underwriting", "Rekomendasi & kovenan", []),
    ("human", "🧑‍⚖️", "Petugas Kredit", "Keputusan manusia", []),
    ("termsheet", "📄", "Term Sheet", "Penerbitan term sheet", ["pricing"]),
]

# Use Case 3 — Smart Customer Servicing (ROUTING)
SERVICING_CATALOG = [
    ("router", "🧭", "Router", "Klasifikasi intent pesan", []),
    ("dispute", "💳", "Sengketa", "Sengketa transaksi", ["corebank"]),
    ("limit", "📈", "Naik Limit", "Kelayakan kenaikan limit", ["corebank", "bureau"]),
    ("hardship", "🆘", "Kesulitan Bayar", "Arahkan ke restrukturisasi", ["servicing"]),
    ("balance", "💰", "Info Saldo", "Saldo & mutasi rekening", ["corebank"]),
    ("general", "💬", "Umum", "Pertanyaan umum", []),
]

# Use Case 4 — Loan Restructuring Advisor (EVALUATOR-OPTIMIZER)
RESTRUCTURE_CATALOG = [
    ("proposer", "🧩", "Proposer", "Menyusun skema restrukturisasi", ["servicing", "bureau"]),
    ("evaluator", "🔎", "Evaluator", "Menilai keterjangkauan & kebijakan", ["policy"]),
    ("writer", "📝", "Penjelasan", "Menulis keputusan akhir", []),
]

# Use Case 5 — AML / Fraud Investigation (ReAct + human SAR gate)
AML_CATALOG = [
    ("investigator", "🕵️", "Investigator", "ReAct: pilih tool dinamis", ["kyc", "corebank", "bureau", "monitoring"]),
    ("human", "🧑‍⚖️", "Analis AML", "Konfirmasi pelaporan SAR", []),
    ("filing", "📄", "Pelaporan SAR", "Terbitkan SAR/LTKM (PPATK)", []),
]

# Use Case 6 — Credit Committee (GROUP CHAT)
COMMITTEE_CATALOG = [
    ("chair", "⚖️", "Chair", "Moderator & keputusan", []),
    ("optimist", "📈", "Risk Optimist", "Argumen pro-approve", []),
    ("skeptic", "🛑", "Risk Skeptic", "Devil's advocate", []),
    ("compliance", "🛡️", "Compliance", "Red line OJK/BI", ["policy"]),
]

# Use Case 7 — Complex Investigation (MAGENTIC)
MAGENTIC_CATALOG = [
    ("manager", "🧠", "Manager", "Task ledger + replan", []),
    ("kyc", "🛡️", "Worker · KYC", "Sanksi/PEP", ["kyc"]),
    ("transactions", "💳", "Worker · Transaksi", "Mutasi + alert", ["corebank", "monitoring"]),
    ("credit", "🏦", "Worker · Kredit", "Eksposur kredit", ["bureau"]),
    ("financials", "📑", "Worker · Finansial", "Profil finansial", ["corebank", "servicing"]),
]

# Use Case 8 — Syndicated / Co-Financing (A2A · Agent2Agent)
A2A_CATALOG = [
    ("arranger", "🏛️", "Lead Arranger (BNS)", "Struktur sindikasi & undangan", []),
    ("a2a", "🔗", "A2A Protocol", "Discover card + message/send", ["partner"]),
    ("partner", "🤝", "Partner Bank (BMS)", "Agen remote (organisasi lain)", []),
    ("finalize", "🧾", "Sindikasi Final", "Gabung porsi & pricing", []),
]

SYSTEMS = {
    "bureau": ("🏦", "Credit Bureau MCP", "mcp"),
    "kyc": ("🛡️", "KYC/AML MCP", "mcp"),
    "policy": ("⚖️", "Policy MCP", "mcp"),
    "corebank": ("💳", "Core Banking API", "rest"),
    "collateral": ("🏠", "Collateral API", "rest"),
    "financials": ("📑", "Financials API", "rest"),
    "pricing": ("🏷️", "Pricing API", "rest"),
    "servicing": ("🧾", "Loan Servicing API", "rest"),
    "monitoring": ("🚨", "Transaction Monitoring API", "rest"),
    "partner": ("🤝", "Partner Bank (BMS) · A2A", "a2a"),
}

_CSS = """
<style>
  .fw{font-family:'Segoe UI',system-ui,sans-serif;color:#e8eef7;background:#0e1420;padding:14px;border-radius:12px;}
  .row{display:flex;align-items:center;justify-content:center;gap:0;flex-wrap:wrap;}
  .fan{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;margin:2px 0;}
  .center{display:flex;justify-content:center;}
  .lbl{text-align:center;font-size:10px;color:#7c8aa0;margin:5px 0 3px;letter-spacing:.5px;}
  .node{background:#182233;border:2px solid #2b3a52;border-radius:11px;padding:8px 10px;
        min-width:146px;max-width:168px;text-align:center;transition:all .25s;}
  .node .em{font-size:22px;line-height:1;}
  .node .nm{font-weight:700;font-size:12px;margin-top:4px;}
  .node .ro{font-size:10px;color:#9fb0c7;margin-top:2px;min-height:24px;}
  .node .st{font-size:9.5px;margin-top:4px;font-weight:600;}
  .bwrap{margin-top:5px;display:flex;flex-direction:column;gap:2px;}
  .b{font-size:9px;border-radius:6px;padding:1px 5px;border:1px solid #2b6fd6;color:#8fc0ff;background:#0f2036;opacity:.65;}
  .b.rest{border-style:dashed;}
  .pending{opacity:.5;} .pending .st{color:#7c8aa0;}
  .done{border-color:#2ecc71;} .done .st{color:#5be08f;}
  .active{border-color:#f5a623;animation:pulse 1s infinite;} .active .st{color:#ffcf70;}
  .active .b{opacity:1;border-color:#4da3ff;box-shadow:0 0 8px #4da3ff88;animation:glow 1s infinite;}
  .waiting{border-color:#c084fc;animation:pulseP 1.3s infinite;} .waiting .st{color:#d6b3ff;}
  @keyframes pulse{0%{box-shadow:0 0 0 0 #f5a62399;}70%{box-shadow:0 0 0 12px #f5a62300;}100%{box-shadow:0 0 0 0 #f5a62300;}}
  @keyframes pulseP{0%{box-shadow:0 0 0 0 #c084fc99;}70%{box-shadow:0 0 0 12px #c084fc00;}100%{box-shadow:0 0 0 0 #c084fc00;}}
  @keyframes glow{0%{box-shadow:0 0 4px #4da3ff44;}50%{box-shadow:0 0 12px #4da3ffcc;}100%{box-shadow:0 0 4px #4da3ff44;}}
  .conn{width:40px;height:5px;background:#22304a;border-radius:3px;position:relative;overflow:hidden;margin:0 2px;}
  .vconn{width:5px;height:26px;background:#22304a;border-radius:3px;position:relative;overflow:hidden;margin:2px auto;}
  .conn.flow::before{content:'';position:absolute;top:0;left:-45%;width:45%;height:100%;
        background:linear-gradient(90deg,transparent,#4da3ff,transparent);animation:flow 1s linear infinite;}
  .vconn.flow::before{content:'';position:absolute;left:0;top:-45%;height:45%;width:100%;
        background:linear-gradient(180deg,transparent,#4da3ff,transparent);animation:vflow 1s linear infinite;}
  @keyframes flow{0%{left:-45%;}100%{left:100%;}}
  @keyframes vflow{0%{top:-45%;}100%{top:100%;}}
</style>
"""


def _badges(system_ids):
    out = []
    for sid in system_ids:
        em, nm, kind = SYSTEMS[sid]
        out.append(f"<div class='b {kind}'>{em} {nm}</div>")
    return f"<div class='bwrap'>{''.join(out)}</div>" if out else ""


def _node(nid, catmap, active, done, waiting):
    _id, em, nm, ro, systems = catmap[nid]
    if nid in done:
        state, label = "done", "✅ selesai"
    elif nid in active:
        state, label = "active", "● memproses…"
    elif waiting == nid:
        state, label = "waiting", "⏳ menunggu"
    else:
        state, label = "pending", "idle"
    return (f"<div class='node {state}'><div class='em'>{em}</div><div class='nm'>{nm}</div>"
            f"<div class='ro'>{ro}</div>{_badges(systems)}<div class='st'>{label}</div></div>")


def _conn(vertical, flow):
    cls = ("vconn" if vertical else "conn") + (" flow" if flow else "")
    return f"<div class='{cls}'></div>"


def render_retail_html(active=None, done=None) -> str:
    active, done = set(active or ()), set(done or ())
    catmap = {c[0]: c for c in RETAIL_CATALOG}
    order = ["intake", "credit", "compliance", "decision"]
    parts = []
    for i, nid in enumerate(order):
        parts.append(f"<div class='center'>{_node(nid, catmap, active, done, None)}</div>")
        if i < len(order) - 1:
            flow = (nid in active) or (order[i + 1] in active)
            parts.append(f"<div class='center'>{_conn(True, flow)}</div>")
    return (_CSS + "<div class='fw'>"
            "<div class='lbl'>ALUR SEQUENTIAL (SERIAL) — badge biru = sistem/MCP yang dipanggil agen</div>"
            f"{''.join(parts)}</div>")


def render_sme_html(active=None, done=None, waiting=None) -> str:
    active, done = set(active or ()), set(done or ())
    catmap = {c[0]: c for c in SME_CATALOG}

    def nd(nid):
        return _node(nid, catmap, active, done, waiting)

    specs = ["financial", "collateral", "aml", "market"]
    fan = "".join(f"<div>{nd(s)}{_conn(True, s in active)}</div>" for s in specs)
    return (_CSS + "<div class='fw'>"
            "<div class='lbl'>ALUR CONCURRENT STAR (HUB-AND-SPOKE) + HUMAN-IN-THE-LOOP — badge = sistem/MCP</div>"
            f"<div class='center'>{nd('orchestrator')}</div>"
            f"<div class='center'>{_conn(True, any(s in active for s in specs))}</div>"
            "<div class='lbl'>fan-out — 4 agen spesialis PARALEL</div>"
            f"<div class='fan'>{fan}</div>"
            f"<div class='center'>{nd('aggregate')}</div>"
            f"<div class='center'>{_conn(True, 'aggregate' in active)}</div>"
            f"<div class='center'>{nd('human')}</div>"
            f"<div class='center'>{_conn(True, 'termsheet' in active)}</div>"
            f"<div class='center'>{nd('termsheet')}</div></div>")


def render_servicing_html(active=None, done=None) -> str:
    active, done = set(active or ()), set(done or ())
    catmap = {c[0]: c for c in SERVICING_CATALOG}

    def nd(nid):
        return _node(nid, catmap, active, done, None)

    handlers = ["dispute", "limit", "hardship", "balance", "general"]
    any_handler = any(h in active or h in done for h in handlers)
    fan = "".join(f"<div>{_conn(True, h in active)}{nd(h)}</div>" for h in handlers)
    return (_CSS + "<div class='fw'>"
            "<div class='lbl'>ALUR ROUTING — Router memilih SATU handler; badge = sistem/MCP</div>"
            f"<div class='center'>{nd('router')}</div>"
            f"<div class='center'>{_conn(True, any_handler)}</div>"
            "<div class='lbl'>routing — hanya 1 handler yang aktif</div>"
            f"<div class='fan'>{fan}</div></div>")


def render_restructure_html(active=None, done=None, iteration=None) -> str:
    active, done = set(active or ()), set(done or ())
    catmap = {c[0]: c for c in RESTRUCTURE_CATALOG}

    def nd(nid):
        return _node(nid, catmap, active, done, None)

    itlbl = f"iterasi #{iteration}" if iteration else "loop propose → evaluate"
    loop_flow = ("proposer" in active) or ("evaluator" in active)
    return (_CSS + "<div class='fw'>"
            "<div class='lbl'>ALUR EVALUATOR–OPTIMIZER (REFLEKSI) — badge = sistem/MCP</div>"
            f"<div class='center'>{nd('proposer')}</div>"
            f"<div class='center'>{_conn(True, loop_flow)}</div>"
            f"<div class='center'>{nd('evaluator')}</div>"
            f"<div class='lbl'>↺ umpan balik ke Proposer bila belum lolos ({itlbl})</div>"
            f"<div class='center'>{_conn(True, 'writer' in active)}</div>"
            f"<div class='center'>{nd('writer')}</div></div>")


def render_aml_html(active=None, done=None, waiting=None) -> str:
    active, done = set(active or ()), set(done or ())
    catmap = {c[0]: c for c in AML_CATALOG}

    def nd(nid):
        return _node(nid, catmap, active, done, waiting)

    return (_CSS + "<div class='fw'>"
            "<div class='lbl'>ALUR ReAct (AUTONOMOUS TOOL USE) + HUMAN SAR GATE — badge = sistem/MCP</div>"
            f"<div class='center'>{nd('investigator')}</div>"
            "<div class='lbl'>ReAct: agen memilih tool secara dinamis (reason → act → observe)</div>"
            f"<div class='center'>{_conn(True, 'investigator' in active)}</div>"
            f"<div class='center'>{nd('human')}</div>"
            f"<div class='center'>{_conn(True, 'filing' in active)}</div>"
            f"<div class='center'>{nd('filing')}</div></div>")


def render_committee_html(active=None, done=None, round=None) -> str:
    active, done = set(active or ()), set(done or ())
    catmap = {c[0]: c for c in COMMITTEE_CATALOG}

    def nd(nid):
        return _node(nid, catmap, active, done, None)

    debaters = ["optimist", "skeptic", "compliance"]
    rlbl = f"ronde #{round}" if round else "debat berputar (round-robin)"
    fan = "".join(f"<div>{nd(d)}{_conn(True, d in active)}</div>" for d in debaters)
    return (_CSS + "<div class='fw'>"
            "<div class='lbl'>ALUR GROUP CHAT — debat bersama dimoderasi Chair; badge = sistem/MCP</div>"
            f"<div class='center'>{nd('chair')}</div>"
            f"<div class='center'>{_conn(True, any(d in active for d in debaters))}</div>"
            f"<div class='lbl'>🗣️ {rlbl} — transkrip dibagikan ke semua peserta</div>"
            f"<div class='fan'>{fan}</div></div>")


def render_magentic_html(active=None, done=None) -> str:
    active, done = set(active or ()), set(done or ())
    catmap = {c[0]: c for c in MAGENTIC_CATALOG}

    def nd(nid):
        return _node(nid, catmap, active, done, None)

    workers = ["kyc", "transactions", "credit", "financials"]
    fan = "".join(f"<div>{_conn(True, w in active)}{nd(w)}</div>" for w in workers)
    return (_CSS + "<div class='fw'>"
            "<div class='lbl'>ALUR MAGENTIC — Manager + task ledger + replan; badge = sistem/MCP</div>"
            f"<div class='center'>{nd('manager')}</div>"
            f"<div class='center'>{_conn(True, any(w in active for w in workers))}</div>"
            "<div class='lbl'>↺ Manager menugaskan worker, meninjau progres, & dapat REPLAN</div>"
            f"<div class='fan'>{fan}</div></div>")


def render_a2a_html(active=None, done=None) -> str:
    active, done = set(active or ()), set(done or ())
    catmap = {c[0]: c for c in A2A_CATALOG}
    order = ["arranger", "a2a", "partner", "finalize"]
    parts = []
    for i, nid in enumerate(order):
        parts.append(f"<div class='center'>{_node(nid, catmap, active, done, None)}</div>")
        if i < len(order) - 1:
            flow = (nid in active) or (order[i + 1] in active)
            parts.append(f"<div class='center'>{_conn(True, flow)}</div>")
            if nid == "a2a":
                parts.append("<div class='lbl'>— batas organisasi (A2A over HTTPS) —</div>")
    return (_CSS + "<div class='fw'>"
            "<div class='lbl'>ALUR A2A (AGENT2AGENT) — delegasi lintas-organisasi; badge = agen remote</div>"
            f"{''.join(parts)}</div>")


class FlowState:
    """Accumulates workflow events into active/done/waiting sets for rendering."""

    def __init__(self) -> None:
        self.active: set[str] = set()
        self.done: set[str] = set()
        self.waiting: str | None = None

    def apply(self, node: str, state: str) -> None:
        if state == "active":
            self.active.add(node)
            self.waiting = None
        elif state == "done":
            self.active.discard(node)
            self.done.add(node)
        elif state == "waiting":
            self.active.discard(node)
            self.waiting = node


# Rich descriptions for the "agents involved" panel.
RETAIL_DETAILS = [
    ("🧾 Intake & Verifikasi",
     "Memverifikasi identitas pemohon (Dukcapil via **KYC/AML MCP** `screen_individual`) dan "
     "mencocokkan penghasilan yang diklaim dengan mutasi rekening (**Core Banking API**). "
     "Keluaran: status verifikasi identitas & penghasilan, rating risiko KYC."),
    ("📊 Credit Risk Scoring",
     "Mengambil laporan **SLIK OJK / Biro Kredit** (**Credit Bureau MCP** `get_credit_report`): skor, "
     "grade, kolektibilitas (kol), kewajiban bulanan. Menghitung DBR & kapasitas bayar."),
    ("⚖️ Compliance OJK/BI",
     "Gerbang keputusan **deterministik** (bukan LLM) via **Policy Rules MCP** `evaluate_retail`: "
     "cek penghasilan minimum, DBR ≤ 40%, usia, skor, kol, dan sanksi DTTOT. Hasil: APPROVE/DECLINE/REFER."),
    ("✅ Decision & Offer",
     "Menyusun keputusan akhir dan (bila disetujui) penawaran dari **Pricing API** — plafon, bunga, "
     "angsuran — serta penjelasan untuk nasabah dalam Bahasa Indonesia."),
]

SME_DETAILS = [
    ("🧭 Orchestrator (Hub)",
     "Pusat arsitektur *star*. Menyebar permohonan ke 4 agen spesialis secara **paralel**, lalu "
     "menggabungkan temuan menjadi satu rekomendasi underwriting."),
    ("📊 Analis Keuangan",
     "**Financials API** `get_financial_statements` (3 tahun): likuiditas, leverage, profitabilitas, "
     "tren arus kas. Menandai penurunan omzet / laba bersih negatif."),
    ("🏠 Penilai Agunan",
     "**Collateral API**: nilai wajar vs nilai appraisal, dan **LTV** terhadap fasilitas yang diminta."),
    ("🛡️ AML / Fraud",
     "**KYC/AML MCP** `screen_entity`: sanksi **DTTOT**, laporan **PPATK** (STR), status **PEP** "
     "beneficial owner, dan adverse media."),
    ("🌐 Risiko Pasar",
     "Menilai risiko sektor & makro Indonesia berdasarkan penalaran model (tanpa tool)."),
    ("🧮 Underwriting (agregasi)",
     "Menggabungkan 4 temuan + pra-skrining **Policy MCP** `evaluate_sme` (LTV, DSCR, DER) menjadi "
     "rekomendasi: keputusan, rating risiko, plafon, bunga, dan kovenan."),
    ("🧑‍⚖️ Petugas Kredit (Human-in-the-loop)",
     "Manusia menyetujui / menolak / meminta info tambahan sebelum term sheet diterbitkan — "
     "dapat menyesuaikan plafon & bunga."),
    ("📄 Term Sheet",
     "Menerbitkan term sheet final (**Pricing API**) sesuai keputusan petugas, dalam Bahasa Indonesia."),
]

SERVICING_DETAILS = [
    ("🧭 Router (Routing)",
     "Membaca pesan bebas nasabah dan mengklasifikasikannya menjadi **satu** intent "
     "(sengketa / naik limit / kesulitan bayar / info saldo / umum). Hanya **satu** handler "
     "yang dijalankan — inti dari pola *routing*."),
    ("💳 Handler Sengketa",
     "**Core Banking** `get_transactions`: menelusuri mutasi, menemukan debit yang disengketakan, "
     "dan membuka kasus sengketa (diteruskan ke tim back-office)."),
    ("📈 Handler Naik Limit",
     "**Core Banking** `get_account_summary` + **Credit Bureau MCP** `get_credit_report`: menilai "
     "arus kas & SLIK untuk kelayakan kenaikan limit."),
    ("🆘 Handler Kesulitan Bayar",
     "**Loan Servicing API** `get_existing_loans`: mengonfirmasi fasilitas berjalan & tunggakan, "
     "lalu mengarahkan ke proses **restrukturisasi**."),
    ("💰 Handler Info Saldo",
     "**Core Banking** `get_account_summary`: menjawab pertanyaan saldo/mutasi secara faktual."),
    ("💬 Handler Umum",
     "Menjawab pertanyaan umum berdasarkan penalaran model (tanpa tool)."),
]

RESTRUCTURE_DETAILS = [
    ("🧩 Proposer",
     "**Loan Servicing API** `get_existing_loans` + **Credit Bureau MCP**: menyusun skema "
     "restrukturisasi (perpanjang tenor, turunkan bunga, grace period) untuk meringankan angsuran."),
    ("🔎 Evaluator (Refleksi)",
     "Mengecek proposal terhadap ambang **keterjangkauan** (DBR) & kebijakan via **Policy MCP** "
     "`evaluate_restructure`. Bila belum lolos, memberi **umpan balik** ke Proposer untuk revisi — "
     "loop *evaluator–optimizer* hingga lolos atau batas iterasi."),
    ("📝 Penjelasan",
     "Menuliskan keputusan akhir & skema yang disetujui dalam Bahasa Indonesia."),
]

AML_DETAILS = [
    ("🕵️ Investigator (ReAct)",
     "Agen **otonom** yang memilih tool secara **dinamis** (reason → act → observe): "
     "**KYC/AML MCP** `screen_individual`, **Core Banking** `get_transactions`, **Transaction "
     "Monitoring API** `get_monitoring_alerts`, **Credit Bureau MCP** `get_credit_report`. "
     "Menyusun rekomendasi SAR/LTKM."),
    ("🧑‍⚖️ Analis AML (Human-in-the-loop)",
     "Analis manusia mengonfirmasi apakah **melaporkan (file)**, menutup (dismiss), atau "
     "mengeskalasi kasus sebelum SAR diterbitkan."),
    ("📄 Pelaporan SAR",
     "Menerbitkan Suspicious Activity Report / LTKM (PPATK) sesuai keputusan analis, "
     "dalam Bahasa Indonesia."),
]

COMMITTEE_DETAILS = [
    ("⚖️ Chair (Moderator/Manager)",
     "Membuka sidang dengan ringkasan kasus, memimpin **debat berputar** (round-robin), lalu "
     "menutup dan **memutuskan** (APPROVE/DECLINE/REFER). Tidak boleh approve bila ada pelanggaran "
     "kebijakan keras (gerbang deterministik OJK/BI)."),
    ("📈 Risk Optimist",
     "Berargumen **mendukung** persetujuan: potensi pertumbuhan, kapasitas bayar, nilai relasi. "
     "Menanggapi transkrip bersama, bukan sekadar mengulang."),
    ("🛑 Risk Skeptic (Devil's Advocate)",
     "Menyoroti **risiko & sisi negatif**: leverage, volatilitas arus kas, risiko sektor, agunan "
     "lemah. Menantang argumen optimist secara langsung."),
    ("🛡️ Compliance",
     "Fokus pada **red line regulasi** (DTTOT, PPATK, LTV/DSCR/DER, usia usaha) via pra-skrining "
     "**Policy MCP** `evaluate_sme`. Menyatakan bila ada pelanggaran keras."),
]

MAGENTIC_DETAILS = [
    ("🧠 Manager (Magentic)",
     "Menyusun **task ledger** (rencana 3-5 langkah), menugaskan tiap langkah ke worker, "
     "**meninjau progres**, dan dapat **REPLAN** (menambah langkah) bila objektif belum tercakup, "
     "lalu menulis **dosir** final. Inti pola *Magentic*: manajer + tim + ledger + replanning."),
    ("🛡️ Worker · KYC",
     "**KYC/AML MCP** `screen_individual`: identitas, sanksi DTTOT, PPATK, PEP."),
    ("💳 Worker · Transaksi",
     "**Core Banking** `get_transactions` + **Transaction Monitoring** `get_monitoring_alerts`: "
     "pola & tipologi mencurigakan."),
    ("🏦 Worker · Kredit",
     "**Credit Bureau MCP** `get_credit_report`: eksposur & fasilitas kredit."),
    ("📑 Worker · Finansial",
     "**Core Banking** `get_account_summary` + **Loan Servicing** `get_existing_loans`: profil "
     "finansial & kewajiban berjalan."),
]

A2A_DETAILS = [
    ("🏛️ Lead Arranger (BNS)",
     "Menyusun struktur sindikasi ketika fasilitas melebihi batas single-obligor BNS: berapa yang "
     "**ditahan** BNS dan berapa yang **disindikasikan**, lalu menyiapkan undangan co-financing."),
    ("🔗 A2A Protocol (Agent2Agent)",
     "BNS **menemukan Agent Card** partner (di `/.well-known/agent-card.json`) lalu mengirim tugas "
     "**JSON-RPC `message/send`** berisi ringkasan deal — melintasi **batas organisasi** via HTTPS. "
     "Ini beda dari MCP (agen→tool): A2A menghubungkan **agen→agen**."),
    ("🤝 Partner Bank (BMS)",
     "Agen **milik bank lain** (Bank Mitra Sejahtera), **di-deploy terpisah** & opaque. Menilai "
     "dengan selera risikonya sendiri dan mengembalikan **penawaran partisipasi** (plafon, bunga, "
     "syarat) — BNS tak melihat kode/data/model-nya."),
    ("🧾 Sindikasi Final",
     "Menggabungkan porsi BNS + porsi partner, menghitung kekurangan (shortfall) & **blended rate**, "
     "lalu menyusun ringkasan penutup."),
]
