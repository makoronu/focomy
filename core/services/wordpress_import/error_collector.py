"""Error Collector for WordPress Import.

Comprehensive error tracking for debugging import issues.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ImportError:
    """Single import error record."""

    phase: str  # "authors", "posts", "media", "categories", "tags", "menus"
    item_id: int | str  # WP ID or slug
    item_title: str  # Human-readable identifier
    error_type: str  # "author_not_found", "transform_failed", etc.
    message: str  # Detailed error message
    traceback_str: str | None = None  # Exception traceback if available
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    context: dict[str, Any] = field(default_factory=dict)  # Additional debug info


class ErrorCollector:
    """Collect and manage import errors for debugging.

    Usage:
        collector = ErrorCollector()
        collector.add_error("posts", 123, "My Post", "author_not_found", "WP user 5 not found")
        collector.add_skip("posts", 456, "Draft Post", "no_author")

        # At end of import
        collector.to_log_file(Path("import_errors.log"))
        summary = collector.summary()
    """

    def __init__(self):
        self.errors: list[ImportError] = []
        self.skipped: list[ImportError] = []
        self.warnings: list[ImportError] = []
        self._counts: dict[str, dict[str, int]] = {}  # phase -> {error_type -> count}

    def add_error(
        self,
        phase: str,
        item_id: int | str,
        item_title: str,
        error_type: str,
        message: str,
        exc: Exception | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Add an error record.

        Args:
            phase: Import phase (authors, posts, media, etc.)
            item_id: WordPress ID or slug
            item_title: Human-readable title
            error_type: Error category for grouping
            message: Detailed error message
            exc: Optional exception object
            context: Optional additional debug info
        """
        tb_str = None
        if exc:
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

        error = ImportError(
            phase=phase,
            item_id=item_id,
            item_title=item_title,
            error_type=error_type,
            message=message,
            traceback_str=tb_str,
            context=context or {},
        )
        self.errors.append(error)
        self._increment_count(phase, error_type)

    def add_skip(
        self,
        phase: str,
        item_id: int | str,
        item_title: str,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Record a skipped item.

        Args:
            phase: Import phase
            item_id: WordPress ID or slug
            item_title: Human-readable title
            reason: Why the item was skipped
            context: Optional additional debug info
        """
        skip = ImportError(
            phase=phase,
            item_id=item_id,
            item_title=item_title,
            error_type="skipped",
            message=reason,
            context=context or {},
        )
        self.skipped.append(skip)
        self._increment_count(phase, f"skipped:{reason}")

    def add_warning(
        self,
        phase: str,
        item_id: int | str,
        item_title: str,
        warning_type: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Add a warning (non-fatal issue).

        Args:
            phase: Import phase
            item_id: WordPress ID or slug
            item_title: Human-readable title
            warning_type: Warning category
            message: Warning message
            context: Optional additional debug info
        """
        warning = ImportError(
            phase=phase,
            item_id=item_id,
            item_title=item_title,
            error_type=warning_type,
            message=message,
            context=context or {},
        )
        self.warnings.append(warning)

    def _increment_count(self, phase: str, error_type: str) -> None:
        """Increment error count for summary."""
        if phase not in self._counts:
            self._counts[phase] = {}
        if error_type not in self._counts[phase]:
            self._counts[phase][error_type] = 0
        self._counts[phase][error_type] += 1

    def summary(self) -> dict[str, Any]:
        """Get error summary for display.

        Returns:
            Dictionary with counts by phase and error type
        """
        return {
            "total_errors": len(self.errors),
            "total_skipped": len(self.skipped),
            "total_warnings": len(self.warnings),
            "by_phase": self._counts,
            "error_types": self._get_error_type_counts(),
        }

    def _get_error_type_counts(self) -> dict[str, int]:
        """Get counts by error type across all phases."""
        counts: dict[str, int] = {}
        for error in self.errors:
            if error.error_type not in counts:
                counts[error.error_type] = 0
            counts[error.error_type] += 1
        return counts

    def to_log_file(self, path: Path) -> None:
        """Write detailed error log to file.

        Args:
            path: Output file path
        """
        lines = []
        lines.append("=" * 80)
        lines.append("WORDPRESS IMPORT ERROR LOG")
        lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
        lines.append("=" * 80)
        lines.append("")

        # Summary
        summary = self.summary()
        lines.append("SUMMARY")
        lines.append("-" * 40)
        lines.append(f"Total Errors: {summary['total_errors']}")
        lines.append(f"Total Skipped: {summary['total_skipped']}")
        lines.append(f"Total Warnings: {summary['total_warnings']}")
        lines.append("")

        if summary["error_types"]:
            lines.append("Errors by Type:")
            for error_type, count in sorted(summary["error_types"].items()):
                lines.append(f"  - {error_type}: {count}")
            lines.append("")

        if summary["by_phase"]:
            lines.append("Errors by Phase:")
            for phase, types in sorted(summary["by_phase"].items()):
                lines.append(f"  {phase}:")
                for error_type, count in sorted(types.items()):
                    lines.append(f"    - {error_type}: {count}")
            lines.append("")

        # Detailed errors
        if self.errors:
            lines.append("=" * 80)
            lines.append("ERRORS (DETAILED)")
            lines.append("=" * 80)
            for i, error in enumerate(self.errors, 1):
                lines.append("")
                lines.append(f"[{i}] {error.phase} / {error.error_type}")
                lines.append(f"    Item: {error.item_title} (ID: {error.item_id})")
                lines.append(f"    Message: {error.message}")
                lines.append(f"    Time: {error.timestamp}")
                if error.context:
                    lines.append(f"    Context: {json.dumps(error.context, ensure_ascii=False)}")
                if error.traceback_str:
                    lines.append("    Traceback:")
                    for tb_line in error.traceback_str.split("\n"):
                        if tb_line.strip():
                            lines.append(f"      {tb_line}")

        # Skipped items
        if self.skipped:
            lines.append("")
            lines.append("=" * 80)
            lines.append("SKIPPED ITEMS")
            lines.append("=" * 80)
            for skip in self.skipped:
                lines.append(f"  [{skip.phase}] {skip.item_title} (ID: {skip.item_id}): {skip.message}")

        # Warnings
        if self.warnings:
            lines.append("")
            lines.append("=" * 80)
            lines.append("WARNINGS")
            lines.append("=" * 80)
            for warning in self.warnings:
                lines.append(f"  [{warning.phase}] {warning.item_title}: {warning.message}")

        lines.append("")
        lines.append("=" * 80)
        lines.append("END OF LOG")
        lines.append("=" * 80)

        path.write_text("\n".join(lines), encoding="utf-8")

    def to_json(self, path: Path) -> None:
        """Write error log as JSON for programmatic access.

        Args:
            path: Output file path
        """
        data = {
            "generated": datetime.now(timezone.utc).isoformat(),
            "summary": self.summary(),
            "errors": [
                {
                    "phase": e.phase,
                    "item_id": e.item_id,
                    "item_title": e.item_title,
                    "error_type": e.error_type,
                    "message": e.message,
                    "timestamp": e.timestamp,
                    "context": e.context,
                    "traceback": e.traceback_str,
                }
                for e in self.errors
            ],
            "skipped": [
                {
                    "phase": s.phase,
                    "item_id": s.item_id,
                    "item_title": s.item_title,
                    "reason": s.message,
                    "context": s.context,
                }
                for s in self.skipped
            ],
            "warnings": [
                {
                    "phase": w.phase,
                    "item_id": w.item_id,
                    "item_title": w.item_title,
                    "type": w.error_type,
                    "message": w.message,
                }
                for w in self.warnings
            ],
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return len(self.errors) > 0

    def to_dict(self) -> dict:
        """Return error log as dictionary for DB storage.

        Returns:
            Dictionary for job.errors. Can be copied and pasted for debugging.
        """
        return {
            "summary": self.summary(),
            "errors": [
                {
                    "phase": e.phase,
                    "item_id": e.item_id,
                    "item_title": e.item_title,
                    "error_type": e.error_type,
                    "message": e.message,
                    "context": e.context,
                }
                for e in self.errors
            ],
            "skipped": [
                {
                    "phase": s.phase,
                    "item_id": s.item_id,
                    "item_title": s.item_title,
                    "reason": s.message,
                }
                for s in self.skipped
            ],
            "warnings": [
                {
                    "phase": w.phase,
                    "item_id": w.item_id,
                    "item_title": w.item_title,
                    "message": w.message,
                }
                for w in self.warnings
            ],
        }

    def print_summary(self) -> str:
        """Get printable summary string.

        Returns:
            Formatted summary for console output
        """
        summary = self.summary()
        lines = []
        lines.append("インポート完了")
        lines.append(f"  エラー: {summary['total_errors']}件")
        lines.append(f"  スキップ: {summary['total_skipped']}件")
        lines.append(f"  警告: {summary['total_warnings']}件")

        if summary["error_types"]:
            lines.append("  エラー内訳:")
            for error_type, count in sorted(summary["error_types"].items()):
                lines.append(f"    - {error_type}: {count}件")

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all collected errors."""
        self.errors.clear()
        self.skipped.clear()
        self.warnings.clear()
        self._counts.clear()
