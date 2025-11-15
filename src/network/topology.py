"""
Network topology manager.

tüm düğümleri ve kanalları bir arada tutar.
mesaj göndermek istediğinde rota bulur,
kanal üzerinden iletir, istatistik toplar.

YAML dosyasından topoloji yükleme de burada.

# bu sınıf biraz graph veri yapısı gibi düşünülebilir
# düğümler = vertex, kanallar = edge
# rota bulma = shortest path (BFS kullandım dijkstra yerine,
# ağırlıklı en kısa yol şimdilik gerek yok)
"""

import yaml
import math
from collections import deque
from typing import Dict, List, Optional, Tuple

from .node import TacticalNode, NodeRole, NodeMode
from .channel import TacticalChannel
from .message import TacticalMessage


class NetworkTopology:
    """
    Taktik ağ topolojisi.

    düğümler ve aralarındaki link'leri yönetir.
    mesaj gönderiminde rota bulur ve kanal üzerinden iletir.

    Parameters
    ----------
    name : str
        topoloji adı (loglarda kullanılır)
    """

    def __init__(self, name: str = "tactical_net"):
        self.name = name
        self.nodes: Dict[str, TacticalNode] = {}
        self.channels: Dict[str, TacticalChannel] = {}
        # her düğümün hangi kanallara bağlı olduğunu tutar
        # adjacency list gibi düşün
        self._adjacency: Dict[str, List[str]] = {}

    def add_node(self, node: TacticalNode):
        """düğüm ekle"""
        self.nodes[node.node_id] = node
        if node.node_id not in self._adjacency:
            self._adjacency[node.node_id] = []

    def add_link(
        self,
        node_a_id: str,
        node_b_id: str,
        base_snr: float = 20.0,
        bandwidth: float = 9600.0,
        base_delay: float = 10.0,
    ) -> TacticalChannel:
        """
        iki düğüm arasına link ekle (iki yönlü).

        bağlantı kanalını oluşturur ve her iki düğüme de
        komşu olarak ekler.
        """
        # kanal id'si: alfabetik sıralı iki düğüm adı
        link_id = self._make_link_id(node_a_id, node_b_id)

        channel = TacticalChannel(
            node_a=node_a_id,
            node_b=node_b_id,
            base_snr=base_snr,
            bandwidth=bandwidth,
            base_delay=base_delay,
        )
        self.channels[link_id] = channel

        # adjacency güncelle
        if node_b_id not in self._adjacency.get(node_a_id, []):
            self._adjacency.setdefault(node_a_id, []).append(node_b_id)
        if node_a_id not in self._adjacency.get(node_b_id, []):
            self._adjacency.setdefault(node_b_id, []).append(node_a_id)

        # düğümlerin komşu listesini de güncelle
        if node_b_id not in self.nodes[node_a_id].neighbors:
            self.nodes[node_a_id].neighbors.append(node_b_id)
        if node_a_id not in self.nodes[node_b_id].neighbors:
            self.nodes[node_b_id].neighbors.append(node_a_id)

        return channel

    def get_channel(self, node_a: str, node_b: str) -> Optional[TacticalChannel]:
        """iki düğüm arasındaki kanalı getir"""
        link_id = self._make_link_id(node_a, node_b)
        return self.channels.get(link_id)

    def find_route(self, source: str, destination: str) -> Optional[List[str]]:
        """
        kaynak → hedef arası en kısa rota bul (BFS).

        dönenler: düğüm id listesi, örn: ['SENSOR_A', 'RELAY_1', 'HQ']
        rota yoksa None döner.

        # dijkstra da kullanabilirdik ama BFS şimdilik yeterli
        # faz 3'te link kalitesine göre ağırlıklı rota eklenecek
        """
        if source not in self.nodes or destination not in self.nodes:
            return None

        if source == destination:
            return [source]

        # BFS
        visited = {source}
        queue = deque([(source, [source])])

        while queue:
            current, path = queue.popleft()

            for neighbor in self._adjacency.get(current, []):
                if neighbor in visited:
                    continue

                new_path = path + [neighbor]

                if neighbor == destination:
                    return new_path

                visited.add(neighbor)

                # sadece online ve SILENT olmayan düğümlerden geç
                node = self.nodes.get(neighbor)
                if node and node.is_online and node.mode != NodeMode.SILENT:
                    queue.append((neighbor, new_path))

        return None  # rota bulunamadı

    def send_message(self, msg: TacticalMessage, current_time: float = None) -> dict:
        """
        mesajı ağ üzerinden gönder.

        rota bulur, her hop'ta kanaldan geçirir.
        sonuç olarak iletim raporu döner.

        Returns
        -------
        dict with:
            - success: bool
            - route: list of node ids
            - total_delay_ms: float
            - hops: int
            - failed_at: str or None (hangi link'te kaybedildi)
        """
        result = {
            "success": False,
            "route": [],
            "total_delay_ms": 0.0,
            "hops": 0,
            "failed_at": None,
            "msg_id": msg.msg_id,
        }

        # rota bul
        route = self.find_route(msg.source, msg.destination)
        if route is None:
            result["failed_at"] = "NO_ROUTE"
            return result

        result["route"] = route

        # BROADCAST mesajları - tüm düğümlere gönder
        # (basit flood, gerçek sistemde daha karmaşık)
        if msg.destination == "BROADCAST":
            route = [msg.source] + [
                n for n in self.nodes if n != msg.source
            ]

        # hop hop gönder
        total_delay = 0.0
        for i in range(len(route) - 1):
            hop_from = route[i]
            hop_to = route[i + 1]

            channel = self.get_channel(hop_from, hop_to)
            if channel is None:
                result["failed_at"] = f"{hop_from}→{hop_to} (no channel)"
                return result

            success, delay = channel.transmit(msg, current_time)
            msg.hop_count += 1

            if not success:
                result["failed_at"] = f"{hop_from}→{hop_to}"
                result["hops"] = i + 1
                return result

            total_delay += delay

        # başarılı teslim
        msg.mark_delivered(current_time)
        result["success"] = True
        result["total_delay_ms"] = round(total_delay, 2)
        result["hops"] = len(route) - 1

        # hedef düğümde al
        dest_node = self.nodes.get(msg.destination)
        if dest_node:
            dest_node.receive_message(msg)

        return result

    def get_network_status(self) -> dict:
        """tüm ağın durumunu özetle"""
        # ortalama link kalitesi
        qualities = [ch.link_quality for ch in self.channels.values()]
        avg_quality = sum(qualities) / len(qualities) if qualities else 0

        # mod dağılımı
        mode_counts = {}
        for node in self.nodes.values():
            mode_counts[node.mode.value] = mode_counts.get(node.mode.value, 0) + 1

        # toplam istatistikler
        total_sent = sum(ch.total_sent for ch in self.channels.values())
        total_delivered = sum(ch.total_delivered for ch in self.channels.values())

        return {
            "name": self.name,
            "nodes": len(self.nodes),
            "links": len(self.channels),
            "avg_link_quality": round(avg_quality, 3),
            "mode_distribution": mode_counts,
            "total_sent": total_sent,
            "total_delivered": total_delivered,
            "delivery_rate": round(total_delivered / max(1, total_sent), 3),
        }

    @classmethod
    def from_yaml(cls, filepath: str) -> "NetworkTopology":
        """
        YAML dosyasından topoloji yükle.

        # YAML formatı config/network.yaml'da tanımlı
        """
        with open(filepath, "r") as f:
            config = yaml.safe_load(f)

        topo = cls(name=config.get("name", "loaded_network"))

        # düğümleri ekle
        for node_cfg in config.get("nodes", []):
            role = NodeRole(node_cfg["role"])
            pos = tuple(node_cfg.get("position", [0, 0]))
            node = TacticalNode(
                node_id=node_cfg["id"],
                role=role,
                position=pos,
            )
            topo.add_node(node)

        # linkleri ekle
        for link_cfg in config.get("links", []):
            node_a = link_cfg[0]
            node_b = link_cfg[1]
            params = link_cfg[2] if len(link_cfg) > 2 else {}
            topo.add_link(
                node_a, node_b,
                base_snr=params.get("base_snr", 20.0),
                bandwidth=params.get("bandwidth", 9600.0),
                base_delay=params.get("base_delay", 10.0),
            )

        return topo

    def _make_link_id(self, a: str, b: str) -> str:
        """link id oluştur - sıralı olsun ki A-B = B-A"""
        return f"{min(a,b)}_{max(a,b)}"

    def distance_between(self, node_a: str, node_b: str) -> float:
        """iki düğüm arası mesafe (metre)"""
        a = self.nodes.get(node_a)
        b = self.nodes.get(node_b)
        if not a or not b:
            return float('inf')
        dx = a.position[0] - b.position[0]
        dy = a.position[1] - b.position[1]
        return math.sqrt(dx*dx + dy*dy)

    def __repr__(self):
        return (
            f"NetworkTopology('{self.name}') "
            f"{len(self.nodes)} nodes, {len(self.channels)} links"
        )
