"""SFT data format conversion: (instruction, input, output) triples."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SFTSample:
    """Single SFT training sample."""
    instruction: str
    input: str
    output: str
    source_id: str = ""


_DEFAULT_INSTRUCTION = (
    "Generate CadQuery Python code to create a 3D CAD model "
    "matching the following description."
)


def code_to_sft_sample(
    description: str,
    cadquery_code: str,
    source_id: str = "",
    instruction: str = _DEFAULT_INSTRUCTION,
) -> SFTSample:
    """Convert a (description, code) pair to SFT format."""
    return SFTSample(
        instruction=instruction,
        input=description,
        output=cadquery_code,
        source_id=source_id,
    )


def write_jsonl(samples: list[SFTSample], output_path: Path) -> int:
    """Write SFT samples to JSONL file. Returns count written."""
    count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for s in samples:
            record = {
                "instruction": s.instruction,
                "input": s.input,
                "output": s.output,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    logger.info("Wrote %d samples to %s", count, output_path)
    return count


@dataclass
class DatasetStats:
    """Quality statistics for a converted dataset."""
    total: int
    valid: int
    invalid: int
    valid_ratio: float
    avg_code_length: float


def compute_stats(samples: list[SFTSample]) -> DatasetStats:
    """Compute quality statistics for a dataset."""
    total = len(samples)
    valid = sum(1 for s in samples if s.output.strip())
    code_lengths = [len(s.output) for s in samples if s.output.strip()]
    return DatasetStats(
        total=total,
        valid=valid,
        invalid=total - valid,
        valid_ratio=valid / total if total > 0 else 0.0,
        avg_code_length=sum(code_lengths) / len(code_lengths) if code_lengths else 0.0,
    )
