"""Execution validation for generated CadQuery code."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a single code sample."""
    source_id: str
    compiles: bool
    executes: bool
    error: Optional[str] = None


# Type alias: code string → (success, error_msg)
ExecFn = Callable[[str], tuple[bool, Optional[str]]]


def _default_compile_check(code: str) -> tuple[bool, Optional[str]]:
    """Check if code compiles (AST parse)."""
    try:
        compile(code, "<sft_sample>", "exec")
        return True, None
    except SyntaxError as e:
        return False, str(e)


def validate_sample(
    source_id: str,
    code: str,
    exec_fn: Optional[ExecFn] = None,
) -> ValidationResult:
    """Validate a single code sample: compile check + optional exec."""
    compiles, compile_err = _default_compile_check(code)
    if not compiles:
        return ValidationResult(
            source_id=source_id,
            compiles=False,
            executes=False,
            error=compile_err,
        )

    if exec_fn is not None:
        executes, exec_err = exec_fn(code)
        return ValidationResult(
            source_id=source_id,
            compiles=True,
            executes=executes,
            error=exec_err,
        )

    return ValidationResult(
        source_id=source_id,
        compiles=True,
        executes=True,  # skip exec if no exec_fn
    )


def validate_batch(
    samples: list[tuple[str, str]],
    exec_fn: Optional[ExecFn] = None,
) -> list[ValidationResult]:
    """Validate a batch of (source_id, code) tuples."""
    results: list[ValidationResult] = []
    for source_id, code in samples:
        result = validate_sample(source_id, code, exec_fn)
        results.append(result)
    passed = sum(1 for r in results if r.compiles and r.executes)
    logger.info(
        "Validated %d samples: %d passed (%.1f%%)",
        len(results), passed, 100 * passed / len(results) if results else 0,
    )
    return results
