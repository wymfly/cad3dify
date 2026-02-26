"""Tests for fine-tuning data pipeline."""
import json
import pytest
from pathlib import Path

from scripts.training.deepcad_converter import (
    DeepCADCommand,
    ConversionResult,
    parse_deepcad_record,
    commands_to_cadquery,
    convert_file,
)
from scripts.training.sft_formatter import (
    SFTSample,
    code_to_sft_sample,
    write_jsonl,
    compute_stats,
    DatasetStats,
)
from scripts.training.data_validator import (
    ValidationResult,
    validate_sample,
    validate_batch,
)


class TestDeepCADConverter:
    def test_parse_record_basic(self):
        record = {
            "id": "test_001",
            "operations": [
                {"type": "create_sketch", "plane": "XY"},
                {"type": "extrude", "depth": 10},
            ],
        }
        cmds = parse_deepcad_record(record)
        assert len(cmds) == 2
        assert cmds[0].type == "create_sketch"
        assert cmds[1].params["depth"] == 10

    def test_parse_empty_record(self):
        cmds = parse_deepcad_record({})
        assert cmds == []

    def test_commands_to_cadquery_basic(self):
        cmds = [
            DeepCADCommand(type="create_sketch", params={"plane": "XY"}),
            DeepCADCommand(type="extrude", params={"depth": 10}),
        ]
        code = commands_to_cadquery(cmds)
        assert "import cadquery as cq" in code
        assert "XY" in code
        assert "result = result.extrude(10)" in code

    def test_commands_unknown_op_skipped(self):
        cmds = [DeepCADCommand(type="unknown_op", params={})]
        code = commands_to_cadquery(cmds)
        assert "import cadquery" in code  # still produces valid header

    def test_convert_file(self, tmp_path):
        data = [
            {
                "id": "r1",
                "operations": [
                    {"type": "create_sketch", "plane": "XY"},
                    {"type": "extrude", "depth": 5},
                ],
            }
        ]
        p = tmp_path / "test.json"
        p.write_text(json.dumps(data))
        results = convert_file(p)
        assert len(results) == 1
        assert results[0].success
        assert results[0].source_id == "r1"

    def test_convert_file_invalid_record(self, tmp_path):
        data = [{"id": "bad", "operations": "not_a_list"}]
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(data))
        results = convert_file(p)
        assert len(results) == 1
        assert not results[0].success


class TestSFTFormatter:
    def test_code_to_sft_sample(self):
        s = code_to_sft_sample("法兰盘", "import cq...", source_id="s1")
        assert s.instruction
        assert s.input == "法兰盘"
        assert s.output == "import cq..."

    def test_write_jsonl(self, tmp_path):
        samples = [
            SFTSample(instruction="gen", input="desc", output="code"),
            SFTSample(instruction="gen", input="desc2", output="code2"),
        ]
        p = tmp_path / "train.jsonl"
        count = write_jsonl(samples, p)
        assert count == 2
        lines = p.read_text().strip().split("\n")
        assert len(lines) == 2
        parsed = json.loads(lines[0])
        assert parsed["instruction"] == "gen"

    def test_compute_stats_all_valid(self):
        samples = [
            SFTSample(instruction="i", input="in", output="code1"),
            SFTSample(instruction="i", input="in", output="code2"),
        ]
        stats = compute_stats(samples)
        assert stats.total == 2
        assert stats.valid == 2
        assert stats.valid_ratio == 1.0

    def test_compute_stats_with_invalid(self):
        samples = [
            SFTSample(instruction="i", input="in", output="code"),
            SFTSample(instruction="i", input="in", output=""),
        ]
        stats = compute_stats(samples)
        assert stats.valid == 1
        assert stats.invalid == 1
        assert stats.valid_ratio == 0.5

    def test_compute_stats_empty(self):
        stats = compute_stats([])
        assert stats.total == 0
        assert stats.valid_ratio == 0.0


class TestDataValidator:
    def test_valid_code_compiles(self):
        r = validate_sample("s1", "x = 1 + 2")
        assert r.compiles
        # No exec_fn → executes is False (only compilation verified)
        assert not r.executes

    def test_syntax_error(self):
        r = validate_sample("s1", "def f(:\n  pass")
        assert not r.compiles
        assert not r.executes
        assert r.error is not None

    def test_with_exec_fn_success(self):
        r = validate_sample("s1", "x = 1", exec_fn=lambda c: (True, None))
        assert r.compiles and r.executes

    def test_with_exec_fn_failure(self):
        r = validate_sample(
            "s1", "x = 1",
            exec_fn=lambda c: (False, "runtime error"),
        )
        assert r.compiles
        assert not r.executes
        assert r.error == "runtime error"

    def test_validate_batch(self):
        samples = [("s1", "x = 1"), ("s2", "def f(:\n")]
        results = validate_batch(samples)
        assert len(results) == 2
        assert results[0].compiles
        assert not results[1].compiles

    def test_validate_batch_empty(self):
        results = validate_batch([])
        assert results == []
