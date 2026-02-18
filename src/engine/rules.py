"""
Rule-based decision engine.

projenin "beyni" - ağ durumunu analiz eder ve karar verir.

çalışma mantığı:
1. her düğümün bağlı olduğu linklerin kalitesine bak
2. MIS'a bak
3. kalite ve MIS eşiklere göre aksiyon belirle
4. safety gate'den geçir
5. kararı uygula

bu versiyon tamamen kural tabanlı (if-else).
faz 4'te ML modeli eklenecek ve ikisi birlikte çalışacak
(hibrit mimari).

# aslında kural tabanlı sistem çoğu durumda gayet iyi çalışır
# ML'in avantajı tahmin gücü - link kalitesinin GELECEKTE ne
# olacağını tahmin edip önceden aksiyon alabilir.
# ama kural tabanlı da gerekli çünkü açıklanabilir.
"""

import time
from typing import Dict, List, Optional

from .policy import NetworkPolicy, PolicyAction, PolicyDecision
from .safety_gate import SafetyGate
from ..network.topology import NetworkTopology
from ..network.node import TacticalNode, NodeMode
from ..network.channel import TacticalChannel


class RuleBasedEngine:
    """
    Kural tabanlı karar motoru.

    Parameters
    ----------
    topology : NetworkTopology
        ağ topolojisi
    policy : NetworkPolicy
        politika kuralları
    safety_gate : SafetyGate
        güvenlik katmanı
    """

    def __init__(
        self,
        topology: NetworkTopology,
        policy: Optional[NetworkPolicy] = None,
        safety_gate: Optional[SafetyGate] = None,
    ):
        self.topology = topology
        self.policy = policy or NetworkPolicy()
        self.safety = safety_gate or SafetyGate(
            mode_change_cooldown=self.policy.mode_change_cooldown
        )

        # karar geçmişi
        self.decisions: List[PolicyDecision] = []

        # aktif aksiyonlar (her düğüm için)
        self.active_actions: Dict[str, List[PolicyAction]] = {}

    def evaluate(self, mis_score: float, sim_time: float) -> List[PolicyDecision]:
        """
        tüm düğümleri değerlendir ve kararlar üret.

        Parameters
        ----------
        mis_score : float
            mevcut görev etki skoru (0-100)
        sim_time : float
            simülasyon zamanı

        Returns
        -------
        list of PolicyDecision
            her düğüm için kararlar
        """
        all_decisions = []

        for node_id, node in self.topology.nodes.items():
            if not node.is_online:
                continue

            # bu düğümün ortalama link kalitesini hesapla
            avg_quality = self._get_node_link_quality(node_id)

            # kural tabanlı karar
            decision = self._decide_for_node(
                node, avg_quality, mis_score, sim_time
            )

            if decision and decision.actions:
                # safety gate'den geçir
                safe_decision = self.safety.check(decision, sim_time)

                if safe_decision.actions:
                    # kararı uygula
                    self._apply_decision(safe_decision, node)
                    all_decisions.append(safe_decision)
                    self.decisions.append(safe_decision)

                    # aktif aksiyonları güncelle
                    self.active_actions[node_id] = safe_decision.actions

        return all_decisions

    def _get_node_link_quality(self, node_id: str) -> float:
        """düğümün bağlı olduğu linklerin ortalama kalitesi"""
        qualities = []
        for link_id, channel in self.topology.channels.items():
            if channel.node_a == node_id or channel.node_b == node_id:
                qualities.append(channel.link_quality)

        if not qualities:
            return 1.0
        return sum(qualities) / len(qualities)

    def _decide_for_node(
        self,
        node: TacticalNode,
        link_quality: float,
        mis_score: float,
        sim_time: float,
    ) -> Optional[PolicyDecision]:
        """
        tek bir düğüm için karar ver.

        karar ağacı:
        1. link kalitesi ve MIS'a göre mod belirle
        2. moda göre ek aksiyonlar ekle
        """
        actions = []
        reason_parts = []
        current_mode = node.mode

        # ---- MOD BELİRLE ----

        # ÇOK KÖTÜ: LOCAL_AUTONOMY gerekli
        if link_quality < self.policy.local_autonomy_threshold:
            if current_mode != NodeMode.LOCAL_AUTONOMY:
                actions.append(PolicyAction.SWITCH_LOCAL_AUTONOMY)
                reason_parts.append(f"quality={link_quality:.2f}<{self.policy.local_autonomy_threshold}")

            # sadece kritik mesajlar geçsin
            actions.append(PolicyAction.CRITICAL_ONLY)

        # KÖTÜ: DEGRADED moda geç
        elif link_quality < self.policy.degraded_threshold:
            if current_mode == NodeMode.NORMAL:
                actions.append(PolicyAction.SWITCH_DEGRADED)
                reason_parts.append(f"quality={link_quality:.2f}<{self.policy.degraded_threshold}")

            # düşük öncelikli mesajları at
            actions.append(PolicyAction.DROP_LOW_PRIORITY)
            actions.append(PolicyAction.COMPRESS_MESSAGES)
            actions.append(PolicyAction.REDUCE_TRAFFIC)

        # İYİ: NORMAL'e dönebilir (kademeli geri dönüş)
        elif link_quality > self.policy.normal_threshold:
            if current_mode == NodeMode.LOCAL_AUTONOMY:
                # önce DEGRADED'a geç, sonra NORMAL'e
                actions.append(PolicyAction.SWITCH_DEGRADED)
                reason_parts.append(f"recovering: quality={link_quality:.2f}>{self.policy.normal_threshold}")
            elif current_mode == NodeMode.DEGRADED:
                actions.append(PolicyAction.SWITCH_NORMAL)
                reason_parts.append(f"quality={link_quality:.2f}>{self.policy.normal_threshold}")

        # ORTA: LOCAL_AUTONOMY'den DEGRADED'a dönebilir
        elif link_quality > self.policy.degraded_threshold:
            if current_mode == NodeMode.LOCAL_AUTONOMY:
                actions.append(PolicyAction.SWITCH_DEGRADED)
                reason_parts.append(f"partial recovery: quality={link_quality:.2f}>{self.policy.local_autonomy_threshold}")

        # ---- MIS BAZLI EK AKSIYONLAR ----

        if mis_score < self.policy.mis_critical:
            actions.append(PolicyAction.ALERT_OPERATOR)
            if PolicyAction.DROP_ROUTINE not in actions:
                actions.append(PolicyAction.DROP_ROUTINE)
            reason_parts.append(f"MIS={mis_score:.0f}<{self.policy.mis_critical}")

        elif mis_score < self.policy.mis_warning:
            if PolicyAction.ALERT_OPERATOR not in actions:
                actions.append(PolicyAction.ALERT_OPERATOR)
            reason_parts.append(f"MIS={mis_score:.0f}<{self.policy.mis_warning}")

        # aksiyon yoksa karar verme
        if not actions:
            return None

        return PolicyDecision(
            actions=actions,
            target_node=node.node_id,
            reason="; ".join(reason_parts) if reason_parts else "routine",
            mis_at_decision=mis_score,
            link_quality=link_quality,
        )

    def _apply_decision(self, decision: PolicyDecision, node: TacticalNode):
        """kararı düğüme uygula"""
        for action in decision.actions:
            if action == PolicyAction.SWITCH_NORMAL:
                node.switch_mode(NodeMode.NORMAL, force=True)
            elif action == PolicyAction.SWITCH_DEGRADED:
                node.switch_mode(NodeMode.DEGRADED, force=True)
            elif action == PolicyAction.SWITCH_LOCAL_AUTONOMY:
                node.switch_mode(NodeMode.LOCAL_AUTONOMY, force=True)
            elif action == PolicyAction.SWITCH_SILENT:
                node.switch_mode(NodeMode.SILENT, force=True)
            # diğer aksiyonlar (DROP_LOW, COMPRESS vs.) runner tarafında
            # mesaj gönderme aşamasında uygulanacak

    def should_send_message(self, node: TacticalNode, msg_priority_value: int) -> bool:
        """
        bu mesaj gönderilmeli mi?

        düğümün moduna ve aktif filtreleme aksiyonlarına göre karar verir.
        runner.py bu fonksiyonu her mesaj gönderiminden önce çağıracak.
        """
        # max kabul edilen priority level
        max_priority = self.policy.get_priority_filter(node.mode.value)

        # mesaj bu seviyede mi veya daha önemli mi
        return msg_priority_value <= max_priority

    def get_compression_ratio(self, node: TacticalNode) -> float:
        """
        düğüm için mesaj sıkıştırma oranı.
        1.0 = sıkıştırma yok, 0.5 = yarı boyuta düşür
        """
        node_actions = self.active_actions.get(node.node_id, [])
        if PolicyAction.COMPRESS_MESSAGES in node_actions:
            return self.policy.compress_ratio
        return 1.0

    def get_traffic_factor(self, node: TacticalNode) -> float:
        """
        trafik azaltma faktörü.
        1.0 = normal, 0.5 = yarı hızda mesaj üret
        """
        node_actions = self.active_actions.get(node.node_id, [])
        if PolicyAction.REDUCE_TRAFFIC in node_actions:
            return self.policy.reduce_traffic_factor
        return 1.0

    def get_summary(self) -> dict:
        """karar motoru özeti"""
        mode_dist = {}
        for node in self.topology.nodes.values():
            m = node.mode.value
            mode_dist[m] = mode_dist.get(m, 0) + 1

        return {
            "total_decisions": len(self.decisions),
            "node_modes": mode_dist,
            "safety_stats": self.safety.get_stats(),
            "active_actions": {
                k: [a.value for a in v]
                for k, v in self.active_actions.items()
                if v
            },
        }

    def __repr__(self):
        return (
            f"RuleEngine: {len(self.decisions)} decisions, "
            f"safety={self.safety}"
        )
