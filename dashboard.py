"""
SPECTRA Dashboard - Streamlit tabanlı görselleştirme ve kontrol paneli.

Ekranlar:
  - Sol sidebar: senaryo seçimi, jammer parametreleri, STM32 durumu
  - Ana alan: simülasyon grafikleri (MIS, delivery rate, link quality)
  - Taktik harita: düğümler, linkler, anlık mod renkleri
  - Monte Carlo: hızlı istatistik özet

Çalıştırma:
    streamlit run dashboard.py
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
import time
from typing import Dict, List

# ─── Sayfa Yapılandırması ──────────────────────────────────────────
st.set_page_config(
    page_title="SPECTRA | Taktik Ağ Karar Motoru",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ─────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .block-container { padding-top: 1rem; }

    /* Metric Card */
    .metric-card {
        background: linear-gradient(135deg, #1a2035 0%, #1c2541 100%);
        border: 1px solid #2d3561;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 10px;
    }
    .metric-label {
        font-size: 12px;
        color: #8892b0;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .metric-value {
        font-size: 28px;
        font-weight: 700;
        color: #ccd6f6;
    }
    .metric-value.good { color: #64ffda; }
    .metric-value.warn { color: #ffd700; }
    .metric-value.bad  { color: #ff6b6b; }

    /* Mode Badge */
    .mode-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 1px;
    }
    .mode-NORMAL        { background:#1a3a2a; color:#64ffda; border:1px solid #64ffda; }
    .mode-DEGRADED      { background:#3a3a1a; color:#ffd700; border:1px solid #ffd700; }
    .mode-LOCAL_AUTONOMY{ background:#3a1a1a; color:#ff9944; border:1px solid #ff9944; }
    .mode-SILENT        { background:#2a1a2a; color:#bb86fc; border:1px solid #bb86fc; }

    /* Header */
    .spectra-header {
        background: linear-gradient(90deg, #0d1b2a, #1c2541, #0d1b2a);
        border-bottom: 2px solid #233554;
        padding: 12px 24px;
        margin-bottom: 20px;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ─── Simülasyon Çalıştırıcı ─────────────────────────────────────────
@st.cache_resource
def load_topology():
    from src.network.topology import NetworkTopology
    return NetworkTopology.from_yaml("config/network.yaml")


def run_simulation(scenario_name: str, jammer_power: float,
                   duration: int, message_rate: float, tick: float):
    """Tek bir simülasyon çalıştırır, sonuçları dict olarak döner."""
    from src.network.topology import NetworkTopology
    from src.ew.spectrum import SpectrumEnvironment
    from src.ew.jammer import create_barrage_jammer, create_spot_jammer, create_sweep_jammer
    from src.ew.effects import EWEffectCalculator
    from src.engine.rules import RuleBasedEngine
    from src.simulation.scenario import Scenario
    from src.simulation.runner import SimulationRunner

    topo = NetworkTopology.from_yaml("config/network.yaml")
    spectrum = SpectrumEnvironment()
    ew = EWEffectCalculator(spectrum, topo)

    jammer_map = {
        "Barrage (Geniş Band)": create_barrage_jammer("JAM_1", power_dbm=jammer_power),
        "Spot (Dar Band)":      create_spot_jammer("JAM_1", power_dbm=jammer_power),
        "Sweep (Süpürücü)":     create_sweep_jammer("JAM_1", power_dbm=jammer_power),
        "Jammer Yok":           None,
    }
    jammer = jammer_map.get(scenario_name)
    if jammer:
        ew.add_jammer(jammer)

    if scenario_name == "Barrage (Geniş Band)":
        sc = Scenario.create_barrage_scenario(duration=duration)
    elif scenario_name in ("Spot (Dar Band)", "Sweep (Süpürücü)"):
        from src.simulation.scenario import EventType
        sc = Scenario(scenario_name, duration=duration)
        sc.add_event(duration * 0.2, EventType.JAMMER_ON, "JAM_1")
        sc.add_event(duration * 0.7, EventType.JAMMER_OFF, "JAM_1")
    else:
        sc = Scenario("normal", duration=duration)

    engine = RuleBasedEngine(topo)
    runner = SimulationRunner(
        topology=topo, scenario=sc,
        message_rate=message_rate, tick_interval=tick,
        verbose=False, ew_calculator=ew, decision_engine=engine,
    )
    metrics = runner.run()

    return {
        "timestamps":        metrics.timestamps,
        "delivery_rates":    metrics.delivery_rates,
        "critical_rates":    metrics.critical_delivery_rates,
        "mis_scores":        metrics.mis_scores,
        "link_qualities":    metrics.avg_link_qualities,
        "summary":           metrics.get_summary(),
        "decisions":         engine.get_summary()["total_decisions"],
        "filtered":          metrics.messages_filtered,
        "node_modes":        {nid: n.mode.value for nid, n in topo.nodes.items()},
        "node_positions":    {nid: n.position for nid, n in topo.nodes.items()},
        "node_roles":        {nid: n.role.value for nid, n in topo.nodes.items()},
        "link_pairs":        [(ch.node_a, ch.node_b) for ch in topo.channels.values()],
    }


# ─── Yardımcı Plot Fonksiyonları ────────────────────────────────────
DARK_TEMPLATE = "plotly_dark"

def make_line_chart(x, y, title, color="#64ffda", yrange=None, ytickformat=None):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines", line=dict(color=color, width=2),
        fill="tozeroy", fillcolor=color.replace(")", ",0.08)").replace("rgb", "rgba") if color.startswith("rgb") else color + "14",
    ))
    fig.update_layout(
        template=DARK_TEMPLATE, title=title,
        margin=dict(l=10, r=10, t=40, b=10), height=200,
        xaxis_title="Zaman (s)", paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
    )
    if yrange:
        fig.update_yaxes(range=yrange)
    if ytickformat:
        fig.update_yaxes(tickformat=ytickformat)
    return fig


def make_network_map(result: dict):
    """Taktik ağ haritasını Plotly Scatter ile çizer."""
    positions = result["node_positions"]
    modes = result["node_modes"]
    roles = result["node_roles"]

    MODE_COLORS = {
        "normal":         "#64ffda",
        "degraded":       "#ffd700",
        "local_autonomy": "#ff9944",
        "silent":         "#bb86fc",
    }
    ROLE_SYMBOLS = {
        "command_center": "star",
        "sensor":         "circle",
        "relay":          "diamond",
        "weapon":         "triangle-up",
    }

    fig = go.Figure()

    # Linkleri çiz
    for a, b in result["link_pairs"]:
        ax, ay = positions[a]
        bx, by = positions[b]
        fig.add_trace(go.Scatter(
            x=[ax, bx], y=[ay, by],
            mode="lines",
            line=dict(color="#233554", width=2),
            hoverinfo="none", showlegend=False,
        ))

    # Düğümleri çiz
    for nid, (x, y) in positions.items():
        mode = modes.get(nid, "normal")
        role = roles.get(nid, "sensor")
        color = MODE_COLORS.get(mode, "#ffffff")
        symbol = ROLE_SYMBOLS.get(role, "circle")
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text",
            marker=dict(size=20, color=color, symbol=symbol,
                        line=dict(color=color, width=2)),
            text=[nid], textposition="top center",
            textfont=dict(color="#ccd6f6", size=11),
            name=nid,
            hovertemplate=f"<b>{nid}</b><br>Rol: {role}<br>Mod: {mode}<extra></extra>",
        ))

    fig.update_layout(
        template=DARK_TEMPLATE, showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10), height=320,
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x"),
    )
    return fig


# ─── SIDEBAR ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🛡️ SPECTRA")
    st.markdown("*Taktik Ağ Karar Motoru*")
    st.divider()

    st.markdown("### Senaryo")
    scenario = st.selectbox(
        "Jammer Tipi",
        ["Jammer Yok", "Barrage (Geniş Band)", "Spot (Dar Band)", "Sweep (Süpürücü)"],
        index=1,
    )

    jammer_power = st.slider("Jammer Gücü (dBm)", -90, -50, -70, step=2)
    duration = st.slider("Süre (s)", 30, 300, 100, step=10)
    message_rate = st.slider("Mesaj Üretim Hızı", 0.1, 2.0, 0.5, step=0.1)
    tick = st.selectbox("Tick Aralığı (s)", [0.5, 1.0, 2.0], index=1)

    st.divider()
    run_btn = st.button("▶️  Simülasyonu Çalıştır", type="primary", use_container_width=True)

    st.divider()
    st.markdown("### STM32 Edge Node")
    stm_mock = st.toggle("Mock Mod (STM32 yok)", value=True)
    if not stm_mock:
        stm_port = st.text_input("Port", "/dev/cu.usbmodem14103")
    else:
        stm_port = "MOCK"
    ping_btn = st.button("📡 Status İste", use_container_width=True)

    # STM32 mock durumu göster
    if ping_btn:
        from src.stm32.serial_bridge import SerialBridge
        from src.stm32.protocol import SpectraProtocol, Command
        bridge = SerialBridge(port=stm_port, mock=True)
        bridge.connect()
        bridge.request_status()
        time.sleep(0.4)
        pkts = bridge.get_all_received()
        bridge.disconnect()
        for p in pkts:
            if p.command == Command.STATUS_REPORT:
                s = SpectraProtocol.parse_status_report(p)
                if s:
                    st.success(f"Mod: **{s['mode']}** | Alert: {s['alert_level']} | Uptime: {s['uptime_s']}s")

    st.divider()
    st.caption("v0.5 | mehmetd7mir/SPECTRA")


# ─── ANA ALAN ────────────────────────────────────────────────────────
st.markdown("""
<div class="spectra-header">
<h2 style="color:#64ffda;margin:0;">SPECTRA</h2>
<span style="color:#8892b0;font-size:13px;">Mission-Impact Driven Spectrum Resilience & Tactical Network Orchestrator</span>
</div>
""", unsafe_allow_html=True)

# Simülasyon verisi session_state'te saklanır
if "result" not in st.session_state:
    st.session_state["result"] = None

if run_btn:
    with st.spinner("Simülasyon çalışıyor..."):
        result = run_simulation(scenario, jammer_power, duration, message_rate, float(tick))
        st.session_state["result"] = result

result = st.session_state["result"]

if result is None:
    st.info("👈 Sol panelden parametreleri ayarlayıp **Simülasyonu Çalıştır** butonuna bas.")
    st.stop()

# ─── Metrik Kartlar ──────────────────────────────────────────────────
s = result["summary"]
c1, c2, c3, c4, c5 = st.columns(5)

def quality_class(val, high=0.8, low=0.5):
    if val >= high: return "good"
    if val >= low:  return "warn"
    return "bad"

with c1:
    dr = s["delivery_rate"]
    st.markdown(f"""<div class='metric-card'>
    <div class='metric-label'>Delivery Rate</div>
    <div class='metric-value {quality_class(dr)}'>{dr:.0%}</div></div>""", unsafe_allow_html=True)

with c2:
    cr = s["critical_rate"]
    st.markdown(f"""<div class='metric-card'>
    <div class='metric-label'>Critical Rate</div>
    <div class='metric-value {quality_class(cr)}'>{cr:.0%}</div></div>""", unsafe_allow_html=True)

with c3:
    mis = s["avg_mis"]
    qc = quality_class(mis/100)
    st.markdown(f"""<div class='metric-card'>
    <div class='metric-label'>Avg MIS</div>
    <div class='metric-value {qc}'>{mis}</div></div>""", unsafe_allow_html=True)

with c4:
    st.markdown(f"""<div class='metric-card'>
    <div class='metric-label'>Karar Sayısı</div>
    <div class='metric-value'>{result['decisions']}</div></div>""", unsafe_allow_html=True)

with c5:
    st.markdown(f"""<div class='metric-card'>
    <div class='metric-label'>Filtrelenen Msg</div>
    <div class='metric-value warn'>{result['filtered']}</div></div>""", unsafe_allow_html=True)

st.divider()

# ─── Grafikler + Harita ───────────────────────────────────────────────
col_charts, col_map = st.columns([2, 1])

with col_charts:
    t = result["timestamps"]

    st.plotly_chart(
        make_line_chart(t, [v*100 for v in result["mis_scores"]],
                        "Mission Impact Score (MIS)", "#64ffda", [0, 105]),
        use_container_width=True,
    )

    c_del, c_qual = st.columns(2)
    with c_del:
        st.plotly_chart(
            make_line_chart(t, [v*100 for v in result["delivery_rates"]],
                            "Delivery Rate (%)", "#7ecef4", [0, 105], ".0f"),
            use_container_width=True,
        )
    with c_qual:
        st.plotly_chart(
            make_line_chart(t, result["link_qualities"],
                            "Ortalama Link Kalitesi", "#ffd700", [0, 1.05]),
            use_container_width=True,
        )

with col_map:
    st.markdown("#### 🗺️ Taktik Ağ Haritası")
    st.plotly_chart(make_network_map(result), use_container_width=True)

    st.markdown("#### 🔵 Düğüm Modları")
    for nid, mode in result["node_modes"].items():
        badge_class = "mode-" + mode.upper()
        st.markdown(
            f"`{nid}` <span class='mode-badge {badge_class}'>{mode.upper()}</span>",
            unsafe_allow_html=True,
        )

st.divider()

# ─── Özet Tablo ──────────────────────────────────────────────────────
st.markdown("#### 📊 Simülasyon Özeti")
df = pd.DataFrame([s]).T.rename(columns={0: "Değer"})
st.dataframe(df, use_container_width=True)
