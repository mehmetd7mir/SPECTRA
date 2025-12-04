"""
Simulation runner - the main simulation loop.

bu dosya tüm parçaları birleştirir:
- topolojiyi yükler
- senaryoyu yükler
- zaman adımlı simülasyonu koşturur
- her adımda:
  1. senaryo olaylarını uygula (jammer aç/kapat vs)
  2. düğümlerden mesaj üret
  3. mesajları ağ üzerinden gönder
  4. metrikleri topla
- sonuçları raporla

# event-driven simülasyon da düşündüm ama discrete-time daha
# basit ve anlaması kolay. her tick = 1 saniye simülasyon zamanı.
"""

import time
import random
import numpy as np
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

from ..network.topology import NetworkTopology
from ..network.node import TacticalNode, NodeRole, NodeMode
from ..network.channel import TacticalChannel
from ..network.message import (
    TacticalMessage, MessageType, MessagePriority,
    create_track_update, create_threat_alert,
    create_health_report, create_command,
)
from .scenario import Scenario, ScenarioEvent, EventType


@dataclass
class SimulationMetrics:
    """
    simülasyon metrikleri - her adımda güncellenir.
    sonunda bunları grafiklerle göstereceğiz.
    """
    # zaman serisi verileri
    timestamps: List[float] = field(default_factory=list)
    delivery_rates: List[float] = field(default_factory=list)
    critical_delivery_rates: List[float] = field(default_factory=list)
    avg_delays: List[float] = field(default_factory=list)
    avg_link_qualities: List[float] = field(default_factory=list)
    mis_scores: List[float] = field(default_factory=list)         # görev etki skoru
    messages_filtered: int = 0     # karar motoru tarafından engellenen mesajlar

    # mesaj istatistikleri - tüm simülasyon boyunca kümülatif
    total_sent: int = 0
    total_delivered: int = 0
    total_lost: int = 0
    critical_sent: int = 0
    critical_delivered: int = 0

    # periyot bazlı (her tick'te sıfırlanır) - anlık değerler için
    _period_sent: int = 0
    _period_delivered: int = 0
    _period_critical_sent: int = 0
    _period_critical_delivered: int = 0
    _period_delays: List[float] = field(default_factory=list)

    def record_send(self, msg: TacticalMessage, success: bool, delay: float = 0):
        """bir mesaj gönderimini kaydet"""
        self.total_sent += 1
        self._period_sent += 1

        if msg.is_critical:
            self.critical_sent += 1
            self._period_critical_sent += 1

        if success:
            self.total_delivered += 1
            self._period_delivered += 1
            self._period_delays.append(delay)
            if msg.is_critical:
                self.critical_delivered += 1
                self._period_critical_delivered += 1
        else:
            self.total_lost += 1

    def end_period(self, timestamp: float, avg_quality: float):
        """periyot sonu - metrikleri kaydet ve sıfırla"""
        self.timestamps.append(timestamp)

        # delivery rate
        if self._period_sent > 0:
            self.delivery_rates.append(
                self._period_delivered / self._period_sent
            )
        else:
            self.delivery_rates.append(1.0)

        # critical delivery rate
        if self._period_critical_sent > 0:
            self.critical_delivery_rates.append(
                self._period_critical_delivered / self._period_critical_sent
            )
        else:
            # kritik mesaj yoksa önceki değeri koru
            prev = self.critical_delivery_rates[-1] if self.critical_delivery_rates else 1.0
            self.critical_delivery_rates.append(prev)

        # ortalama gecikme
        if self._period_delays:
            self.avg_delays.append(
                sum(self._period_delays) / len(self._period_delays)
            )
        else:
            self.avg_delays.append(0.0)

        # link kalitesi
        self.avg_link_qualities.append(avg_quality)

    def record_mis(self, mis_score: float):
        """görev etki skorunu kaydet"""
        self.mis_scores.append(mis_score)

        # sıfırla
        self._period_sent = 0
        self._period_delivered = 0
        self._period_critical_sent = 0
        self._period_critical_delivered = 0
        self._period_delays = []

    def get_summary(self) -> dict:
        """sonuç özeti"""
        return {
            "total_sent": self.total_sent,
            "total_delivered": self.total_delivered,
            "total_lost": self.total_lost,
            "filtered": self.messages_filtered,
            "delivery_rate": round(self.total_delivered / max(1, self.total_sent), 3),
            "critical_sent": self.critical_sent,
            "critical_delivered": self.critical_delivered,
            "critical_rate": round(
                self.critical_delivered / max(1, self.critical_sent), 3
            ),
            "avg_delay_ms": round(
                np.mean(self.avg_delays) if self.avg_delays else 0, 2
            ),
            "avg_mis": round(
                np.mean(self.mis_scores) if self.mis_scores else 100, 1
            ),
        }


