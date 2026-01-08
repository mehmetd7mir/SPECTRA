"""
EW effects calculator.

bu modül jammer'ların etkisini spektrum üzerinden
ağ kanallarına yansıtır. arada köprü görevi görür:

   Jammer → Spectrum → Channel → Network
              ↑                     ↑
        effects.py hesaplar   topology.py uygular

ayrıca görev etki skoru (Mission Impact Score - MIS) hesaplar.
MIS, karar motorunun en önemli girdisi olacak.

# hocamız "mission effectiveness" kavramını çok vurguluyordu
# sadece teknik metrikler değil, görevin ne kadar etkilendiği önemli
"""

import numpy as np
from typing import Dict, Optional
from dataclasses import dataclass

from .spectrum import SpectrumEnvironment
from .jammer import Jammer
from ..network.topology import NetworkTopology


@dataclass
class MissionImpactScore:
    """
    Görev etki skoru.

    0 = görev tamamen başarısız
    100 = görev mükemmel devam ediyor

    alt bileşenleri de tutar - dashboardda göstereceğiz.
    """
    overall: float = 100.0

    # alt bileşenler
    communication_score: float = 100.0    # haberleşme kalitesi
    coverage_score: float = 100.0         # sensör kapsama
    command_score: float = 100.0          # komuta kontrolü
    response_score: float = 100.0         # tepki kapasitesi

    def to_dict(self) -> dict:
        return {
            "overall": round(self.overall, 1),
            "communication": round(self.communication_score, 1),
            "coverage": round(self.coverage_score, 1),
            "command": round(self.command_score, 1),
            "response": round(self.response_score, 1),
        }


class EWEffectCalculator:
    """
    EW etkisi hesaplayıcı.

    jammer'ları alır, spektruma uygular, ağ kanallarını günceller
    ve görev etki skorunu hesaplar.

    Parameters
    ----------
    spectrum : SpectrumEnvironment
        spektrum ortamı
    topology : NetworkTopology
        ağ topolojisi
    """

    def __init__(self, spectrum: SpectrumEnvironment, topology: NetworkTopology):
        self.spectrum = spectrum
        self.topology = topology
        self.jammers: Dict[str, Jammer] = {}
        self.current_mis = MissionImpactScore()

        # link → bant eşleştirmesi (varsayılan UHF)
        # her linkin çalıştığı frekans bandını ata
        self._setup_default_band_assignments()

    def _setup_default_band_assignments(self):
        """
        linkleri frekans bantlarına ata.
        gerçek hayatta her link farklı frekansta çalışabilir.
        # TODO: bunu config'den okumak daha iyi olur ama simdilik
        # hardcode yapıyoruz
        """
        for link_id in self.topology.channels:
            # varsayılan: UHF bandı
            self.spectrum.assign_link_band(link_id, "UHF")

    def add_jammer(self, jammer: Jammer):
        """karıştırıcı ekle"""
        self.jammers[jammer.jammer_id] = jammer

    def remove_jammer(self, jammer_id: str):
        """karıştırıcı kaldır"""
        if jammer_id in self.jammers:
            del self.jammers[jammer_id]

    def update(self, sim_time: float = 0.0):
        """
        tüm EW etkilerini güncelle. her simülasyon adımında çağrılır.

        1. spektrumu temizle
        2. aktif jammer'ların etkisini spektruma uygula
        3. spektrum bozulmasını ağ kanallarına yansıt
        4. görev etki skorunu hesapla
        """
        # 1. spektrumu sıfırla
        self.spectrum.clear_all()

        # 2. jammer etkilerini uygula
        for jammer in self.jammers.values():
            if not jammer.is_active:
                continue

            powers = jammer.get_power_per_band(sim_time)
            for band_name, power_dbm in powers.items():
                self.spectrum.apply_interference(band_name, power_dbm)

        # 3. kanal SNR'larını güncelle
        self._update_channels()

        # 4. MIS hesapla
        self.current_mis = self._calculate_mis()

        # 5. geçmişe kaydet
        self.spectrum.record_history()

    def _update_channels(self):
        """spektrum bozulmasını ağ kanallarına yansıt"""
        for link_id, channel in self.topology.channels.items():
            degradation = self.spectrum.get_link_degradation(link_id)
            if degradation > 0:
                channel.apply_jamming(degradation)
            else:
                channel.clear_jamming()

    def _calculate_mis(self) -> MissionImpactScore:
        """
        Görev Etki Skoru hesapla.

        4 bileşenden oluşur:
        1. communication: genel link kalitesi
        2. coverage: kaç sensör aktif
        3. command: HQ'nun bağlantı durumu
        4. response: silah sisteminin bağlantısı

        ağırlıklı ortalama ile toplam skor hesaplanır.

        # bu formülü ben tasarladım, gerçek askeri sistemlerde
        # daha karmaşık ama prensibi aynı
        """
        mis = MissionImpactScore()

        # 1. Communication Score - tüm linklerin ortalama kalitesi
        qualities = [ch.link_quality for ch in self.topology.channels.values()]
        mis.communication_score = (sum(qualities) / len(qualities)) * 100 if qualities else 0

        # 2. Coverage Score - aktif sensörlerin oranı
        sensors = [n for n in self.topology.nodes.values()
                   if n.role.value == "sensor"]
        if sensors:
            active_sensors = sum(1 for s in sensors if s.is_online)
            mis.coverage_score = (active_sensors / len(sensors)) * 100
        else:
            mis.coverage_score = 100

        # 3. Command Score - HQ'nun bağlantı kalitesi
        hq_links = []
        for link_id, ch in self.topology.channels.items():
            if "HQ" in link_id:
                hq_links.append(ch.link_quality)
        if hq_links:
            mis.command_score = (sum(hq_links) / len(hq_links)) * 100
        else:
            mis.command_score = 0

        # 4. Response Score - silah sisteminin durumu
        weapons = [n for n in self.topology.nodes.values()
                   if n.role.value == "weapon"]
        if weapons:
            weapon_online = sum(1 for w in weapons if w.is_online)
            # silah linklerinin kalitesi
            weapon_quality = []
            for link_id, ch in self.topology.channels.items():
                if any(w.node_id in link_id for w in weapons):
                    weapon_quality.append(ch.link_quality)

            online_ratio = weapon_online / len(weapons)
            avg_quality = sum(weapon_quality) / len(weapon_quality) if weapon_quality else 0
            mis.response_score = (online_ratio * 0.5 + avg_quality * 0.5) * 100
        else:
            mis.response_score = 100

        # toplam skor - ağırlıklı ortalama
        # haberleşme en önemli (%35), sonra komuta (%30),
        # kapsama (%20), tepki (%15)
        mis.overall = (
            0.35 * mis.communication_score +
            0.30 * mis.command_score +
            0.20 * mis.coverage_score +
            0.15 * mis.response_score
        )

        return mis

    def get_status(self) -> dict:
        """genel EW durumu"""
        return {
            "active_jammers": sum(1 for j in self.jammers.values() if j.is_active),
            "total_jammers": len(self.jammers),
            "spectrum_quality": self.spectrum.overall_quality,
            "spectrum_occupancy": self.spectrum.spectrum_occupancy,
            "mission_impact": self.current_mis.to_dict(),
        }

    def __repr__(self):
        active = sum(1 for j in self.jammers.values() if j.is_active)
        return (
            f"EWEffects: {active}/{len(self.jammers)} jammers active, "
            f"MIS={self.current_mis.overall:.1f}"
        )
