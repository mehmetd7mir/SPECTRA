# 🛡️ SPECTRA

**Mission-Impact Driven Spectrum Resilience & Tactical Network Orchestrator**

> Elektromanyetik savaş (EW) altında taktik ağların görev başarım oranını hesaplayan, haberleşmeyi ve düğüm davranışını gerçek zamanlı yeniden yapılandıran bir karar destek sistemi.

---

## 📖 Proje Özeti

Klasik EW sistemleri sinyali algılar, sınıflandırır ve raporlar. SPECTRA bunu bir adım ileri taşıyarak şu soruyu sorar: **"ağdaki bozulma göreve ne kadar zarar veriyor?"**

Bu soruyu yanıtlamak için:

- Barrage / Spot / Sweep jammer modellerini simüle eder
- Her linkin SNR degradasyonunu hesaplar
- Bir **Mission Impact Score (MIS)** üretir
- Kural tabanlı + ML destekli hibrit motor ile düğümleri otonom yönetir
- STM32 MCU üzerindeki edge node ile kapalı çevrim oluşturur

---

## 🗂️ Proje Yapısı

```
SPECTRA/
├── config/
│   └── network.yaml          # Ağ topolojisi (düğümler, linkler, parametreler)
├── firmware/
│   └── spectra_node.c        # STM32F407 C firmware taslağı
├── src/
│   ├── network/              # Faz 1 — Taktik ağ katmanı
│   │   ├── message.py        # Mesaj tipleri ve öncelikleri
│   │   ├── node.py           # TacticalNode — mod yönetimi, kuyruk
│   │   ├── channel.py        # Link modeli (SNR, gecikme, PER, jamming)
│   │   └── topology.py       # Ağ yönetimi, BFS rota bulma
│   ├── ew/                   # Faz 2 — Elektronik Harp modeli
│   │   ├── spectrum.py       # Spektrum ortamı, frekans bandları
│   │   ├── jammer.py         # Barrage / Spot / Sweep karıştırıcı modelleri
│   │   └── effects.py        # EW etkileri → kanal → Mission Impact Score
│   ├── engine/               # Faz 3-4 — Karar motorları
│   │   ├── policy.py         # Politika eşikleri ve aksiyon tanımları
│   │   ├── safety_gate.py    # Deterministik güvenlik filtresi
│   │   ├── rules.py          # Kural tabanlı karar motoru
│   │   └── ml_predictor.py   # RandomForest link kalite tahmini
│   ├── simulation/           # Simülasyon motoru
│   │   ├── scenario.py       # Zamanlı olay yöneticisi
│   │   ├── runner.py         # Ayrık zamanlı ana döngü
│   │   └── monte_carlo.py    # Paralel Monte Carlo analizi
│   └── stm32/                # Faz 5 — STM32 haberleşme
│       ├── protocol.py       # Binary UART protokolü (CRC korumalı)
│       └── serial_bridge.py  # PC tarafı köprü (mock + gerçek UART)
├── dashboard.py              # Streamlit görselleştirme paneli
├── requirements.txt
└── README.md
```

---

## ⚙️ Kurulum

Python **3.9+** gereklidir.

```bash
git clone https://github.com/mehmetd7mir/SPECTRA.git
cd SPECTRA
pip install -r requirements.txt
```

---

## 🚀 Kullanım

### Simülasyon Koştur

```bash
python -m src.simulation.runner
```

### Streamlit Dashboard

```bash
streamlit run dashboard.py
```

Açılır panelden senaryo tipi, jammer gücü, süre gibi parametreleri ayarlayıp simülasyonu başlatabilirsin. Grafiklerde MIS, delivery rate ve link kalitesi canlı olarak güncellenir.

### Monte Carlo Analizi

```bash
python -m src.simulation.monte_carlo
```

Farklı senaryoları otomatik karşılaştırır, sonuçları `results/` klasörüne CSV olarak kaydeder.

---

## 🔬 Modül Detayları

### `src/network/` — Taktik Ağ Katmanı

| Sınıf/Fonksiyon | Açıklama |
|---|---|
| `TacticalMessage` | Mesaj tipi: `track_update`, `threat_alert`, `command`, `health_report` |
| `MessagePriority` | `CRITICAL > HIGH > MEDIUM > LOW` — filtreleme için kullanılır |
| `TacticalNode` | Düğüm rolleri: `COMMAND_CENTER`, `SENSOR`, `RELAY`, `WEAPON` |
| `NodeMode` | `NORMAL → DEGRADED → LOCAL_AUTONOMY → SILENT` |
| `TacticalChannel` | SNR → PER dönüşümü (sigmoid bazlı), jamming, bant genişliği kısıtlaması |
| `NetworkTopology` | BFS rota bulma, YAML'dan yükleme, hop-by-hop iletim |

