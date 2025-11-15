"""
Tactical node model - represents one node in the network.

her düğüm (node) taktik ağda bir birim temsil eder:
- komuta merkezi (HQ)
- aktarıcı (relay)
- sensör (radar, kamera vs)
- silah sistemi

her düğümün bir modu var. normal durumda hepsi NORMAL modda,
ama ağ bozulunca DEGRADED veya LOCAL_AUTONOMY moduna geçebilir.
bu geçişler karar motoruyla yapılacak (faz 3'te).

# not: gerçek sistemlerde her düğüm bir bilgisayar veya STM32 gibi
# bir mikrodenetleyici üzerinde çalışır. biz simülasyonda python objesi
# olarak temsil ediyoruz, faz 5'te gerçek STM32 bağlanacak.
"""

import time
import heapq
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from .message import TacticalMessage, MessagePriority


class NodeRole(Enum):
    """
    düğüm rolleri. her rolün ağdaki görevi farklı.
    """
    COMMAND_CENTER = "command_center"  # HQ - komut verir, bilgi toplar
    RELAY = "relay"                    # veri aktarır, kendisi üretmez
    SENSOR = "sensor"                  # hedef tespit eder, track gönderir
    WEAPON = "weapon"                  # silah sistemi, komut bekler


class NodeMode(Enum):
    """
    düğüm çalışma modları. EW baskısına göre değişir.

    NORMAL:         her şey yolunda, tam haberleşme
    DEGRADED:       kanal bozuk ama hala bağlı, önceliklendirme aktif
    LOCAL_AUTONOMY: bağlantı koptu veya çok kötü, kendi başına karar ver
    SILENT:         radyo sessizliği, hiç yayın yapma (EMCON)

    # TODO: belki EMERGENCY modu da eklemeliyiz ama simdilik 4 yeter
    """
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    LOCAL_AUTONOMY = "LOCAL_AUTONOMY"
    SILENT = "SILENT"


# hangi moddan hangi moda geçiş yapılabilir?
# her geçiş legal değil - direk SILENT'tan NORMAL'a geçemezsin mesela
VALID_TRANSITIONS = {
    NodeMode.NORMAL: [NodeMode.DEGRADED, NodeMode.SILENT],
    NodeMode.DEGRADED: [NodeMode.NORMAL, NodeMode.LOCAL_AUTONOMY, NodeMode.SILENT],
    NodeMode.LOCAL_AUTONOMY: [NodeMode.DEGRADED, NodeMode.SILENT],
    NodeMode.SILENT: [NodeMode.NORMAL, NodeMode.DEGRADED],
}


@dataclass
class NodeStats:
    """düğüm istatistikleri - performans takibi için"""
    messages_sent: int = 0
    messages_received: int = 0
    messages_dropped: int = 0      # kuyruk dolu veya priority düşük
    messages_expired: int = 0      # TTL geçmiş
    bytes_sent: int = 0
    bytes_received: int = 0
    mode_changes: int = 0
    last_mode_change: float = 0.0


