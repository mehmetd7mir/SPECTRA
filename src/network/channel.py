"""
Tactical communication channel model.

iki düğüm arasındaki haberleşme kanalını simüle eder.
gerçek hayatta bu radyo linki olur (UHF, VHF, SHF vs.).

kanalın temel parametreleri:
- SNR (Signal-to-Noise Ratio): sinyal kalitesi, dB cinsinden
  yüksek SNR = temiz sinyal, düşük SNR = gürültülü
- paket kayıp oranı (PER): SNR'dan hesaplanır
- gecikme: mesajın ne kadar sürede ulaştığı
- bant genişliği: saniyede kaç byte gönderilebilir

EW baskısı SNR'ı düşürür → PER artar → mesajlar kaybolur.
bu ilişkiyi bu modül hesaplıyor.

# derste öğrendiğim BER-SNR formülünü kullandım ama basitleştirdim
# asıl formül modülasyon tipine göre değişir (BPSK, QPSK vs.)
# biz genel bir sigmoid eğrisi kullanıyoruz
"""

import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

from .message import TacticalMessage


@dataclass
class ChannelState:
    """
    kanalın anlık durumu.
    simülasyon her adımda bunu günceller.
    """
    snr_db: float = 20.0           # sinyal/gürültü oranı (dB)
    packet_error_rate: float = 0.0  # paket hata oranı (0-1)
    delay_ms: float = 10.0         # temel gecikme (ms)
    bandwidth_bps: float = 9600.0  # bant genişliği (byte/s)
    is_active: bool = True         # kanal çalışıyor mu


