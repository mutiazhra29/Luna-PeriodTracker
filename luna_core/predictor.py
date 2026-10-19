from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, stdev
from typing import Sequence


@dataclass(frozen=True)
class CyclePrediction:
    next_period: date
    ovulation: date
    fertile_start: date
    fertile_end: date
    cycle_length: int
    cycle_day: int
    phase: str
    uncertainty_days: int
    irregular: bool


def predict_cycle(
    starts: Sequence[date],
    today: date,
    default_cycle: int = 28,
    period_length: int = 5,
) -> CyclePrediction | None:
    ordered = sorted(set(starts))
    if not ordered:
        return None

    lengths = [
        (later - earlier).days
        for earlier, later in zip(ordered, ordered[1:])
        if 15 <= (later - earlier).days <= 60
    ][-6:]
    cycle_length = round(mean(lengths)) if len(lengths) >= 2 else default_cycle
    uncertainty = round(stdev(lengths)) if len(lengths) >= 2 else 0
    irregular = len(lengths) >= 2 and max(lengths) - min(lengths) >= 7

    last_start = ordered[-1]
    next_period = last_start + timedelta(days=cycle_length)
    ovulation = next_period - timedelta(days=14)
    day_in_cycle = max(1, (today - last_start).days + 1)
    if day_in_cycle <= period_length:
        phase = "Menstruasi"
    elif ovulation - timedelta(days=5) <= today <= ovulation + timedelta(days=1):
        phase = "Masa subur"
    elif today < ovulation - timedelta(days=5):
        phase = "Folikular"
    else:
        phase = "Luteal"

    return CyclePrediction(
        next_period=next_period,
        ovulation=ovulation,
        fertile_start=ovulation - timedelta(days=5),
        fertile_end=ovulation + timedelta(days=1),
        cycle_length=cycle_length,
        cycle_day=day_in_cycle,
        phase=phase,
        uncertainty_days=uncertainty if irregular else 0,
        irregular=irregular,
    )