class SimulationRunner:
    """
    Ana simülasyon koşturucusu.

    topolojiyi ve senaryoyu alır, zaman adımlı simülasyonu koşturur.

    Parameters
    ----------
    topology : NetworkTopology
        ağ topolojisi
    scenario : Scenario, optional
        uygulanacak senaryo. None ise normal durum (bozulma yok)
    tick_interval : float
        simülasyon adım aralığı (saniye)
    message_rate : float
        her düğümün saniyede ürettiği ortalama mesaj sayısı
    verbose : bool
        adım adım detay yazdır mı
    """

    def __init__(
        self,
        topology: NetworkTopology,
        scenario: Optional[Scenario] = None,
        tick_interval: float = 1.0,
        message_rate: float = 0.5,
        verbose: bool = False,
        ew_calculator=None,
        decision_engine=None,
    ):
        self.topology = topology
        self.scenario = scenario
        self.tick_interval = tick_interval
        self.message_rate = message_rate
        self.verbose = verbose

        # EW ve karar motoru (opsiyonel, onsuz da çalışır)
        self.ew = ew_calculator
        self.engine = decision_engine

        # simülasyon durumu
        self.current_time = 0.0
        self.is_running = False
        self.metrics = SimulationMetrics()

        # ek callback (test veya harici entegrasyon için)
        self.decision_callback: Optional[Callable] = None

    def run(self, duration: Optional[float] = None) -> SimulationMetrics:
        """
        simülasyonu koştur.

        Parameters
        ----------
        duration : float, optional
            süre. None ise senaryo süresini kullanır.

        Returns
        -------
        SimulationMetrics
            simülasyon sonuç metrikleri
        """
        if duration is None:
            duration = self.scenario.duration if self.scenario else 60.0

        self.current_time = 0.0
        self.is_running = True
        self.metrics = SimulationMetrics()

        if self.scenario:
            self.scenario.reset()

        total_ticks = int(duration / self.tick_interval)

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"SİMÜLASYON BAŞLIYOR")
            print(f"  Süre: {duration}s | Tick: {self.tick_interval}s")
            print(f"  Düğüm: {len(self.topology.nodes)} | Link: {len(self.topology.channels)}")
            if self.scenario:
                print(f"  Senaryo: {self.scenario.name} ({len(self.scenario.events)} olay)")
            print(f"{'='*60}\n")

        for tick in range(total_ticks):
            self.current_time = tick * self.tick_interval

            # 1. senaryo olaylarını uygula
            if self.scenario:
                events = self.scenario.check_events(self.current_time)
                for event in events:
                    self._apply_event(event)

            # 2. EW etkilerini güncelle
            mis_score = 100.0
            if self.ew:
                self.ew.update(self.current_time)
                mis_score = self.ew.current_mis.overall

            # 3. karar motoru çalıştır
            if self.engine:
                self.engine.evaluate(mis_score, self.current_time)

            # 4. mesaj üret
            messages = self._generate_messages()

            # 5. mesajları filtrele + gönder
            for msg in messages:
                # karar motoru aktifse mesaj filtreleme uygula
                if self.engine:
                    src_node = self.topology.nodes.get(msg.source)
                    if src_node and not self.engine.should_send_message(src_node, msg.priority.value):
                        self.metrics.messages_filtered += 1
                        continue  # mesaj engellendi

                result = self.topology.send_message(msg, self.current_time)
                self.metrics.record_send(
                    msg, result["success"], result["total_delay_ms"]
                )

            # 6. ek callback
            if self.decision_callback:
                self.decision_callback(self)

            # 7. metrikleri kaydet
            net_status = self.topology.get_network_status()
            self.metrics.end_period(
                self.current_time,
                net_status["avg_link_quality"],
            )
            self.metrics.record_mis(mis_score)

            # verbose çıktı - her 10 saniyede bir
            if self.verbose and tick % 10 == 0:
                dr = self.metrics.delivery_rates[-1] if self.metrics.delivery_rates else 1.0
                cr = self.metrics.critical_delivery_rates[-1] if self.metrics.critical_delivery_rates else 1.0
                q = net_status["avg_link_quality"]
                # düğüm mod bilgisi
                modes = {}
                for n in self.topology.nodes.values():
                    m = n.mode.value[:3]  # kısa göster
                    modes[m] = modes.get(m, 0) + 1
                mode_str = " ".join(f"{k}:{v}" for k, v in modes.items())
                print(
                    f"  t={self.current_time:5.0f}s | "
                    f"del={dr:.0%} crit={cr:.0%} | "
                    f"MIS={mis_score:5.1f} q={q:.2f} | "
                    f"{mode_str}"
                )

        self.is_running = False

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"SİMÜLASYON BİTTİ")
            summary = self.metrics.get_summary()
            for k, v in summary.items():
                print(f"  {k}: {v}")
            print(f"{'='*60}")

        return self.metrics

    def _apply_event(self, event: ScenarioEvent):
        """senaryo olayını uygula"""

        if self.verbose:
            print(f"  ⚡ t={self.current_time:.0f}s: {event}")

        if event.event_type == EventType.JAMMER_ON:
            # EW modülü varsa jammer objesini aktive et
            if self.ew and event.target in self.ew.jammers:
                jammer = self.ew.jammers[event.target]
                jammer.total_power_dbm = event.params.get("power_dbm", jammer.total_power_dbm)
                jammer.activate()
            else:
                # fallback: kanala direkt uygula
                ch = self._find_channel(event.target)
                if ch:
                    ch.apply_jamming(event.params.get("jamming_db", 15.0))

        elif event.event_type == EventType.JAMMER_OFF:
            if self.ew and event.target in self.ew.jammers:
                self.ew.jammers[event.target].deactivate()
            else:
                ch = self._find_channel(event.target)
                if ch:
                    ch.clear_jamming()

        elif event.event_type == EventType.JAMMER_CHANGE:
            if self.ew and event.target in self.ew.jammers:
                jammer = self.ew.jammers[event.target]
                jammer.total_power_dbm = event.params.get("power_dbm", jammer.total_power_dbm)
            else:
                ch = self._find_channel(event.target)
                if ch:
                    ch.apply_jamming(event.params.get("jamming_db", 15.0))

        elif event.event_type == EventType.NODE_FAIL:
            node = self.topology.nodes.get(event.target)
            if node:
                node.is_online = False
                node.switch_mode(NodeMode.SILENT, force=True)

        elif event.event_type == EventType.NODE_RECOVER:
            node = self.topology.nodes.get(event.target)
            if node:
                node.is_online = True
                node.switch_mode(NodeMode.NORMAL, force=True)

        elif event.event_type == EventType.LINK_CUT:
            ch = self._find_channel(event.target)
            if ch:
                ch.state.is_active = False

        elif event.event_type == EventType.LINK_RESTORE:
            ch = self._find_channel(event.target)
            if ch:
                ch.state.is_active = True
                ch._update_state()

    def _generate_messages(self) -> List[TacticalMessage]:
        """
        her düğümden mesaj üret.

        sensor düğümler → track update + bazen threat alert
        tüm düğümler → periyodik health report
        komuta merkezi → ara sıra command

        message_rate ile kontrol edilir (poisson dağılımı)
        """
        messages = []

        for node_id, node in self.topology.nodes.items():
            # offline düğümler mesaj üretmez
            if not node.is_online:
                continue
            # SILENT modda mesaj gönderilmez
            if node.mode == NodeMode.SILENT:
                continue

            # poisson dağılımıyla rastgele mesaj sayısı
            n_messages = np.random.poisson(self.message_rate)

            for _ in range(n_messages):
                msg = self._create_random_message(node)
                if msg:
                    messages.append(msg)

        return messages

    def _create_random_message(self, node: TacticalNode) -> Optional[TacticalMessage]:
        """düğüm rolüne göre rastgele mesaj üret"""

        # komuta merkezi → diğer düğümlere komut gönderir
        if node.role == NodeRole.COMMAND_CENTER:
            targets = [n for n in self.topology.nodes if n != node.node_id]
            if not targets:
                return None
            target = random.choice(targets)

            if random.random() < 0.3:
                return create_command(node.node_id, target, "STATUS_REQUEST")
            else:
                return create_health_report(
                    node.node_id, target,
                    {"hq_status": "operational"}
                )

        # sensör → track update + nadiren threat alert
        elif node.role == NodeRole.SENSOR:
            dest = "HQ"  # sensörler HQ'ya rapor verir

            if random.random() < 0.1:
                # %10 ihtimalle tehdit tespit
                return create_threat_alert(
                    node.node_id, dest,
                    {
                        "type": random.choice(["drone", "missile", "aircraft"]),
                        "bearing": random.randint(0, 360),
                        "range_km": round(random.uniform(1, 50), 1),
                    }
                )
            else:
                # normal track update
                return create_track_update(
                    node.node_id, dest,
                    {
                        "target_id": random.randint(1, 100),
                        "pos": [
                            node.position[0] + random.randint(-200, 200),
                            node.position[1] + random.randint(-200, 200),
                        ],
                        "velocity": round(random.uniform(0, 100), 1),
                    }
                )

        # relay → sadece health report (kendisi mesaj üretmez, iletir)
        elif node.role == NodeRole.RELAY:
            if random.random() < 0.3:
                return create_health_report(
                    node.node_id, "HQ",
                    {"link_quality": random.uniform(0.5, 1.0)}
                )
            return None

        # silah sistemi → health report + ACK
        elif node.role == NodeRole.WEAPON:
            if random.random() < 0.3:
                return create_health_report(
                    node.node_id, "HQ",
                    {"ammo": random.randint(0, 100), "status": "ready"}
                )
            return None

        return None

    def _find_channel(self, target: str) -> Optional[TacticalChannel]:
        """
        olay hedefinden kanalı bul.
        target formatı: "NODE_A_NODE_B" veya direkt link id
        """
        # direkt id ile ara
        if target in self.topology.channels:
            return self.topology.channels[target]

        # düğüm çiftinden bul
        parts = target.split("_", 1)
        if len(parts) == 2:
            return self.topology.get_channel(parts[0], parts[1])

        return None


# ---- doğrudan çalıştırma ----
if __name__ == "__main__":
    from ..ew.spectrum import SpectrumEnvironment
    from ..ew.jammer import create_barrage_jammer
    from ..ew.effects import EWEffectCalculator
    from ..engine.rules import RuleBasedEngine

    # tam entegre simülasyon: ağ + EW + karar motoru
    topo = NetworkTopology.from_yaml("config/network.yaml")
    spectrum = SpectrumEnvironment()
    ew = EWEffectCalculator(spectrum, topo)
    engine = RuleBasedEngine(topo)

    # jammer ekle (senaryo ile aktif/pasif olacak)
    jammer = create_barrage_jammer(power_dbm=-70.0)
    ew.add_jammer(jammer)

    scenario = Scenario.create_barrage_scenario(duration=100)

    runner = SimulationRunner(
        topology=topo,
        scenario=scenario,
        tick_interval=1.0,
        message_rate=0.5,
        verbose=True,
        ew_calculator=ew,
        decision_engine=engine,
    )

    metrics = runner.run()
    summary = metrics.get_summary()
    print(f"\nÖzet: {summary}")
