"""
ML-based link quality predictor and mission score estimator.

kural tabanlı motor "şu an ne yapmalı" sorusuna cevap verir.
ML motoru "gelecekte ne olacak" sorusuna cevap verir.

ikisi birlikte çalışınca:
- ML: "5 saniye sonra link kalitesi %20'ye düşecek"
- Rules: "o zaman şimdiden DEGRADED moduna geç"

bu sayede reaktif değil proaktif karar verilebilir.

eğitim verisi simülasyondan üretilir (sentetik).
model basit: RandomForest ve küçük MLP.

# bilerek basit modeller kullanıyorum çünkü:
# 1. açıklanabilirlik (explainability) önemli
# 2. gerçek zamanlı çalışmalı (inference hızlı)
# 3. az veriyle de çalışmalı
# 4. savunma sektörü black-box sevmez
"""

import numpy as np
import pickle
import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class PredictionResult:
    """ML tahmin sonucu"""
    predicted_quality: float       # tahmini link kalitesi (0-1)
    predicted_mis: float           # tahmini MIS (0-100)
    confidence: float              # tahmin güveni (0-1)
    features_used: List[str] = field(default_factory=list)
    # kural motoru bu sonucu kullanarak önceden aksiyon alabilir
    recommended_action: str = ""


class LinkQualityPredictor:
    """
    Link kalitesi tahmin modeli.

    son N adımdaki link kalitesi verilerini kullanarak
    gelecekteki kaliteyi tahmin eder.

    basit yaklaşım: sliding window + trend analizi.
    daha sonra sklearn RandomForest ile değiştirilebilir.

    Parameters
    ----------
    window_size : int
        kaç adım geriye bakacak
    prediction_horizon : int
        kaç adım ilerisi tahmin edilecek
    """

    def __init__(self, window_size: int = 10, prediction_horizon: int = 5):
        self.window_size = window_size
        self.horizon = prediction_horizon

        # geçmiş veriler (link_id → quality listesi)
        self._history: Dict[str, List[float]] = {}

        # eğitilmiş model (None = henüz eğitilmemiş, basit trend kullan)
        self._model = None
        self._is_trained = False

        # eğitim verisi biriktirici
        self._training_X: List[List[float]] = []
        self._training_y: List[float] = []

    def update(self, link_id: str, quality: float):
        """yeni kalite ölçümü ekle"""
        if link_id not in self._history:
            self._history[link_id] = []
        self._history[link_id].append(quality)

        # çok uzun büyümesin
        if len(self._history[link_id]) > 200:
            self._history[link_id] = self._history[link_id][-100:]

    def predict(self, link_id: str) -> Optional[float]:
        """
        link kalitesinin gelecekteki değerini tahmin et.

        eğitilmiş model varsa model kullan,
        yoksa basit trend analizi yap.

        basit trend: son window_size adımda kalite artıyor mu azalıyor mu?
        lineer extrapolasyon ile tahmin.

        Returns None if not enough data
        """
        history = self._history.get(link_id, [])
        if len(history) < 3:  # en az 3 veri lazım
            return None

        # son window_size veriyi al
        window = history[-self.window_size:] if len(history) >= self.window_size else history

        if self._is_trained and self._model is not None:
            return self._predict_with_model(window)
        else:
            return self._predict_with_trend(window)

    def _predict_with_trend(self, window: List[float]) -> float:
        """
        basit lineer trend ile tahmin.

        # numpy polyfit ile 1. derece polinom (doğru) uyduruyoruz
        # y = mx + b, sonra x = len(window) + horizon için tahmin
        """
        x = np.arange(len(window))
        y = np.array(window)

        # lineer fit
        try:
            coeffs = np.polyfit(x, y, deg=1)
            slope = coeffs[0]
            intercept = coeffs[1]

            # gelecek tahmin
            future_x = len(window) + self.horizon
            predicted = slope * future_x + intercept

            # sınırla (0-1 arası)
            return float(max(0.0, min(1.0, predicted)))
        except Exception:
            # fit başarısız olursa son değeri döndür
            return float(window[-1])

    def _predict_with_model(self, window: List[float]) -> float:
        """eğitilmiş ML modeli ile tahmin (faz 4 - sonra implement)"""
        features = self._extract_features(window)
        try:
            pred = self._model.predict([features])[0]
            return float(max(0.0, min(1.0, pred)))
        except Exception:
            return self._predict_with_trend(window)

    def _extract_features(self, window: List[float]) -> List[float]:
        """
        ham kalite verilerinden özellik çıkar.

        - ortalama
        - standart sapma (ne kadar salınıyor)
        - trend (eğim)
        - son değer
        - min/max
        - degradation rate (ne kadar hızlı düşüyor)
        """
        arr = np.array(window)
        features = [
            float(np.mean(arr)),              # ort
            float(np.std(arr)),               # std
            float(arr[-1]),                    # son
            float(np.min(arr)),               # min
            float(np.max(arr)),               # max
            float(arr[-1] - arr[0]),           # toplam değişim
            float(np.mean(np.diff(arr))) if len(arr) > 1 else 0.0,  # ort değişim hızı
        ]
        # window'u sabit uzunluğa pad et
        padded = list(arr[-self.window_size:]) if len(arr) >= self.window_size else list(arr) + [0.0] * (self.window_size - len(arr))
        features.extend(padded)
        return features

    def collect_training_data(self, link_id: str, actual_future_quality: float):
        """
        eğitim verisi topla.

        simülasyon sırasında geçmiş veriyi ve gelecekteki gerçek
        kaliteyi kaydeder. sonra train() ile model eğitilir.
        """
        history = self._history.get(link_id, [])
        if len(history) < self.window_size:
            return

        window = history[-self.window_size:]
        features = self._extract_features(window)
        self._training_X.append(features)
        self._training_y.append(actual_future_quality)

    def train(self):
        """
        toplanan verilerle modeli eğit.

        sklearn RandomForest kullanıyoruz:
        - az veriyle iyi çalışır
        - overfitting riski düşük
        - feature importance verir (açıklanabilirlik)
        """
        if len(self._training_X) < 20:
            return False

        try:
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.model_selection import train_test_split

            X = np.array(self._training_X)
            y = np.array(self._training_y)

            # train/test split
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=42
            )

            # model eğit
            self._model = RandomForestRegressor(
                n_estimators=50,
                max_depth=8,
                random_state=42,
                n_jobs=-1,  # paralel eğit
            )
            self._model.fit(X_train, y_train)
            self._is_trained = True

            # accuracy
            train_score = self._model.score(X_train, y_train)
            test_score = self._model.score(X_test, y_test)

            return {
                "trained": True,
                "samples": len(X),
                "features": X.shape[1],
                "train_r2": round(train_score, 3),
                "test_r2": round(test_score, 3),
            }

        except ImportError:
            # sklearn yoksa trend'e devam
            return False

    def save_model(self, path: str):
        """modeli diske kaydet"""
        if self._model:
            with open(path, 'wb') as f:
                pickle.dump(self._model, f)

    def load_model(self, path: str):
        """modeli diskten yükle"""
        if os.path.exists(path):
            with open(path, 'rb') as f:
                self._model = pickle.load(f)
                self._is_trained = True


