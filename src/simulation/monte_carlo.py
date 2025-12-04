"""
Monte Carlo simülasyon motoru — Faz 7.

Aynı senaryoyu farklı rastgele tohumlarla N kez çalıştırır.
Sonuçların dağılımını istatistiksel olarak analiz eder.

Neden Monte Carlo?
  Taktik ağ simülasyon sonuçları stokastik (Poisson mesaj üretimi,
  sigmoid kanal kaybı, gürültü katkısı). Tek bir koşu yanıltıcı
  olabilir. 50+ koşunun ortalaması gerçek sistem davranışını yansıtır.

Paralel koşturma için multiprocessing kullanılır.
Sonuçlar CSV ve PNG olarak kaydedilir.
"""

import os
import time
import numpy as np
import csv
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from multiprocessing import Pool, cpu_count
from functools import partial


@dataclass
class RunResult:
    """Tek bir Monte Carlo koşusunun sonucu."""
    run_id: int
    seed: int
    scenario: str
    jammer_power: float
    duration: float

    delivery_rate: float = 0.0
    critical_rate: float = 0.0
    avg_mis: float = 0.0
    avg_link_quality: float = 0.0
    total_sent: int = 0
    total_filtered: int = 0
    total_decisions: int = 0
    avg_delay_ms: float = 0.0


@dataclass
class MonteCarloReport:
    """N koşunun istatistiksel özeti."""
    scenario: str
    n_runs: int
    results: List[RunResult] = field(default_factory=list)

    def summary(self) -> Dict:
        """ortamaça, std, min/max istatistikler döndür."""
        if not self.results:
            return {}

        def stat(key):
            vals = [getattr(r, key) for r in self.results]
            return {
                "mean":   round(float(np.mean(vals)), 4),
                "std":    round(float(np.std(vals)), 4),
                "min":    round(float(np.min(vals)), 4),
                "max":    round(float(np.max(vals)), 4),
                "p5":     round(float(np.percentile(vals, 5)), 4),
                "p95":    round(float(np.percentile(vals, 95)), 4),
            }

        return {
            "scenario":    self.scenario,
            "n_runs":      self.n_runs,
            "delivery_rate":    stat("delivery_rate"),
            "critical_rate":    stat("critical_rate"),
            "avg_mis":          stat("avg_mis"),
            "avg_link_quality": stat("avg_link_quality"),
            "avg_delay_ms":     stat("avg_delay_ms"),
            "total_filtered":   stat("total_filtered"),
        }

    def worst_case(self) -> Optional[RunResult]:
        """En düşük MIS'a sahip koşuyu döndür."""
        if not self.results:
            return None
        return min(self.results, key=lambda r: r.avg_mis)

    def best_case(self) -> Optional[RunResult]:
        """En yüksek MIS'a sahip koşuyu döndür."""
        if not self.results:
            return None
        return max(self.results, key=lambda r: r.avg_mis)

    def to_csv(self, path: str):
        """Tüm koşu sonuçlarını CSV olarak kaydet."""
        if not self.results:
            return
        fieldnames = [f.name for f in RunResult.__dataclass_fields__.values()]
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in self.results:
                writer.writerow({k: getattr(r, k) for k in fieldnames})


def _single_run(args) -> RunResult:
    """
    Tek bir Monte Carlo koşusu.
    multiprocessing Pool'a gönderilecek — basit fonksiyon olmalı.
    """
    run_id, seed, scenario_name, jammer_power, duration, message_rate, tick = args
    np.random.seed(seed)

    try:
        from src.network.topology import NetworkTopology
        from src.ew.spectrum import SpectrumEnvironment
        from src.ew.effects import EWEffectCalculator
        from src.engine.rules import RuleBasedEngine
        from src.simulation.scenario import Scenario, EventType
        from src.simulation.runner import SimulationRunner

        topo = NetworkTopology.from_yaml("config/network.yaml")
        spectrum = SpectrumEnvironment()
        ew = EWEffectCalculator(spectrum, topo)

        # jammer tipi
        jammer = None
        if scenario_name != "normal":
            if scenario_name == "barrage":
                from src.ew.jammer import create_barrage_jammer
                jammer = create_barrage_jammer("JAM_1", power_dbm=jammer_power)
            elif scenario_name == "spot":
                from src.ew.jammer import create_spot_jammer
                jammer = create_spot_jammer("JAM_1", power_dbm=jammer_power)
            elif scenario_name == "sweep":
                from src.ew.jammer import create_sweep_jammer
                jammer = create_sweep_jammer("JAM_1", power_dbm=jammer_power)
            if jammer:
                ew.add_jammer(jammer)

        # senaryo
        if scenario_name == "barrage":
            sc = Scenario.create_barrage_scenario(duration=duration)
        elif scenario_name in ("spot", "sweep"):
            sc = Scenario(scenario_name, duration=duration)
            sc.add_event(duration * 0.25, EventType.JAMMER_ON, "JAM_1")
            sc.add_event(duration * 0.75, EventType.JAMMER_OFF, "JAM_1")
        else:
            sc = Scenario("normal", duration=duration)

        engine = RuleBasedEngine(topo)
        runner = SimulationRunner(
            topology=topo, scenario=sc,
            message_rate=message_rate, tick_interval=tick,
            verbose=False, ew_calculator=ew, decision_engine=engine,
        )
        metrics = runner.run()
        sm = metrics.get_summary()

        return RunResult(
            run_id=run_id, seed=seed,
            scenario=scenario_name, jammer_power=jammer_power, duration=duration,
            delivery_rate=sm["delivery_rate"],
            critical_rate=sm["critical_rate"],
            avg_mis=sm["avg_mis"],
            avg_link_quality=float(np.mean(metrics.avg_link_qualities)) if metrics.avg_link_qualities else 0.0,
            total_sent=sm["total_sent"],
            total_filtered=metrics.messages_filtered,
            total_decisions=engine.get_summary()["total_decisions"],
            avg_delay_ms=sm["avg_delay_ms"],
        )

    except Exception as e:
        # hata durumunda boş sonuç döndür
        return RunResult(
            run_id=run_id, seed=seed,
            scenario=scenario_name, jammer_power=jammer_power, duration=duration,
        )