### `src/ew/` — EW Modeli

| Modül | Açıklama |
|---|---|
| `SpectrumEnvironment` | VHF/UHF/L/S bandlarını, gürültü seviyelerini ve anlık bozulmayı modeller |
| `Jammer` (3 tip) | **Barrage**: geniş band, düşük güç / **Spot**: hedefe yüksek güç / **Sweep**: tarama |
| `EWEffectCalculator` | Jammer → spectrum → kanal zincirini yönetir; **MIS** üretir |

**Mission Impact Score (MIS):** 0–100 arası ağırlıklı skor. İletişim kalitesi, sensör kapsama, komuta bağlantısı ve silah sistemi yanıt süresini birleştirir.

### `src/engine/` — Karar Motorları

**Kural tabanlı motor:** Link kalitesi + MIS eşiğine bakarak düğüm modlarını değiştirir, mesajları filtreler.

**SafetyGate:** Mod değişikliklerine cooldown uygular, otomatik `SILENT` geçişini engeller. Savunma uygulamalarında explainability için kritik.

**ML Predictor:** Sliding window üzerinden lineer ekstrapolasyon veya (eğitilmişse) RandomForest ile gelecekteki link kalitesini tahmin eder. Motor proaktif karar alabilir.

### `src/stm32/` — STM32 Haberleşme

Binary protokol: `[0xAA | CMD | LEN | DATA... | CRC_XOR | 0x55]`

JPC tarafı (`SerialBridge`) hem gerçek UART (`pyserial`) hem de mock modu destekler. STM32 bağlı değilken de simülasyon ve dashboard tamamen çalışır. C taslağı `firmware/spectra_node.c` içindedir; STM32CubeIDE'ye aktarılması için hazırdır.

---

## 📊 Örnek Sonuçlar

| Senaryo | Avg MIS | Delivery Rate | Filtrelenen Msg |
|---|---|---|---|
| Jammer yok | 91.3 | %100 | 0 |
| Barrage (−70 dBm) | 28.9 | %92.5 | ~50 |
| Spot (−65 dBm) | 55.2 | %95.1 | ~30 |

Kural motoru jammer altında düğümleri `LOCAL_AUTONOMY` moduna alır, yalnızca `CRITICAL` mesajlara izin verir. Jammer kapandıktan sonra `LOCAL_AUTONOMY → DEGRADED → NORMAL` kademeli dönüş gerçekleşir.

---

## 🧠 Neler Öğrendim

Çoğu EW projesi "sinyali algıla, raporla" ile biter. Burada **etkiyi hesaplayıp ona göre davranmak** üzerine kurulu bir sistem yapmak istiyordum.

- Ayrık zamanlı simülasyonun nasıl tasarlandığını (Poisson mesaj üretimi, tick bazlı döngü)
- Shannon'ın kapasite teoremini kanal modeline nasıl yansıtacağımı (SNR → PER sigmoid)
- Kural tabanlı ve ML motorunun aynı safety-gate altında nasıl çalışabileceğini
- Binary UART protokolü tasarımını (CRC, framing)
- STM32 tarafındaki fail-operational mantığını (PC bağlantısı kesilince `LOCAL_AUTONOMY`)

---

## 🔧 Donanım

STM32 edge node için kullanılan bileşenler:

| Bileşen | Bağlantı | Kullanım |
|---|---|---|
| STM32F407G-DISC1 | — | MCU |
| LM35 | PA0 (ADC) | Sıcaklık ölçümü |
| KY-018 LDR | PA1 (ADC) | Ortam ışık seviyesi |
| HC-SR04 | PB6/PB7 | Ultrasonik mesafe |
| Potansiyometre | PA4 (ADC) | Manuel parametre girişi |
| SSD1306 OLED | PB8/PB9 (I2C) | Anlık mod gösterimi |
| Passive Buzzer | PA5 | Alarm sesi |
| USB (UART) | PA2/PA3 | PC haberleşme |

---

## 📄 Gereksinimler

```
numpy
scipy
pyyaml
pyserial
matplotlib
plotly
streamlit
scikit-learn
pandas
```

---

*mehmetd7mir — Elektrik-Elektronik Mühendisliği*
