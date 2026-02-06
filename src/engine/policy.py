"""
Network policy definitions and actions.

karar motoru "ne yapacağını" burada tanımlanan politika
aksiyonları (PolicyAction) üzerinden ifade eder.

örneğin:
  - link kalitesi %30 altına düşerse → DEGRADED moda geç
  - DEGRADED modda → sadece CRITICAL ve HIGH mesajları gönder
  - LOCAL_AUTONOMY → hiç mesaj gönderme, yerel karar ver

# farklı politikaları karşılaştırarak hangisinin daha iyi
# çalıştığını görmek ilginç olacak, faz 4'te ML ile optimize
# edebiliriz belki
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class PolicyAction(Enum):
    """karar motorunun verebileceği aksiyonlar"""
    # mod değişikliği
    SWITCH_NORMAL = "switch_normal"
    SWITCH_DEGRADED = "switch_degraded"
    SWITCH_LOCAL_AUTONOMY = "switch_local_autonomy"
    SWITCH_SILENT = "switch_silent"

    # mesaj filtreleme
    DROP_LOW_PRIORITY = "drop_low_priority"        # LOW mesajları at
    DROP_ROUTINE = "drop_routine"                   # ROUTINE de at
    CRITICAL_ONLY = "critical_only"                 # sadece CRITICAL geçir

    # ağ adaptasyonu
    COMPRESS_MESSAGES = "compress_messages"          # mesaj boyutunu küçült
    INCREASE_RETRY = "increase_retry"                # tekrar deneme artır
    REDUCE_TRAFFIC = "reduce_traffic"                # mesaj üretimini azalt
    REROUTE = "reroute"                              # alternatif rota kullan

    # uyarılar
    ALERT_OPERATOR = "alert_operator"                # operatöre bildir


@dataclass
class PolicyDecision:
    """
    karar motorunun bir adımdaki kararı.

    birden fazla aksiyon aynı anda uygulanabilir
    örn: SWITCH_DEGRADED + DROP_LOW_PRIORITY + ALERT_OPERATOR
    """
    actions: List[PolicyAction] = field(default_factory=list)
    target_node: Optional[str] = None    # hangi düğüm için
    reason: str = ""                      # neden bu karar verildi
    mis_at_decision: float = 0.0          # karar anındaki MIS
    link_quality: float = 0.0            # karar anındaki link kalitesi

    def __repr__(self):
        acts = ", ".join(a.value for a in self.actions)
        return f"Decision({acts}) → {self.target_node} | reason: {self.reason}"


class NetworkPolicy:
    """
    Ağ politikası tanımları.

    eşik değerlerini tutar - karar motoru bu eşiklere
    bakarak hangi aksiyonu uygulayacağını belirler.

    Parameters
    ----------
    name : str
        politika adı (karşılaştırma için)
    """

    def __init__(self, name: str = "default"):
        self.name = name

        # --- mod geçiş eşikleri ---
        # link kalitesi bu değerlerin altına düşünce mod değişir
        self.degraded_threshold = 0.5       # < 0.5 → DEGRADED
        self.local_autonomy_threshold = 0.15 # < 0.15 → LOCAL_AUTONOMY
        self.normal_threshold = 0.7          # > 0.7 → NORMAL'e dön

        # --- MIS eşikleri ---
        self.mis_warning = 70.0     # MIS < 70 → uyarı
        self.mis_critical = 40.0    # MIS < 40 → acil önlem

        # --- mesaj filtreleme ---
        # DEGRADED modda hangi öncelik seviyelerine kadar kabul et
        # 1=CRITICAL, 2=HIGH, 3=ROUTINE, 4=LOW
        self.degraded_max_priority = 2      # HIGH ve üstü geçer
        self.local_max_priority = 1         # sadece CRITICAL geçer

        # --- trafik kontrolü ---
        self.reduce_traffic_factor = 0.5    # DEGRADED'da %50 azalt
        self.compress_ratio = 0.6           # mesaj boyutunu %60'a düşür

        # --- histerezis ---
        # mod geçişlerinde salınımı önlemek için bekleme süresi
        # yoksa link kalitesi eşik civarında sallanınca sürekli
        # mod değişir, bu kötü
        # # TODO: histeresis süreleri biraz deneysel, sonra ayarlarız
        self.mode_change_cooldown = 5.0     # en az 5 saniye bekle

    def get_priority_filter(self, node_mode_value: str) -> int:
        """
        mod'a göre kabul edilecek max priority level.
        dönen değer ve altındaki mesajlar geçer.

        NORMAL: 4 (hepsi geçer)
        DEGRADED: 2 (HIGH ve CRITICAL)
        LOCAL_AUTONOMY: 1 (sadece CRITICAL)
        """
        filters = {
            "NORMAL": 4,
            "DEGRADED": self.degraded_max_priority,
            "LOCAL_AUTONOMY": self.local_max_priority,
            "SILENT": 0,  # hiçbiri
        }
        return filters.get(node_mode_value, 4)

    def __repr__(self):
        return (
            f"Policy('{self.name}') "
            f"degraded<{self.degraded_threshold} "
            f"local<{self.local_autonomy_threshold}"
        )
