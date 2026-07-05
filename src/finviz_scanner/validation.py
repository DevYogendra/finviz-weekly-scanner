"""Run validation policies."""

from __future__ import annotations

from finviz_scanner.errors import ValidationError
from finviz_scanner.models import ExtractionResult


def validate_extraction(result: ExtractionResult, *, require_exact_count: bool = True) -> None:
    if result.displayed_count <= 0:
        raise ValidationError("Finviz displayed an empty or missing result count.")
    if not result.rows:
        raise ValidationError("No ticker rows were extracted.")
    if require_exact_count and result.unique_count != result.displayed_count:
        raise ValidationError(
            f"Displayed count {result.displayed_count} does not match "
            f"unique extracted count {result.unique_count}."
        )
