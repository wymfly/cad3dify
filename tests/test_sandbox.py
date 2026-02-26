"""Tests for SafeExecutor — AST pre-check + subprocess isolation."""

from __future__ import annotations

import pytest

from backend.infra.sandbox import ExecutionResult, SafeExecutor, SecurityViolation


class TestASTChecks:
    """Test that dangerous code patterns are blocked by AST analysis."""

    def test_blocks_os_system(self):
        executor = SafeExecutor()
        with pytest.raises(SecurityViolation, match="os"):
            executor.check_code("import os; os.system('ls')")

    def test_blocks_os_popen(self):
        executor = SafeExecutor()
        with pytest.raises(SecurityViolation, match="os"):
            executor.check_code("import os; os.popen('ls')")

    def test_blocks_subprocess(self):
        executor = SafeExecutor()
        with pytest.raises(SecurityViolation, match="subprocess"):
            executor.check_code("import subprocess; subprocess.run(['ls'])")

    def test_blocks_eval(self):
        executor = SafeExecutor()
        with pytest.raises(SecurityViolation, match="eval"):
            executor.check_code("eval('1+1')")

    def test_blocks_exec(self):
        executor = SafeExecutor()
        with pytest.raises(SecurityViolation, match="exec"):
            executor.check_code("exec('x=1')")

    def test_blocks_dunder_import(self):
        executor = SafeExecutor()
        with pytest.raises(SecurityViolation, match="__import__"):
            executor.check_code("__import__('os')")

    def test_blocks_compile(self):
        executor = SafeExecutor()
        with pytest.raises(SecurityViolation, match="compile"):
            executor.check_code("compile('x=1', '<string>', 'exec')")

    def test_allows_cadquery_code(self):
        executor = SafeExecutor()
        code = """
import cadquery as cq
result = cq.Workplane("XY").box(10, 10, 10)
"""
        # Should not raise
        executor.check_code(code)

    def test_allows_math_and_numpy(self):
        executor = SafeExecutor()
        code = """
import math
import numpy as np
x = math.pi * np.array([1, 2, 3])
"""
        executor.check_code(code)

    def test_blocks_nested_import(self):
        executor = SafeExecutor()
        with pytest.raises(SecurityViolation, match="subprocess"):
            executor.check_code("from subprocess import call; call(['ls'])")


class TestExecution:
    """Test subprocess-based code execution."""

    def test_simple_execution(self):
        executor = SafeExecutor()
        result = executor.execute("print('hello')")
        assert isinstance(result, ExecutionResult)
        assert result.success is True
        assert "hello" in result.stdout

    def test_timeout_enforcement(self):
        executor = SafeExecutor(timeout_s=2)
        result = executor.execute("import time; time.sleep(10)")
        assert result.timed_out is True
        assert result.success is False

    def test_syntax_error_reports_failure(self):
        executor = SafeExecutor()
        with pytest.raises(SecurityViolation, match="Syntax error"):
            executor.execute("def (broken")

    def test_runtime_error_reports_failure(self):
        executor = SafeExecutor()
        result = executor.execute("raise ValueError('test error')")
        assert result.success is False
        assert "ValueError" in result.stderr

    def test_ast_check_before_execute(self):
        executor = SafeExecutor()
        with pytest.raises(SecurityViolation):
            executor.execute("import os; os.system('rm -rf /')")

    def test_execution_result_has_duration(self):
        executor = SafeExecutor()
        result = executor.execute("x = 1 + 1")
        assert result.success is True
        assert result.duration_s >= 0
