"""
Scenario manager for the simulation.

senaryo = zamana bağlı olaylar dizisi.
"t=30s'de barrage jammer aç", "t=60s'de jammer kapat" gibi.

YAML dosyasından yüklenir veya kod ile oluşturulur.
simülasyon koşturucusu her adımda senaryoya bakar,
zamanı gelen olayları uygular.

# not: gerçek EW eğitim simülatörlerinde senaryolar çok daha
# detaylı, frekans bazında vs. biz basit tutuyoruz
"""

import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class EventType(Enum):
    """senaryo olay tipleri"""
    # karıştırıcı olayları
    JAMMER_ON = "jammer_on"       # karıştırıcıyı aç
    JAMMER_OFF = "jammer_off"     # karıştırıcıyı kapat
    JAMMER_CHANGE = "jammer_change"  # gücünü değiştir

    # ağ olayları
    NODE_FAIL = "node_fail"       # düğüm arızası
    NODE_RECOVER = "node_recover" # düğüm düzeldi
    LINK_CUT = "link_cut"        # bağlantı kopması (fiziksel)
    LINK_RESTORE = "link_restore" # bağlantı geri geldi

    # trafik olayları
    TRAFFIC_BURST = "traffic_burst"   # ani mesaj patlaması
    THREAT_INJECT = "threat_inject"   # tehdit enjeksiyonu (test için)


@dataclass
class ScenarioEvent:
    """
    tek bir senaryo olayı.

    Parameters
    ----------
    time : float
        olayın gerçekleşeceği simülasyon zamanı (saniye)
    event_type : EventType
        olay tipi
    target : str
        etkilenen hedef (düğüm id, link id, veya "all")
    params : dict
        olay parametreleri (jamming_db, fail_duration vs.)
    """
    time: float
    event_type: EventType
    target: str
    params: Dict[str, Any] = field(default_factory=dict)

    # olayın uygulanıp uygulanmadığını takip et
    applied: bool = False

    def __repr__(self):
        return (
            f"t={self.time:.1f}s: {self.event_type.value} "
            f"→ {self.target} {self.params}"
        )


class Scenario:
    """
    Simülasyon senaryosu.

    zamana sıralı olaylar listesi tutar.
    simülasyon her adımda check_events() çağırır,
    zamanı gelen olayları döndürür.

    Parameters
    ----------
    name : str
        senaryo adı
    duration : float
        toplam simülasyon süresi (saniye)
    """

    def __init__(self, name: str = "default", duration: float = 120.0):
        self.name = name
        self.duration = duration
        self.events: List[ScenarioEvent] = []
        self.description = ""

    def add_event(self, time: float, event_type: EventType,
                  target: str, params: dict = None):
        """olay ekle ve zamana göre sırala"""
        event = ScenarioEvent(
            time=time,
            event_type=event_type,
            target=target,
            params=params or {},
        )
        self.events.append(event)
        # zamana göre sırala
        self.events.sort(key=lambda e: e.time)

    def check_events(self, current_time: float) -> List[ScenarioEvent]:
        """
        zamanı gelmiş ama henüz uygulanmamış olayları döndür.
        """
        triggered = []
        for event in self.events:
            if event.applied:
                continue
            if event.time <= current_time:
                event.applied = True
                triggered.append(event)
        return triggered

    def reset(self):
        """senaryoyu sıfırla (tekrar koşturmak için)"""
        for event in self.events:
            event.applied = False

    @classmethod
    def from_yaml(cls, filepath: str) -> "Scenario":
        """YAML dosyasından senaryo yükle"""
        with open(filepath, "r") as f:
            config = yaml.safe_load(f)

        scenario = cls(
            name=config.get("name", "loaded"),
            duration=config.get("duration", 120.0),
        )
        scenario.description = config.get("description", "")

        for event_cfg in config.get("events", []):
            scenario.add_event(
                time=event_cfg["time"],
                event_type=EventType(event_cfg["type"]),
                target=event_cfg["target"],
                params=event_cfg.get("params", {}),
            )
        return scenario

    @classmethod
    def create_barrage_scenario(cls, duration: float = 120.0) -> "Scenario":
        """
        hazır senaryo: barrage jamming.

        0-30s:  normal (baseline ölçümü)
        30-70s: barrage jamming (tüm ağ baskı altında)
        70-120s: jamming bitti, toparlanma
        """
        s = cls("barrage_attack", duration)
        s.description = "Barrage jamming attack on relay link"

        # t=30s: HQ-RELAY arasına 15dB jamming
        s.add_event(30, EventType.JAMMER_ON, "HQ_RELAY_1",
                    {"jamming_db": 15.0})

        # t=45s: gücü artır
        s.add_event(45, EventType.JAMMER_CHANGE, "HQ_RELAY_1",
                    {"jamming_db": 20.0})

        # t=70s: jammer kapat
        s.add_event(70, EventType.JAMMER_OFF, "HQ_RELAY_1")

        return s

    @classmethod
    def create_targeted_scenario(cls, duration: float = 120.0) -> "Scenario":
        """
        hazır senaryo: hedefli saldırı.

        0-20s:  normal
        20-40s: SENSOR_A linki baskı altında
        40-60s: SENSOR_A düşer, SENSOR_B'ye geçiş
        60-80s: SENSOR_A geri gelir
        80-120s: tamamen normal
        """
        s = cls("targeted_attack", duration)
        s.description = "Targeted attack on SENSOR_A"

        s.add_event(20, EventType.JAMMER_ON, "RELAY_1_SENSOR_A",
                    {"jamming_db": 18.0})
        s.add_event(40, EventType.NODE_FAIL, "SENSOR_A")
        s.add_event(40, EventType.JAMMER_OFF, "RELAY_1_SENSOR_A")
        s.add_event(60, EventType.NODE_RECOVER, "SENSOR_A")

        return s

    def __repr__(self):
        return (
            f"Scenario('{self.name}', {self.duration}s, "
            f"{len(self.events)} events)"
        )
