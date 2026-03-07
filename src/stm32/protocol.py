"""
SPECTRA haberleşme protokolü - PC ↔ STM32 UART üzerinden.

basit, güvenilir bir binary protokol:
  [START] [CMD] [LEN] [DATA...] [CRC] [END]

her paket:
- START: 0xAA (senkronizasyon)
- CMD:   1 byte komut kodu
- LEN:   1 byte veri uzunluğu (max 255)
- DATA:  0-255 byte veri
- CRC:   1 byte XOR checksum
- END:   0x55 (bitiş)

# neden binary? çünkü:
# 1. bant genişliği verimli (UART 115200 baud)
# 2. parse etmesi deterministik (JSON gibi değil)
# 3. CRC ile hata kontrolü var
# 4. gömülüde hafıza verimli
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, List
import struct


class Command(IntEnum):
    """protokol komut kodları"""
    # PC → STM32
    SET_MODE = 0x01         # düğüm modunu değiştir
    REQUEST_STATUS = 0x02   # durum iste
    SET_ALERT_LEVEL = 0x03  # alarm seviyesi ayarla
    DISPLAY_TEXT = 0x04     # OLED'e yazı gönder
    BUZZER_ON = 0x05        # buzzer aç
    BUZZER_OFF = 0x06       # buzzer kapat

    # STM32 → PC
    STATUS_REPORT = 0x10    # durum raporu
    SENSOR_DATA = 0x11      # sensör verisi
    MODE_ACK = 0x12         # mod değişikliği onayı
    HEARTBEAT = 0x13        # hayat sinyali (her 1s)
    ALERT = 0x14            # yerel alarm


class NodeMode_STM32(IntEnum):
    """STM32 tarafındaki mod tanımları (Python'dakiyle eşleşmeli)"""
    NORMAL = 0
    DEGRADED = 1
    LOCAL_AUTONOMY = 2
    SILENT = 3
    EMERGENCY = 4


class AlertLevel(IntEnum):
    """alarm seviyeleri"""
    NONE = 0
    LOW = 1       # sadece LED
    MEDIUM = 2    # LED + kısa bip
    HIGH = 3      # LED + sürekli bip
    CRITICAL = 4  # tüm uyarılar


# paket sabitleri
START_BYTE = 0xAA
END_BYTE = 0x55
MAX_DATA_LEN = 255


@dataclass
class SpectraPacket:
    """
    protokol paketi.

    PC tarafında oluşturulup bytes'a çevrilir → UART'tan gönderilir.
    STM32'den gelen bytes parse edilir → SpectraPacket olur.
    """
    command: int
    data: bytes = b""

    @property
    def length(self) -> int:
        return len(self.data)

    def calculate_crc(self) -> int:
        """XOR checksum hesapla"""
        crc = self.command ^ self.length
        for b in self.data:
            crc ^= b
        return crc & 0xFF

    def to_bytes(self) -> bytes:
        """paketi byte dizisine çevir (gönderim için)"""
        crc = self.calculate_crc()
        packet = struct.pack(
            f"BBB{len(self.data)}sBB",
            START_BYTE,
            self.command,
            self.length,
            self.data,
            crc,
            END_BYTE,
        )
        return packet

    @classmethod
    def from_bytes(cls, raw: bytes) -> Optional["SpectraPacket"]:
        """
        byte dizisinden paket parse et.
        hatalıysa None döndürür.
        """
        if len(raw) < 5:  # min: START CMD LEN CRC END
            return None

        if raw[0] != START_BYTE or raw[-1] != END_BYTE:
            return None

        cmd = raw[1]
        length = raw[2]

        if len(raw) != 5 + length:
            return None

        data = raw[3:3 + length]
        crc = raw[3 + length]

        # CRC doğrula
        packet = cls(command=cmd, data=data)
        if packet.calculate_crc() != crc:
            return None  # bozuk paket

        return packet

    def __repr__(self):
        cmd_name = Command(self.command).name if self.command in Command._value2member_map_ else f"0x{self.command:02X}"
        return f"Packet({cmd_name}, {self.length}B, data={self.data.hex()})"


class SpectraProtocol:
    """
    Paket oluşturma yardımcıları.

    runner veya dashboard bu sınıfı kullanarak
    STM32'ye komut gönderir.
    """

    @staticmethod
    def set_mode(mode: int) -> SpectraPacket:
        """mod değişikliği komutu"""
        return SpectraPacket(Command.SET_MODE, bytes([mode]))

    @staticmethod
    def request_status() -> SpectraPacket:
        """durum isteği"""
        return SpectraPacket(Command.REQUEST_STATUS)

    @staticmethod
    def set_alert(level: int) -> SpectraPacket:
        """alarm seviyesi"""
        return SpectraPacket(Command.SET_ALERT_LEVEL, bytes([level]))

    @staticmethod
    def display_text(text: str) -> SpectraPacket:
        """OLED'e yazı gönder (max 32 karakter)"""
        data = text[:32].encode("ascii", errors="replace")
        return SpectraPacket(Command.DISPLAY_TEXT, data)

    @staticmethod
    def buzzer(on: bool) -> SpectraPacket:
        """buzzer aç/kapat"""
        cmd = Command.BUZZER_ON if on else Command.BUZZER_OFF
        return SpectraPacket(cmd)

    @staticmethod
    def parse_sensor_data(packet: SpectraPacket) -> Optional[dict]:
        """
        STM32'den gelen sensör verisi paketini parse et.

        veri formatı (8 byte):
        - temperature (2 byte, 0.1°C çözünürlük)
        - light (2 byte, 0-4095 ADC değeri)
        - distance (2 byte, mm cinsinden)
        - pot_value (2 byte, 0-4095 ADC)
        """
        if packet.command != Command.SENSOR_DATA or len(packet.data) < 8:
            return None

        temp_raw, light, distance, pot = struct.unpack("<HHHH", packet.data[:8])
        return {
            "temperature_c": temp_raw / 10.0,   # 0.1°C → °C
            "light_level": light,                 # 0-4095
            "distance_cm": distance / 10.0,       # mm → cm
            "pot_percent": round(pot / 4095 * 100, 1),  # 0-100%
        }

    @staticmethod
    def parse_status_report(packet: SpectraPacket) -> Optional[dict]:
        """
        STM32 durum raporu parse et.

        veri formatı (4 byte):
        - current_mode (1 byte)
        - alert_level (1 byte)
        - uptime_seconds (2 byte)
        """
        if packet.command != Command.STATUS_REPORT or len(packet.data) < 4:
            return None

        mode, alert, uptime = struct.unpack("<BBH", packet.data[:4])
        return {
            "mode": NodeMode_STM32(mode).name if mode < 5 else "UNKNOWN",
            "alert_level": AlertLevel(alert).name if alert < 5 else "UNKNOWN",
            "uptime_s": uptime,
        }