class MissionScorePredictor:
    """
    Görev etki skoru tahmincisi.

    link kalitelerini ve düğüm durumlarını alarak
    MIS'ın gelecekteki değerini tahmin eder.

    # aslında MIS, link kalitelerinin ağırlıklı ortalaması
    # olduğu için ML'e bile gerek yok, ama burada ML'in
    # "proaktif" karar verme yeteneğini gösteriyoruz
    """

    def __init__(self, link_predictor: LinkQualityPredictor):
        self.link_predictor = link_predictor

    def predict_mis(self, current_mis: float, link_qualities: Dict[str, float]) -> float:
        """
        gelecekteki MIS'ı tahmin et.

        her linkin tahmin edilen kalitesini kullanır.
        """
        predicted_qualities = []

        for link_id, current_q in link_qualities.items():
            predicted_q = self.link_predictor.predict(link_id)
            if predicted_q is not None:
                predicted_qualities.append(predicted_q)
            else:
                predicted_qualities.append(current_q)

        if not predicted_qualities:
            return current_mis

        # basit tahmin: link kaliteleri ortalamasından MIS hesapla
        avg_quality = sum(predicted_qualities) / len(predicted_qualities)
        predicted_mis = avg_quality * 100

        return round(predicted_mis, 1)

    def get_trend(self, link_qualities: Dict[str, float]) -> str:
        """
        genel trend: iyileşiyor mu, kötüleşiyor mu, stabil mi?
        karar motoruna yardımcı bilgi.
        """
        improvements = 0
        degradations = 0

        for link_id, current_q in link_qualities.items():
            predicted = self.link_predictor.predict(link_id)
            if predicted is None:
                continue
            if predicted > current_q + 0.05:
                improvements += 1
            elif predicted < current_q - 0.05:
                degradations += 1

        if degradations > improvements:
            return "DEGRADING"
        elif improvements > degradations:
            return "IMPROVING"
        else:
            return "STABLE"
