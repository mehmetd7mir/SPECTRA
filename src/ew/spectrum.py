"""
Spectrum environment model.

elektromanyetik spektrumu simüle eder. gerçek dünyada radyo
frekansları kullanılır (VHF: 30-300MHz, UHF: 300MHz-3GHz vs).
her frekans bandında bir gürültü seviyesi (noise floor) vardır.

bu modül spektrumun genel durumunu takip eder:
- hangi bantlar temiz, hangileri bozuk
- toplam bant doluluk oranı (spectrum occupancy)
- zaman içinde bozulma nasıl değişiyor

# ders notlarından: spektrum yoğunluğu hesaplamak için FFT kullanılır
# ama biz burada doğrudan modelliyoruz, sinyal seviyesine inmiyoruz
# çünkü amacımız "etkiyi" ölçmek, sinyali işlemek değil
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class FrequencyBand:
    """
    bir frekans bandını temsil eder.

    gerçek sistemde her haberleşme kanalı belirli bir bant
    üzerinde çalışır. jammer o bandı hedeflerse o kanal
    bozulur.
    """
    name: str
    center_freq_mhz: float     # merkez frekansı
    bandwidth_mhz: float       # bant genişliği
    noise_floor_dbm: float     # doğal gürültü seviyesi (dBm)

    # anlık durum
    current_noise_dbm: float = 0.0    # şu anki gürültü (jammer dahil)
    is_jammed: bool = False

    def __post_init__(self):
        self.current_noise_dbm = self.noise_floor_dbm

    @property
    def degradation_db(self) -> float:
        """gürültü artışı (dB). 0 = normal, yüksek = bozuk"""
        return max(0, self.current_noise_dbm - self.noise_floor_dbm)

    @property
    def quality(self) -> float:
        """bant kalitesi (0-1). 1 = temiz, 0 = kullanılamaz"""
        # 20 dB degradation'da kalite 0'a yaklaşsın
        deg = self.degradation_db
        return max(0.0, 1.0 - (deg / 25.0))


# varsayılan frekans bantları - taktik haberleşme için tipik
DEFAULT_BANDS = [
    FrequencyBand("VHF_LOW", 50.0, 10.0, -110.0),
    FrequencyBand("VHF_HIGH", 150.0, 20.0, -105.0),
    FrequencyBand("UHF", 400.0, 50.0, -100.0),
    FrequencyBand("L_BAND", 1500.0, 100.0, -95.0),
    FrequencyBand("S_BAND", 3000.0, 200.0, -90.0),
]


class SpectrumEnvironment:
    """
    Spektrum ortamı yöneticisi.

    tüm frekans bantlarının durumunu takip eder.
    jammer'lar buraya etki eder, kanallar buradan SNR çeker.

    Parameters
    ----------
    bands : list of FrequencyBand, optional
        frekans bantları. None ise varsayılanları kullanır.
    """

    def __init__(self, bands: Optional[List[FrequencyBand]] = None):
        if bands is None:
            # varsayılanların kopyasını al (orijinali bozma)
            self.bands = [
                FrequencyBand(b.name, b.center_freq_mhz, b.bandwidth_mhz, b.noise_floor_dbm)
                for b in DEFAULT_BANDS
            ]
        else:
            self.bands = bands

        # isimle hızlı erişim için dict
        self._band_map: Dict[str, FrequencyBand] = {
            b.name: b for b in self.bands
        }

        # link → bant eşleştirmesi (hangi link hangi bantta çalışıyor)
        # varsayılan olarak tüm linkler UHF bandında
        self.link_band_map: Dict[str, str] = {}

        # geçmiş veriler (grafik için)
        self._history: List[Dict[str, float]] = []

    def assign_link_band(self, link_id: str, band_name: str):
        """bir linki belirli bir frekans bandına ata"""
        if band_name in self._band_map:
            self.link_band_map[link_id] = band_name

    def get_band(self, name: str) -> Optional[FrequencyBand]:
        """isimle bant getir"""
        return self._band_map.get(name)

    def apply_interference(self, band_name: str, power_dbm: float):
        """
        bir banda karıştırma gücü uygula.

        power_dbm: jammer'ın o banttaki gücü (dBm cinsinden)
        gürültü seviyesine eklenir (dB toplamı log alanında)
        """
        band = self._band_map.get(band_name)
        if not band:
            return

        # iki güç kaynağını toplamak için:
        # P_total = 10 * log10(10^(P1/10) + 10^(P2/10))
        # bu formülü sinyal işleme dersinde öğrendim
        noise_linear = 10 ** (band.noise_floor_dbm / 10)
        jam_linear = 10 ** (power_dbm / 10)
        total_linear = noise_linear + jam_linear
        band.current_noise_dbm = round(10 * np.log10(total_linear), 2)
        band.is_jammed = True

    def clear_interference(self, band_name: str):
        """bandın gürültüsünü normale döndür"""
        band = self._band_map.get(band_name)
        if band:
            band.current_noise_dbm = band.noise_floor_dbm
            band.is_jammed = False

    def clear_all(self):
        """tüm bantları temizle"""
        for band in self.bands:
            band.current_noise_dbm = band.noise_floor_dbm
            band.is_jammed = False

    def get_link_degradation(self, link_id: str) -> float:
        """
        bir linkin bağlı olduğu banttaki bozulma miktarı (dB).
        bu değer channel.py'deki jamming_db olarak kullanılacak.
        """
        band_name = self.link_band_map.get(link_id, "UHF")
        band = self._band_map.get(band_name)
        if not band:
            return 0.0
        return band.degradation_db

    @property
    def overall_quality(self) -> float:
        """tüm spektrumun genel kalitesi (0-1)"""
        if not self.bands:
            return 1.0
        qualities = [b.quality for b in self.bands]
        return round(sum(qualities) / len(qualities), 3)

    @property
    def spectrum_occupancy(self) -> float:
        """
        bant doluluk oranı: kaç bant bozuk (0-1).
        # EW raporlarında "spectral occupancy" olarak geçer
        """
        if not self.bands:
            return 0.0
        jammed = sum(1 for b in self.bands if b.is_jammed)
        return round(jammed / len(self.bands), 3)

    def snapshot(self) -> dict:
        """anlık durum fotoğrafı (dashboard ve log için)"""
        return {
            "overall_quality": self.overall_quality,
            "occupancy": self.spectrum_occupancy,
            "bands": {
                b.name: {
                    "noise_dbm": round(b.current_noise_dbm, 1),
                    "degradation_db": round(b.degradation_db, 1),
                    "quality": round(b.quality, 2),
                    "jammed": b.is_jammed,
                }
                for b in self.bands
            }
        }

    def record_history(self):
        """mevcut durumu geçmişe kaydet"""
        self._history.append(self.snapshot())

    def __repr__(self):
        jammed = sum(1 for b in self.bands if b.is_jammed)
        return (
            f"Spectrum: {len(self.bands)} bands, "
            f"{jammed} jammed, "
            f"quality={self.overall_quality:.2f}"
        )