class TacticalNode:
    """
    Taktik ağdaki bir düğüm.

    mesaj kuyruğu priority queue olarak çalışır - yüksek öncelikli
    mesajlar önce gönderilir. kuyruk boyutu sınırlıdır, dolduğunda
    en düşük öncelikli mesaj düşürülür.

    Parameters
    ----------
    node_id : str
        düğüm kimliği, örn: "HQ", "SENSOR_A"
    role : NodeRole
        düğümün rolü
    position : tuple
        (x, y) koordinatları (metre cinsinden, harita üzerinde)
    queue_size : int
        maksimum mesaj kuyruğu boyutu
    """

    def __init__(
        self,
        node_id: str,
        role: NodeRole,
        position: Tuple[float, float] = (0, 0),
        queue_size: int = 50,
    ):
        self.node_id = node_id
        self.role = role
        self.position = position
        self.queue_size = queue_size

        # çalışma durumu
        self.mode = NodeMode.NORMAL
        self.health_score = 100.0   # 0-100, düşerse sorun var
        self.is_online = True

        # mesaj kuyruğu - heapq ile priority queue
        # heapq min-heap olduğu için priority değeri küçük olan önce çıkar
        # (CRITICAL=1 < LOW=4) bu yüzden direkt çalışır
        self._msg_queue: List[Tuple[int, float, TacticalMessage]] = []
        self._queue_counter = 0  # aynı priority'de sıralama için

        # istatistikler
        self.stats = NodeStats()

        # bağlı komşu düğümler (topology.py'de doldurulacak)
        self.neighbors: List[str] = []

        # sensör verileri (STM32'den gelecek, şimdilik simüle)
        self.sensor_data: Dict[str, float] = {
            "temperature": 25.0,
            "light_level": 0.5,
            "proximity": 100.0,
            "priority_dial": 0.5,  # potansiyometre değeri (0-1)
        }

    def enqueue_message(self, msg: TacticalMessage) -> bool:
        """
        mesajı gönderim kuyruğuna ekle.

        kuyruk doluysa en düşük öncelikli mesajı düşürür ve yerine koyar.
        ama yeni mesajın önceliği daha düşükse direkt reddeder.

        Returns True if message was queued, False if rejected
        """
        # kuyruk doluysa
        if len(self._msg_queue) >= self.queue_size:
            # en düşük öncelikli mesajı bul (en büyük priority değeri)
            worst = max(self._msg_queue, key=lambda x: x[0])

            # yeni mesaj daha önemliyse (daha küçük priority)
            if msg.priority.value < worst[0]:
                self._msg_queue.remove(worst)
                heapq.heapify(self._msg_queue)
                self.stats.messages_dropped += 1
            else:
                # yeni mesaj daha az önemli, reddet
                self.stats.messages_dropped += 1
                return False

        # kuyruğa ekle
        self._queue_counter += 1
        heapq.heappush(
            self._msg_queue,
            (msg.priority.value, self._queue_counter, msg)
        )
        return True

    def dequeue_message(self) -> Optional[TacticalMessage]:
        """
        kuyruktan en yüksek öncelikli mesajı al.
        kuyruk boşsa None döner.
        """
        if not self._msg_queue:
            return None

        _, _, msg = heapq.heappop(self._msg_queue)

        # süresi geçmişse at, sonrakini dene
        current_time = time.time()
        while msg.is_expired(current_time):
            self.stats.messages_expired += 1
            if not self._msg_queue:
                return None
            _, _, msg = heapq.heappop(self._msg_queue)

        self.stats.messages_sent += 1
        self.stats.bytes_sent += msg.size_bytes
        return msg

    def receive_message(self, msg: TacticalMessage):
        """gelen mesajı kaydet"""
        self.stats.messages_received += 1
        self.stats.bytes_received += msg.size_bytes

    def switch_mode(self, new_mode: NodeMode, force: bool = False) -> bool:
        """
        düğüm modunu değiştir.

        geçiş kurallarına uyulur - her moddan her moda geçemezsin.
        force=True ile kurallar atlanabilir (acil durum için).

        Returns True if mode changed successfully
        """
        if new_mode == self.mode:
            return True  # zaten bu modda

        # geçiş legal mi kontrol et
        if not force and new_mode not in VALID_TRANSITIONS.get(self.mode, []):
            return False

        old_mode = self.mode
        self.mode = new_mode
        self.stats.mode_changes += 1
        self.stats.last_mode_change = time.time()

        return True

    @property
    def queue_usage(self) -> float:
        """kuyruk doluluk oranı (0.0 - 1.0)"""
        return len(self._msg_queue) / self.queue_size

    @property
    def queue_length(self) -> int:
        """kuyrukta kaç mesaj var"""
        return len(self._msg_queue)

    def update_health(self, score: float):
        """
        sağlık skorunu güncelle.
        sensör verileri, kuyruk durumu vs. baz alınarak hesaplanır.
        0 = çok kötü, 100 = mükemmel
        """
        self.health_score = max(0.0, min(100.0, score))

    def get_status(self) -> dict:
        """düğüm durumu özeti - dashboard ve log için"""
        return {
            "node_id": self.node_id,
            "role": self.role.value,
            "mode": self.mode.value,
            "health": round(self.health_score, 1),
            "online": self.is_online,
            "queue": f"{self.queue_length}/{self.queue_size}",
            "queue_usage": round(self.queue_usage, 2),
            "position": self.position,
            "sent": self.stats.messages_sent,
            "received": self.stats.messages_received,
            "dropped": self.stats.messages_dropped,
        }

    def __repr__(self):
        mode_icons = {
            NodeMode.NORMAL: "🟢",
            NodeMode.DEGRADED: "🟡",
            NodeMode.LOCAL_AUTONOMY: "🟠",
            NodeMode.SILENT: "🔴",
        }
        icon = mode_icons.get(self.mode, "⚪")
        return (
            f"{icon} {self.node_id} [{self.role.value}] "
            f"mode={self.mode.value} health={self.health_score:.0f} "
            f"queue={self.queue_length}/{self.queue_size}"
        )