class TacticalChannel:
    """
    İki düğüm arasındaki haberleşme kanalı.

    mesaj gönderildiğinde:
    1. SNR'a göre paket kayıp olasılığını hesapla
    2. kayıp varsa mesajı düşür
    3. kaybı yoksa gecikmeyi hesapla
    4. mesajı hedef düğüme teslim et

    Parameters
    ----------
    node_a : str
        birinci düğüm id
    node_b : str
        ikinci düğüm id
    base_snr : float
        temel SNR (dB) - bozulma olmadan
    bandwidth : float
        bant genişliği (byte/s)
    base_delay : float
        temel gecikme (ms)

    # not: kanal çift yönlü (bidirectional), A→B ile B→A aynı kanal
    """

    def __init__(
        self,
        node_a: str,
        node_b: str,
        base_snr: float = 20.0,
        bandwidth: float = 9600.0,
        base_delay: float = 10.0,
    ):
        self.node_a = node_a
        self.node_b = node_b
        self.base_snr = base_snr
        self.bandwidth = bandwidth
        self.base_delay = base_delay

        # mevcut durum
        self.state = ChannelState(
            snr_db=base_snr,
            delay_ms=base_delay,
            bandwidth_bps=bandwidth,
        )

        # EW baskısı (dB cinsinden SNR düşüşü)
        # jammer aktifken bu değer artar, SNR düşer
        self._jamming_power = 0.0

        # istatistikler
        self.total_sent = 0
        self.total_delivered = 0
        self.total_lost = 0
        self.total_bytes = 0

        # son güncelleme zamanı
        self._last_update = time.time()

    def apply_jamming(self, jamming_db: float):
        """
        karıştırıcı etkisi uygula.

        jamming_db: ne kadar dB SNR düşüşü yapacak
        örnek: 10 dB jamming → SNR 20'den 10'a düşer
        """
        self._jamming_power = max(0.0, jamming_db)
        self._update_state()

    def clear_jamming(self):
        """karıştırma etkisini kaldır"""
        self._jamming_power = 0.0
        self._update_state()

    def _update_state(self):
        """
        kanal durumunu güncelle.
        SNR → PER → gecikme hesaplaması burada yapılır.
        """
        # efektif SNR = temel SNR - karıştırma gücü
        effective_snr = self.base_snr - self._jamming_power

        # SNR 0'ın altına düşebilir (çok güçlü jamming)
        self.state.snr_db = effective_snr
        self.state.is_active = effective_snr > -5  # -5 dB altında kanal ölü

        # SNR → PER dönüşümü (sigmoid fonksiyonu)
        # SNR yüksekken PER ≈ 0, düşükken PER ≈ 1
        # geçiş bölgesi 5-15 dB civarında
        #
        # formül: PER = 1 / (1 + e^(k * (SNR - threshold)))
        # k ne kadar büyükse geçiş o kadar keskin
        # threshold: %50 hata oranı noktası
        self.state.packet_error_rate = self._snr_to_per(effective_snr)

        # gecikme modeli:
        # SNR düştükçe tekrar iletim (ARQ) gerekir → gecikme artar
        # base_delay * (1 + retry_factor)
        retry_factor = self.state.packet_error_rate * 3.0  # max 3x ek gecikme
        self.state.delay_ms = self.base_delay * (1.0 + retry_factor)

        # bant genişliği de SNR'a göre düşer
        # shannon capacity: C = B * log2(1 + SNR_linear)
        # basitleştirilmiş versiyonu kullanıyoruz
        if effective_snr > 0:
            snr_linear = 10 ** (effective_snr / 10)
            capacity_factor = math.log2(1 + snr_linear) / math.log2(1 + 10 ** (self.base_snr / 10))
            self.state.bandwidth_bps = self.bandwidth * min(1.0, capacity_factor)
        else:
            self.state.bandwidth_bps = 0.0

    def _snr_to_per(self, snr_db: float) -> float:
        """
        SNR'dan paket hata oranına dönüşüm.

        sigmoid fonksiyonu kullanıyoruz:
        - SNR > 15 dB → PER ≈ 0 (temiz kanal)
        - SNR = 8 dB → PER ≈ 0.5 (yarı yarıya kayıp)
        - SNR < 0 dB → PER ≈ 1 (hemen hemen hiç geçmiyor)

        # bu parametreleri biraz deneyerek buldum,
        # gerçek sistemde modülasyona göre değişir
        """
        k = 0.5            # geçiş keskinliği
        threshold = 8.0    # %50 PER noktası (dB)

        try:
            per = 1.0 / (1.0 + math.exp(k * (snr_db - threshold)))
        except OverflowError:
            per = 0.0 if snr_db > threshold else 1.0

        return round(per, 4)

    def transmit(self, msg: TacticalMessage, current_time: Optional[float] = None) -> Tuple[bool, float]:
        """
        mesajı kanal üzerinden gönder.

        Returns
        -------
        (success, delay_ms) : tuple
            success: mesaj ulaştı mı
            delay_ms: gecikme süresi (ms). başarısızsa 0.
        """
        if current_time is None:
            current_time = time.time()

        self.total_sent += 1
        self.total_bytes += msg.size_bytes

        # kanal aktif değilse direkt kaybet
        if not self.state.is_active:
            self.total_lost += 1
            return (False, 0.0)

        # paket kaybı kontrolü - rastgele
        if random.random() < self.state.packet_error_rate:
            self.total_lost += 1
            return (False, 0.0)

        # başarılı iletim
        self.total_delivered += 1

        # gecikme hesapla: temel gecikme + mesaj boyutuna göre ek
        # büyük mesaj → daha uzun iletim süresi
        transmission_time = (msg.size_bytes / max(1, self.state.bandwidth_bps)) * 1000  # ms
        jitter = random.gauss(0, self.base_delay * 0.1)  # %10 jitter
        total_delay = self.state.delay_ms + transmission_time + abs(jitter)

        return (True, round(total_delay, 2))

    @property
    def link_quality(self) -> float:
        """
        link kalitesi skoru (0.0 - 1.0).

        karar motoru bu değeri kullanarak ağ politikasını belirleyecek.
        0 = ölü link, 1 = mükemmel link
        """
        if not self.state.is_active:
            return 0.0

        # SNR normalizasyonu (0-30 dB arası → 0-1)
        snr_score = max(0, min(1, self.state.snr_db / 30.0))

        # PER tersi (düşük PER = iyi)
        per_score = 1.0 - self.state.packet_error_rate

        # ağırlıklı ortalama
        return round(0.4 * snr_score + 0.6 * per_score, 3)

    @property
    def delivery_rate(self) -> float:
        """toplam teslim oranı"""
        if self.total_sent == 0:
            return 1.0
        return self.total_delivered / self.total_sent

    def get_status(self) -> dict:
        """kanal durumu özeti"""
        return {
            "link": f"{self.node_a}↔{self.node_b}",
            "snr_db": round(self.state.snr_db, 1),
            "per": round(self.state.packet_error_rate, 3),
            "delay_ms": round(self.state.delay_ms, 1),
            "bandwidth": round(self.state.bandwidth_bps, 0),
            "active": self.state.is_active,
            "quality": self.link_quality,
            "delivery_rate": round(self.delivery_rate, 3),
            "jamming_db": round(self._jamming_power, 1),
        }

    def __repr__(self):
        q = self.link_quality
        if q > 0.7:
            icon = "🟢"
        elif q > 0.3:
            icon = "🟡"
        elif q > 0:
            icon = "🔴"
        else:
            icon = "⚫"

        return (
            f"{icon} {self.node_a}↔{self.node_b} "
            f"SNR={self.state.snr_db:.1f}dB "
            f"PER={self.state.packet_error_rate:.1%} "
            f"quality={q:.2f}"
        )
