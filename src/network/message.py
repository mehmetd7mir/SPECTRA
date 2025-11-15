"""
Tactical message types for the network simulation.

basically every communication in a tactical network is a "message"
but they have different types and priority levels. a threat alert
is way more important than a routine health check, so we need to
handle them differently.

i got the message classification idea from NATO STANAG docs that
my professor shared in class, simplified it a lot though
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class MessageType(Enum):
    """
    Types of tactical messages. in real military systems there are
    like 50+ types but we keep the important ones.
    """
    # sensor sends target position updates
    TRACK_UPDATE = "track_update"

    # high priority - enemy detected or something dangerous
    THREAT_ALERT = "threat_alert"

    # nodes send their health status periodically
    SYSTEM_HEALTH = "system_health"

    # commands from HQ to field nodes
    COMMAND = "command"

    # acknowledgement - "i got your message"
    ACK = "ack"


class MessagePriority(Enum):
    """
    Priority levels for messages.

    lower number = higher priority (like in OS scheduling)
    critical messages should ALWAYS get through even if the
    channel is degraded. low priority ones can be dropped.

    # TODO: belki flash priority de eklemeliyiz, NATO sistemlerinde
    # var ama simülasyon icin 4 seviye yeter simdilik
    """
    CRITICAL = 1    # must deliver - threat alerts, emergency commands
    HIGH = 2        # important - track updates near target
    ROUTINE = 3     # normal - periodic health, routine tracks
    LOW = 4         # can be delayed or dropped - logs, diagnostics


# her mesaj tipi icin varsayılan oncelikler
# bu mapping sayesinde mesaj olusturulurken otomatik oncelik atanir
DEFAULT_PRIORITIES = {
    MessageType.THREAT_ALERT: MessagePriority.CRITICAL,
    MessageType.COMMAND: MessagePriority.HIGH,
    MessageType.TRACK_UPDATE: MessagePriority.ROUTINE,
    MessageType.SYSTEM_HEALTH: MessagePriority.ROUTINE,
    MessageType.ACK: MessagePriority.LOW,
}

# mesaj boyutlari (byte cinsinden) - gercekci olsun diye
# gercek sistemlerde track update ~200 byte, threat alert daha buyuk
MESSAGE_SIZES = {
    MessageType.TRACK_UPDATE: 256,
    MessageType.THREAT_ALERT: 512,
    MessageType.SYSTEM_HEALTH: 128,
    MessageType.COMMAND: 384,
    MessageType.ACK: 64,
}


@dataclass
class TacticalMessage:
    """
    One tactical message in the network.

    her mesaj bir kaynak dugumden hedef dugume gider.
    TTL (time to live) suresi gecerse mesaj artik gecersizdir,
    cunku taktik veri eski olunca ise yaramaz.

    Parameters
    ----------
    msg_type : MessageType
        what kind of message is this
    source : str
        sender node id
    destination : str
        receiver node id (or "BROADCAST" for all)
    payload : dict
        actual data in the message
    priority : MessagePriority, optional
        if not given, uses default priority for this msg type
    ttl : float, optional
        time to live in seconds. if message doesnt arrive in
        this time, its useless. default depends on type.
    """
    msg_type: MessageType
    source: str
    destination: str
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: Optional[MessagePriority] = None
    ttl: float = 5.0

    # bunlar otomatik dolduruluyor, kullanici vermesine gerek yok
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=time.time)
    size_bytes: int = 0

    # iletim takibi
    delivered: bool = False
    delivered_at: Optional[float] = None
    hop_count: int = 0      # kac dugumden gecti
    retries: int = 0        # kac kere tekrar denendi

    def __post_init__(self):
        """mesaj olusunca otomatik ayarlar"""
        # oncelik verilmemisse varsayilan kullan
        if self.priority is None:
            self.priority = DEFAULT_PRIORITIES.get(
                self.msg_type, MessagePriority.ROUTINE
            )

        # boyut ata
        if self.size_bytes == 0:
            self.size_bytes = MESSAGE_SIZES.get(self.msg_type, 256)

        # TTL mesaj tipine gore ayarla
        # threat alert icin daha uzun ttl lazim, ack icin kisa yeter
        if self.ttl == 5.0:  # default degistirme
            ttl_defaults = {
                MessageType.THREAT_ALERT: 10.0,
                MessageType.COMMAND: 8.0,
                MessageType.TRACK_UPDATE: 3.0,
                MessageType.SYSTEM_HEALTH: 5.0,
                MessageType.ACK: 2.0,
            }
            self.ttl = ttl_defaults.get(self.msg_type, 5.0)

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        """mesajin suresi gecmis mi kontrol et"""
        if current_time is None:
            current_time = time.time()
        return (current_time - self.created_at) > self.ttl

    def mark_delivered(self, delivery_time: Optional[float] = None):
        """mesaj teslim edildi olarak isaretle"""
        self.delivered = True
        self.delivered_at = delivery_time or time.time()

    @property
    def latency(self) -> Optional[float]:
        """teslim gecikmesi (saniye). teslim edilmediyse None doner"""
        if self.delivered_at is None:
            return None
        return self.delivered_at - self.created_at

    @property
    def is_critical(self) -> bool:
        """bu mesaj kritik mi? karar motorunda cok kullanacagiz bunu"""
        return self.priority == MessagePriority.CRITICAL

    def __repr__(self):
        status = "✓" if self.delivered else "✗"
        return (
            f"[{status}] {self.msg_type.value} "
            f"({self.priority.name}) "
            f"{self.source}→{self.destination} "
            f"id={self.msg_id}"
        )

    def to_dict(self) -> dict:
        """dashboard ve loglama icin dict formatina cevir"""
        return {
            "msg_id": self.msg_id,
            "type": self.msg_type.value,
            "priority": self.priority.name,
            "source": self.source,
            "destination": self.destination,
            "size_bytes": self.size_bytes,
            "ttl": self.ttl,
            "created_at": self.created_at,
            "delivered": self.delivered,
            "latency": self.latency,
            "hop_count": self.hop_count,
        }


# ---- helper functions ----
# mesaj olusturmayi kolaylastiran fonksiyonlar
# her seferinde TacticalMessage(...) yazmak yerine bunlari kullaniriz

def create_track_update(source: str, dest: str, track_data: dict) -> TacticalMessage:
    """
    sensor dugumunden track update mesaji olustur.
    track_data icinde target_id, position, velocity vs olur.
    """
    return TacticalMessage(
        msg_type=MessageType.TRACK_UPDATE,
        source=source,
        destination=dest,
        payload={"track": track_data},
    )


def create_threat_alert(source: str, dest: str, threat_info: dict) -> TacticalMessage:
    """
    kritik tehdit uyarisi olustur. bu mesaj MUTLAKA ulastirilmali.
    threat_info: threat_type, position, severity vs.
    """
    return TacticalMessage(
        msg_type=MessageType.THREAT_ALERT,
        source=source,
        destination=dest,
        payload={"threat": threat_info},
        priority=MessagePriority.CRITICAL,  # her zaman critical
    )


def create_health_report(source: str, dest: str, health_data: dict) -> TacticalMessage:
    """
    dugum saglik raporu. cpu_temp, battery, link_quality vs.
    """
    return TacticalMessage(
        msg_type=MessageType.SYSTEM_HEALTH,
        source=source,
        destination=dest,
        payload={"health": health_data},
    )


def create_command(source: str, dest: str, command: str, params: dict = None) -> TacticalMessage:
    """
    komuta merkezinden saha dugumune komut.
    ornegin: "SWITCH_MODE", {"mode": "LOCAL_AUTONOMY"}
    """
    return TacticalMessage(
        msg_type=MessageType.COMMAND,
        source=source,
        destination=dest,
        payload={"command": command, "params": params or {}},
    )
