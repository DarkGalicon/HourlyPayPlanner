from collections.abc import Collection, Iterable
from dataclasses import dataclass

from hourly_pay.domain.anomalies import detect_workload_anomalies
from hourly_pay.domain.models import ImportWarning, WorkloadItem
from hourly_pay.domain.normalization import WorkloadBreakdown, summarize_workload


@dataclass(frozen=True, slots=True)
class NormalizedWorkload:
    items: tuple[WorkloadItem, ...]
    breakdown: WorkloadBreakdown
    warnings: tuple[ImportWarning, ...]


def normalize_workload(
    items: Iterable[WorkloadItem],
    *,
    known_control_kinds: Collection[str] = ("Эк", "Зч"),
) -> NormalizedWorkload:
    materialized = tuple(items)
    return NormalizedWorkload(
        items=materialized,
        breakdown=summarize_workload(materialized),
        warnings=tuple(
            detect_workload_anomalies(
                materialized,
                known_control_kinds=known_control_kinds,
            )
        ),
    )
