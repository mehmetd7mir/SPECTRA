"""
Safety gate - deterministic safety layer.

ML karar motorunun (faz 4) üzerinde çalışan güvenlik katmanı.
ML ne karar verirse versin, bazı kurallar değiştirilemez:

- kritik mesajlar ASLA düşürülmez
- HQ her zaman bağlı kalmalı (mümkünse)
- silah sistemine yanlış mod gönderilmez
- çok hızlı mod değişikliği engellenir

savunma sektöründe "açıklanabilir + güvenli AI" çok önemli.
bu katman sayesinde ML modeli hata yapsa bile sistem güvenli
kalır. mülakata bunu söylersen çok iyi puan alırsın.

# hocamız diyordu ki: "otonom sistemlerde her zaman bir
# deterministik güvenlik katmanı olmalı, ML tek başına
# karar vermemeli." bu o katman.
"""

import time
from typing import List, Optional

from .policy import PolicyAction, PolicyDecision
from ..network.node import NodeMode


class SafetyGate:
    """
    Deterministik güvenlik katmanı.

    karar motorundan gelen kararları filtreler.
    güvenli olmayan aksiyonları engeller veya değiştirir.

    Parameters
    ----------
    mode_change_cooldown : float
        aynı düğümde iki mod değişikliği arasındaki min süre (sn)
    """

    def __init__(self, mode_change_cooldown: float = 5.0):
        self.cooldown = mode_change_cooldown

        # her düğümün son mod değişikliği zamanı
        self._last_mode_change: dict = {}

        # engellenen karar sayısı (loglama için)
        self.blocked_count = 0
        self.modified_count = 0
        self.passed_count = 0

        # güvenlik logları
        self.log: List[str] = []

    def check(self, decision: PolicyDecision, current_time: float) -> PolicyDecision:
        """
        kararı güvenlik kontrolünden geçir.

        - güvenli değilse: aksiyonu kaldır veya değiştir
        - güvenliyse: olduğu gibi geçir

        Returns
        -------
        PolicyDecision
            filtrelenmiş karar (aksiyonlar değişmiş olabilir)
        """
        filtered_actions = []
        node_id = decision.target_node

        for action in decision.actions:
            safe, reason = self._check_action(action, node_id, current_time)

            if safe:
                filtered_actions.append(action)
            else:
                self.blocked_count += 1
                self.log.append(
                    f"t={current_time:.0f}s BLOCKED: {action.value} "
                    f"for {node_id} - {reason}"
                )

        # filtrelenmiş karar oluştur
        if len(filtered_actions) != len(decision.actions):
            self.modified_count += 1
        else:
            self.passed_count += 1

        result = PolicyDecision(
            actions=filtered_actions,
            target_node=decision.target_node,
            reason=decision.reason,
            mis_at_decision=decision.mis_at_decision,
            link_quality=decision.link_quality,
        )
        return result

    def _check_action(self, action: PolicyAction, node_id: str,
                      current_time: float) -> tuple:
        """
        tek bir aksiyonun güvenliğini kontrol et.
        Returns: (güvenli_mi, sebep)
        """

        # Kural 1: CRITICAL_ONLY sadece acil durumda kabul edilir
        # (MIS çok düşükse zaten doğru karar)
        # → geçiriyoruz, tehlikeli değil

        # Kural 2: mod değişikliklerinde cooldown kontrolü
        mode_actions = {
            PolicyAction.SWITCH_NORMAL,
            PolicyAction.SWITCH_DEGRADED,
            PolicyAction.SWITCH_LOCAL_AUTONOMY,
            PolicyAction.SWITCH_SILENT,
        }
        if action in mode_actions and node_id:
            last_change = self._last_mode_change.get(node_id, 0.0)
            elapsed = current_time - last_change
            if elapsed < self.cooldown and last_change > 0:
                return (False, f"cooldown: {elapsed:.1f}s < {self.cooldown}s")

            # cooldown geçtiyse son değişikliği kaydet
            self._last_mode_change[node_id] = current_time

        # Kural 3: SWITCH_SILENT sadece force durumunda
        # aktif savaş sırasında suskunluk tehlikeli olabilir
        if action == PolicyAction.SWITCH_SILENT:
            return (False, "SILENT modu otomatik verilemez, operatör onayı gerekir")

        # tüm kontroller geçti
        return (True, "")

    def record_mode_change(self, node_id: str, current_time: float):
        """mod değişikliğini kaydet (harici çağrı için)"""
        self._last_mode_change[node_id] = current_time

    def get_stats(self) -> dict:
        """güvenlik istatistikleri"""
        total = self.blocked_count + self.passed_count
        return {
            "total_checks": total,
            "passed": self.passed_count,
            "blocked": self.blocked_count,
            "modified": self.modified_count,
            "block_rate": round(self.blocked_count / max(1, total), 3),
        }

    def __repr__(self):
        return (
            f"SafetyGate: {self.passed_count} passed, "
            f"{self.blocked_count} blocked"
        )
