"""Governance dashboard — audit trail, cost/token, content safety, SME cases."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.core.config import get_settings
from app.governance.audit_log import get_audit_logger
from app.governance.content_safety import redact_pii
from app.portal.portal_utils import render_audit_legend
from app.workflows.case_store import get_case_store

st.title("🛡️ Audit & Governance")
st.caption("Jejak audit setiap langkah agen · budget token · content safety/PII · human approval")

settings = get_settings()
audit = get_audit_logger()
events = audit.recent(500)

if not events:
    st.info("Belum ada aktivitas. Jalankan salah satu use case (Retail, UKM, Servicing, "
            "Restrukturisasi, AML) terlebih dahulu.")
    st.stop()

df = pd.DataFrame(events)

# ---- Summary metrics ----
tokens_by_req = df.groupby("request_id")["tokens"].max()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total permohonan", df["request_id"].nunique())
c2.metric("Total langkah audit", len(df))
c3.metric("Total token (≈)", f"{int(tokens_by_req.sum()):,}")
c4.metric("Budget/req", f"{settings.token_budget_per_request:,}")

st.divider()

# ---- Filter by request ----
left, right = st.columns([1, 3])
with left:
    use_cases = ["(semua)"] + sorted(df["use_case"].unique().tolist())
    use_case = st.selectbox("Use case", use_cases)
    req_ids = ["(semua)"] + sorted(df["request_id"].unique().tolist())
    req = st.selectbox("Request ID", req_ids)

view = df.copy()
if use_case != "(semua)":
    view = view[view["use_case"] == use_case]
if req != "(semua)":
    view = view[view["request_id"] == req]

with right:
    st.markdown("**Jejak audit** (PII sudah diredaksi)")
    view = view.assign(detail=view["detail"].map(redact_pii))
    st.dataframe(
        view[["ts", "request_id", "use_case", "step", "actor", "decision", "tokens", "detail"]],
        use_container_width=True, hide_index=True, height=380,
    )
    render_audit_legend()

st.divider()

# ---- Decisions & human-in-loop cases ----
d1, d2 = st.columns(2)
with d1:
    st.markdown("**Distribusi keputusan akhir**")
    finals = df[df["step"].isin(["final", "compliance", "prescreen", "recommendation"])]
    if not finals.empty:
        st.bar_chart(finals["decision"].value_counts())
with d2:
    st.markdown("**Case Human-in-the-Loop (UKM & AML)**")
    store = get_case_store()
    sme_cases = [{**c, "use_case": "sme"} for c in store.list_all(100)]
    aml_cases = [{"request_id": c["request_id"], "company_id": c["subject_id"],
                  "status": c["status"], "tokens": c["tokens"], "updated_ts": c["updated_ts"],
                  "use_case": "aml"} for c in store.list_aml_all(100)]
    cases = sme_cases + aml_cases
    if cases:
        st.dataframe(pd.DataFrame(cases), use_container_width=True, hide_index=True)
    else:
        st.caption("Belum ada case human-in-the-loop.")

st.divider()
st.markdown(
    f"""
**Kontrol governance aktif:**
- 🔒 Redaksi PII: NIK, NPWP, telepon, email (regex) — Azure AI Content Safety endpoint:
  `{'terkonfigurasi' if settings.content_safety_endpoint else 'fallback keyword'}`
- 🧮 Policy engine deterministik OJK/BI (bukan LLM) untuk keputusan compliance & keterjangkauan
- 🧑‍⚖️ Human approval gate pada pembiayaan UKM & pelaporan SAR (AML)
- 💰 Budget token per permohonan: {settings.token_budget_per_request:,}
- 📈 Telemetry OpenTelemetry → Azure Application Insights (`appi-finance-agenticai`)
    """
)
