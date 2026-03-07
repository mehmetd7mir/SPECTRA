"""
Serial bridge - PC ↔ STM32 UART haberleşme köprüsü.

pyserial kullanarak STM32 ile haberleşir.
thread-safe: arka planda okuma, ana thread'den yazma.

eğer STM32 bağlı değilse simülasyon modu (mock) devreye girer.
bu sayede dashboard ve simülasyon STM32 olmadan da çalışır.

# gerçek cihaz takılıyken: /dev/cu.usbmodem... (mac)
# veya /dev/ttyACM0 (linux)
# windows: COM3, COM4 vs.
"""

import time
import threading
import queue
from typing import Optional, Callable, List

from .protocol import (
    SpectraPacket, SpectraProtocol, Command,
    NodeMode_STM32, AlertLevel,
    START_BYTE, END_BYTE,
)


class SerialBridge:
    """
    PC ↔ STM32 seri haberleşme köprüsü.

    Parameters
    ----------
    port : str
        seri port (/dev/cu.usbmodem... veya COM3)
    baudrate : int
        haberleşme hızı (STM32 firmware'de aynı olmalı)
    mock : bool
        True ise gerçek seri port kullanmaz,
        simülasyon modu çalışır
    """

    def __init__(
        self,
        port: str = "/dev/cu.usbmodem14103",
        baudrate: int = 115200,
        mock: bool = True,
    ):
        self.port = port
        self.baudrate = baudrate
        self.mock = mock

        # seri bağlantı (mock=False olduğunda)
        self._serial = None
        self.is_connected = False

        # thread-safe kuyruklar
        self._rx_queue: queue.Queue = queue.Queue(maxsize=100)
        self._tx_queue: queue.Queue = queue.Queue(maxsize=100)

        # alınan paketler için callback
        self._on_packet: Optional[Callable] = None

        # arka plan thread'leri
        self._rx_thread: Optional[threading.Thread] = None
        self._running = False

        # mock state (simüle edilmiş STM32 durumu)
        self._mock_state = {
            "mode": NodeMode_STM32.NORMAL,
            "alert": AlertLevel.NONE,
            "temperature": 25.0,
            "light": 2048,
            "distance": 150,
            "pot": 2048,
            "uptime": 0,
        }

    def connect(self) -> bool:
        """bağlantıyı aç"""
        if self.mock:
            self.is_connected = True
            self._running = True
            # mock heartbeat thread
            self._rx_thread = threading.Thread(
                target=self._mock_receiver, daemon=True
            )
            self._rx_thread.start()
            return True

        try:
            import serial
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.1,
            )
            self.is_connected = True
            self._running = True

            # gerçek seri okuma thread'i
            self._rx_thread = threading.Thread(
                target=self._serial_receiver, daemon=True
            )
            self._rx_thread.start()
            return True

        except Exception as e:
            print(f"⚠️ Seri port açılamadı: {e}")
            print("   Mock moda geçiliyor...")
            self.mock = True
            return self.connect()

    def disconnect(self):
        """bağlantıyı kapat"""
        self._running = False
        if self._rx_thread:
            self._rx_thread.join(timeout=2.0)
        if self._serial:
            self._serial.close()
        self.is_connected = False

    def send_packet(self, packet: SpectraPacket):
        """paket gönder"""
        if not self.is_connected:
            return

        if self.mock:
            self._mock_process(packet)
        else:
            raw = packet.to_bytes()
            self._serial.write(raw)

    def set_mode(self, mode: int):
        """mod değiştir"""
        self.send_packet(SpectraProtocol.set_mode(mode))

    def set_alert(self, level: int):
        """alarm seviyesi"""
        self.send_packet(SpectraProtocol.set_alert(level))

    def display(self, text: str):
        """OLED'e yazı"""
        self.send_packet(SpectraProtocol.display_text(text))

    def buzzer(self, on: bool):
        """buzzer kontrol"""
        self.send_packet(SpectraProtocol.buzzer(on))

    def request_status(self):
        """durum iste"""
        self.send_packet(SpectraProtocol.request_status())

    def get_received(self) -> Optional[SpectraPacket]:
        """alınan paketi oku (non-blocking)"""
        try:
            return self._rx_queue.get_nowait()
        except queue.Empty:
            return None

    def get_all_received(self) -> List[SpectraPacket]:
        """tüm alınan paketleri oku"""
        packets = []
        while not self._rx_queue.empty():
            try:
                packets.append(self._rx_queue.get_nowait())
            except queue.Empty:
                break
        return packets

    def on_packet(self, callback: Callable):
        """paket alındığında çağrılacak callback"""
        self._on_packet = callback

    # --- seri okuma thread'leri ---

    def _serial_receiver(self):
        """gerçek seri porttan paket oku"""
        buffer = bytearray()
        while self._running:
            try:
                data = self._serial.read(64)
                if data:
                    buffer.extend(data)
                    self._parse_buffer(buffer)
            except Exception:
                time.sleep(0.1)

    def _parse_buffer(self, buffer: bytearray):
        """buffer'dan paket parse et"""
        while len(buffer) >= 5:
            # START byte ara
            start_idx = buffer.find(bytes([START_BYTE]))
            if start_idx < 0:
                buffer.clear()
                return
            if start_idx > 0:
                del buffer[:start_idx]

            if len(buffer) < 5:
                return

            length = buffer[2]
            packet_len = 5 + length

            if len(buffer) < packet_len:
                return  # eksik veri, bekle

            raw = bytes(buffer[:packet_len])
            del buffer[:packet_len]

            packet = SpectraPacket.from_bytes(raw)
            if packet:
                self._rx_queue.put(packet)
                if self._on_packet:
                    self._on_packet(packet)

    def _mock_receiver(self):
        """mock mod: sahte STM32 cevapları üret"""
        import random
        while self._running:
            time.sleep(1.0)
            self._mock_state["uptime"] += 1

            # sahte sensör verileri üret (gerçekçi değişimler)
            self._mock_state["temperature"] += random.uniform(-0.3, 0.3)
            self._mock_state["light"] += random.randint(-50, 50)
            self._mock_state["light"] = max(0, min(4095, self._mock_state["light"]))
            self._mock_state["distance"] += random.randint(-5, 5)
            self._mock_state["distance"] = max(2, min(400, self._mock_state["distance"]))

            # heartbeat gönder
            import struct
            heartbeat = SpectraPacket(
                Command.HEARTBEAT,
                bytes([int(self._mock_state["mode"])]),
            )
            self._rx_queue.put(heartbeat)

            # her 3 saniyede sensör verisi
            if self._mock_state["uptime"] % 3 == 0:
                temp = int(self._mock_state["temperature"] * 10)
                light = self._mock_state["light"]
                dist = self._mock_state["distance"] * 10
                pot = self._mock_state["pot"]
                sensor_data = struct.pack("<HHHH", temp, light, dist, pot)
                sensor_pkt = SpectraPacket(Command.SENSOR_DATA, sensor_data)
                self._rx_queue.put(sensor_pkt)

    def _mock_process(self, packet: SpectraPacket):
        """mock modda gelen komutu işle"""
        if packet.command == Command.SET_MODE:
            if packet.data:
                self._mock_state["mode"] = packet.data[0]
                ack = SpectraPacket(Command.MODE_ACK, packet.data)
                self._rx_queue.put(ack)

        elif packet.command == Command.SET_ALERT_LEVEL:
            if packet.data:
                self._mock_state["alert"] = packet.data[0]

        elif packet.command == Command.REQUEST_STATUS:
            import struct
            data = struct.pack(
                "<BBH",
                int(self._mock_state["mode"]),
                int(self._mock_state["alert"]),
                self._mock_state["uptime"],
            )
            status = SpectraPacket(Command.STATUS_REPORT, data)
            self._rx_queue.put(status)

    @property
    def mock_state(self) -> dict:
        """mock durumu (test için)"""
        return dict(self._mock_state)

    def __repr__(self):
        mode = "MOCK" if self.mock else self.port
        status = "🟢" if self.is_connected else "🔴"
        return f"SerialBridge({mode}) {status}"
