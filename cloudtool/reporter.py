"""
reporter.py
Tracks ActionResults across a full run and prints a clean summary.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

from cloudtool.apt_manager import ActionResult, Status
from cloudtool.logger import get_logger

log = get_logger(__name__)


@dataclass
class RunReport:
    start_time: float = field(default_factory=time.time)
    source_results: list[ActionResult] = field(default_factory=list)
    package_results: list[ActionResult] = field(default_factory=list)
    cache_result: ActionResult | None = None

    def record_source(self, result: ActionResult) -> None:
        self.source_results.append(result)

    def record_package(self, result: ActionResult) -> None:
        self.package_results.append(result)

    def record_cache(self, result: ActionResult) -> None:
        self.cache_result = result

    def has_failures(self) -> bool:
        all_results = self.source_results + self.package_results
        if self.cache_result:
            all_results.append(self.cache_result)
        return any(r.status == Status.FAILED for r in all_results)

    def _summarise(self, results: list[ActionResult]) -> dict:
        return {
            "ok":      sum(1 for r in results if r.status == Status.OK),
            "skipped": sum(1 for r in results if r.status == Status.SKIPPED),
            "failed":  sum(1 for r in results if r.status == Status.FAILED),
        }

    def print_summary(self, log_file: Path | None = None) -> None:
        elapsed = time.time() - self.start_time
        pkg   = self._summarise(self.package_results)
        src   = self._summarise(self.source_results)

        lines = [
            "",
            "=" * 52,
            "  Ubuntu Cloud Tooling — Run Summary",
            "=" * 52,
            f"  Packages : {pkg['ok']:>3} installed  "
            f"{pkg['skipped']:>3} skipped  "
            f"{pkg['failed']:>3} failed",
            f"  Sources  : {src['ok']:>3} added      "
            f"{src['skipped']:>3} skipped  "
            f"{src['failed']:>3} failed",
            f"  Duration : {elapsed:.1f}s",
        ]

        if log_file:
            lines.append(f"  Log      : {log_file}")

        if self.has_failures():
            lines.append("  Status   : FAILED — check log for details")
        else:
            lines.append("  Status   : SUCCESS")

        lines.append("=" * 52)

        output = "\n".join(lines)
        print(output)
        log.info(output)