class MonteCarloEngine:
    """
    Monte Carlo simülasyon motoru.

    Parameters
    ----------
    n_runs : int
        kaç koşu çalıştırılacak
    use_parallel : bool
        True ise multiprocessing kullan (False = tek işlemci, debug için)
    n_workers : int, optional
        worker sayısı. None ise cpu_count() // 2
    """

    def __init__(
        self,
        n_runs: int = 50,
        use_parallel: bool = True,
        n_workers: Optional[int] = None,
    ):
        self.n_runs = n_runs
        self.use_parallel = use_parallel
        self.n_workers = n_workers or max(1, cpu_count() // 2)

    def run(
        self,
        scenario: str = "barrage",
        jammer_power: float = -70.0,
        duration: float = 100.0,
        message_rate: float = 0.5,
        tick: float = 1.0,
        seed_base: int = 42,
        verbose: bool = True,
    ) -> MonteCarloReport:
        """
        Monte Carlo simülasyonu koştur.

        Parameters
        ----------
        scenario : str
            'barrage' | 'spot' | 'sweep' | 'normal'
        """
        args_list = [
            (i, seed_base + i, scenario, jammer_power, duration, message_rate, tick)
            for i in range(self.n_runs)
        ]

        if verbose:
            print(f"\n{'='*60}")
            print(f"MONTE CARLO: {self.n_runs} koşu | senaryo={scenario}")
            print(f"Workers: {self.n_workers if self.use_parallel else 1}")
            print(f"{'='*60}")

        t0 = time.time()
        results = []

        if self.use_parallel:
            with Pool(processes=self.n_workers) as pool:
                for i, res in enumerate(pool.imap_unordered(_single_run, args_list)):
                    results.append(res)
                    if verbose and (i+1) % max(1, self.n_runs // 10) == 0:
                        print(f"  Tamamlanan: {i+1}/{self.n_runs} | ~MIS: {res.avg_mis:.1f}")
        else:
            for i, args in enumerate(args_list):
                res = _single_run(args)
                results.append(res)
                if verbose and (i+1) % max(1, self.n_runs // 5) == 0:
                    print(f"  Tamamlanan: {i+1}/{self.n_runs} | MIS: {res.avg_mis:.1f}")

        elapsed = time.time() - t0

        report = MonteCarloReport(scenario=scenario, n_runs=self.n_runs, results=results)

        if verbose:
            sm = report.summary()
            print(f"\n⏱  Süre: {elapsed:.1f}s ({elapsed/self.n_runs:.2f}s/koşu)")
            print("\n📊 İSTATİSTİKLER:")
            for key in ("delivery_rate", "critical_rate", "avg_mis", "avg_delay_ms"):
                st = sm.get(key, {})
                if st:
                    print(f"  {key:20s}: mean={st['mean']:.3f} ± {st['std']:.3f}  "
                          f"[p5={st['p5']:.3f} p95={st['p95']:.3f}]")

            worst = report.worst_case()
            best = report.best_case()
            if worst:
                print(f"\n🔴 En kötü: MIS={worst.avg_mis:.1f} (seed={worst.seed})")
            if best:
                print(f"🟢 En iyi : MIS={best.avg_mis:.1f} (seed={best.seed})")

        return report


# ─── Senaryo Karşılaştırma ─────────────────────────────────────────
def compare_scenarios(
    scenarios: List[str],
    n_runs: int = 30,
    jammer_power: float = -70.0,
    duration: float = 80.0,
    save_csv: bool = False,
    verbose: bool = True,
) -> Dict[str, MonteCarloReport]:
    """
    Birden fazla senaryoyu çalıştırıp karşılaştır.
    Sonucu {'barrage': MonteCarloReport, ...} olarak döner.
    """
    engine = MonteCarloEngine(n_runs=n_runs, use_parallel=True)
    reports = {}

    for sc in scenarios:
        if verbose:
            print(f"\n>>> Senaryo: {sc.upper()}")
        report = engine.run(
            scenario=sc, jammer_power=jammer_power, duration=duration, verbose=verbose
        )
        reports[sc] = report

        if save_csv:
            os.makedirs("results", exist_ok=True)
            report.to_csv(f"results/mc_{sc}.csv")
            if verbose:
                print(f"  💾 results/mc_{sc}.csv kayıt edildi")

    if verbose:
        print(f"\n{'='*60}")
        print("KARŞILAŞTIRMA ÖZET (ortalama MIS):")
        for sc, rpt in reports.items():
            sm = rpt.summary()
            mis = sm["avg_mis"]
            dr = sm["delivery_rate"]
            print(f"  {sc:10s}: MIS={mis['mean']:.1f}±{mis['std']:.1f}  "
                  f"delivery={dr['mean']:.1%}")
        print(f"{'='*60}")

    return reports


# ─── Çalıştırma ───────────────────────────────────────────────────
if __name__ == "__main__":
    # hızlı test: 3 senaryo, 20 koşu
    compare_scenarios(
        scenarios=["normal", "barrage", "spot"],
        n_runs=20,
        jammer_power=-70.0,
        duration=60.0,
        save_csv=True,
        verbose=True,
    )
