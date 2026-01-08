"""
Jammer models - different types of electronic warfare jammers.

karıştırıcı (jammer) düşmanın haberleşmesini bozmak için
kasıtlı olarak radyo sinyali yayan cihazdır.

3 temel tip var:
- barrage: geniş bant, tüm frekansları aynı anda bozar. güçsüz ama geniş.
- spot: dar bant, tek frekansa odaklanır. çok güçlü ama dar alan.
- sweep: frekanslar arasında tarar. orta güç, orta genişlik.

# EW dersinden: jammer gücü "J/S oranı" (Jamming-to-Signal)
# ile ölçülür. J/S yüksekse haberleşme bozulur.
# biz basitleştirdik, direkt dBm gücü kullanıyoruz.
"""

import time
import math
import numpy as np
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict


class JammerType(Enum):
    """karıştırıcı tipleri"""
    BARRAGE = "barrage"    # geniş bant, düşük güç/bant
    SPOT = "spot"          # dar bant, yüksek güç
    SWEEP = "sweep"        # taramalı, orta güç


@dataclass
class Jammer:
    """
    Bir elektronik harp karıştırıcısı.

    Parameters
    ----------
    jammer_id : str
        karıştırıcı kimliği
    jammer_type : JammerType
        tip (barrage/spot/sweep)
    total_power_dbm : float
        toplam yayın gücü (dBm). barrage'da bantlara bölünür,
        spot'ta tek banda yoğunlaşır.
    position : tuple
        (x, y) konumu (metre)
    target_bands : list
        hedeflenen frekans bantları. spot için 1 bant,
        barrage için hepsi.
    """
    jammer_id: str
    jammer_type: JammerType
    total_power_dbm: float = -70.0   # varsayılan güç
    position: tuple = (0, 0)
    target_bands: List[str] = field(default_factory=list)

    # çalışma durumu
    is_active: bool = False
    activation_time: float = 0.0

    # sweep parametreleri
    sweep_period: float = 5.0    # tarama periyodu (saniye)
    _sweep_phase: float = 0.0   # şu anki tarama fazı

    def activate(self):
        """karıştırıcıyı aç"""
        self.is_active = True
        self.activation_time = time.time()

    def deactivate(self):
        """karıştırıcıyı kapat"""
        self.is_active = False

    def get_power_per_band(self, sim_time: float = 0.0) -> Dict[str, float]:
        """
        her hedef bant için ne kadar güç düşüyor hesapla.

        barrage: toplam güç / bant sayısı (eşit dağılım)
        spot: tüm güç tek banda
        sweep: o anda hangi banttaysa tüm güç oraya

        Returns: {band_name: power_dbm}
        """
        if not self.is_active or not self.target_bands:
            return {}

        result = {}

        if self.jammer_type == JammerType.BARRAGE:
            # gücü bantlara eşit dağıt
            # P_bant = P_total - 10*log10(N)
            # yani 3 bandaysa her bant 4.8 dB daha az güç alır
            n_bands = len(self.target_bands)
            power_per = self.total_power_dbm - 10 * math.log10(n_bands)
            for band in self.target_bands:
                result[band] = round(power_per, 2)

        elif self.jammer_type == JammerType.SPOT:
            # tüm güç tek banda - en yıkıcı tip
            target = self.target_bands[0]
            result[target] = self.total_power_dbm

        elif self.jammer_type == JammerType.SWEEP:
            # taramalı - zamanla bantlar arasında geçiş yapar
            # hangi bantta olduğunu zaman ve periyottan hesapla
            n_bands = len(self.target_bands)
            # her banta eşit süre ayrılır
            band_duration = self.sweep_period / n_bands
            current_idx = int((sim_time % self.sweep_period) / band_duration)
            current_idx = min(current_idx, n_bands - 1)

            target = self.target_bands[current_idx]
            result[target] = self.total_power_dbm

        return result

    def get_effective_power_at(self, distance_m: float) -> float:
        """
        mesafeye göre efektif güç hesapla.
        free-space path loss (FSPL) modeli kullanıyoruz.

        FSPL(dB) = 20*log10(d) + 20*log10(f) - 147.55
        basitleştirilmiş versiyonu: her 10x mesafe için 20dB kayıp

        # gerçek hayatta anten kazancı, arazi etkisi vs de var
        # ama simülasyon için bu yeterli
        """
        if distance_m <= 0:
            return self.total_power_dbm

        # basit model: referans mesafe 100m, her 10x uzaklaşmada 20dB kayıp
        ref_distance = 100.0
        if distance_m <= ref_distance:
            return self.total_power_dbm

        path_loss = 20 * math.log10(distance_m / ref_distance)
        return round(self.total_power_dbm - path_loss, 2)

    def __repr__(self):
        status = "🔴 ON" if self.is_active else "⚪ OFF"
        return (
            f"Jammer({self.jammer_id}) {self.jammer_type.value} "
            f"{status} power={self.total_power_dbm}dBm "
            f"bands={self.target_bands}"
        )


# ---- hazır jammer oluşturucular ----

def create_barrage_jammer(
    jammer_id: str = "JAM_1",
    power_dbm: float = -65.0,
    position: tuple = (600, 300),
) -> Jammer:
    """
    barrage jammer oluştur - tüm bantları hedefler.
    gücü bantlara bölündüğü için her bant nispeten az etkilenir
    ama geniş alan etkilenir.
    """
    return Jammer(
        jammer_id=jammer_id,
        jammer_type=JammerType.BARRAGE,
        total_power_dbm=power_dbm,
        position=position,
        target_bands=["VHF_LOW", "VHF_HIGH", "UHF", "L_BAND", "S_BAND"],
    )


def create_spot_jammer(
    jammer_id: str = "JAM_SPOT",
    power_dbm: float = -55.0,
    target_band: str = "UHF",
    position: tuple = (600, 300),
) -> Jammer:
    """
    spot jammer - tek banda yoğunlaşır, çok etkili.
    tüm güç tek banta gittiği için o bant neredeyse ölür.
    """
    return Jammer(
        jammer_id=jammer_id,
        jammer_type=JammerType.SPOT,
        total_power_dbm=power_dbm,
        position=position,
        target_bands=[target_band],
    )


def create_sweep_jammer(
    jammer_id: str = "JAM_SWEEP",
    power_dbm: float = -60.0,
    position: tuple = (600, 300),
    sweep_period: float = 10.0,
) -> Jammer:
    """
    sweep jammer - bantlar arasında tarar.
    her an tek bandı etkiler ama sırayla hepsine geçer.
    tahmin edilmesi zor, savunması da zor.
    """
    return Jammer(
        jammer_id=jammer_id,
        jammer_type=JammerType.SWEEP,
        total_power_dbm=power_dbm,
        position=position,
        target_bands=["VHF_HIGH", "UHF", "L_BAND"],
        sweep_period=sweep_period,
    )
