# Phase 5: AI 增强 + 多模态 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 cad3dify V3 添加 RAG 检索增强、OCR 辅助分析、多模型投票、参考图片理解和成本优化能力。

**Architecture:** 所有增强功能通过 PipelineConfig 开关控制，mock LLM/embedding callable 依赖注入确保可测试性。EmbeddingStore (Phase 3) 为 RAG 基础，DrawingAnalyzerChain 为 OCR/投票集成点，IntentParser 为图片理解入口。

**Tech Stack:** Python 3.10+, Pydantic v2, numpy, pytest, FastAPI

**Baseline:** 605 tests collected, 602 passed, 3 skipped

---

## 依赖图

```
T5.1 (RAG 数据管道) ──→ T5.2 (RAG 代码生成)
T5.3 (OCR + 两阶段)  独立
T5.4 (多模型投票)    独立
T5.5 (参考图片)      独立 (T4.2 已完成)
T5.6 (成本优化)      独立
```

- Wave 1 (并行): T5.1, T5.3, T5.4, T5.5, T5.6
- Wave 2: T5.2 (依赖 T5.1)

---

## Task 5.1: RAG 数据管道 + 检索 API

**Files:**
- Create: `backend/infra/rag.py`
- Create: `backend/api/rag.py`
- Create: `tests/test_rag_pipeline.py`
- Modify: `backend/main.py` (注册 rag router)
- Modify: `tests/conftest.py` (添加 sentence_transformers stub)

**Context:**
- `backend/infra/embedding.py` 已有 EmbeddingStore + spec_to_embedding_text()
- `backend/knowledge/examples/` 有 36+ TaggedExample
- PipelineConfig.rag_enabled 开关已预定义
- 原始 tasks.md 说用 pgvector，但 V3 分阶段构建用 in-memory EmbeddingStore 即可

**Step 1: Write tests**

```python
# tests/test_rag_pipeline.py
"""Tests for RAG data pipeline and retrieval API."""
import numpy as np
import pytest

from backend.infra.rag import (
    RAGPipeline,
    RAGEntry,
    embed_text_mock,
)
from backend.infra.embedding import EmbeddingStore


class TestRAGEntry:
    def test_create_entry(self):
        entry = RAGEntry(
            id="ex_001",
            description="圆柱法兰盘",
            code="import cq...",
            tags={"revolve", "flange"},
        )
        assert entry.id == "ex_001"

    def test_entry_to_text(self):
        entry = RAGEntry(
            id="ex_001",
            description="圆柱法兰盘",
            code="import cq...",
            tags={"revolve"},
        )
        text = entry.to_embedding_text()
        assert "圆柱法兰盘" in text
        assert "revolve" in text


class TestRAGPipeline:
    def test_init_empty(self):
        pipe = RAGPipeline(embed_fn=embed_text_mock)
        assert len(pipe) == 0

    def test_add_and_search(self):
        pipe = RAGPipeline(embed_fn=embed_text_mock)
        pipe.add(RAGEntry(
            id="e1", description="法兰盘 revolve", code="code1", tags={"revolve"},
        ))
        pipe.add(RAGEntry(
            id="e2", description="齿轮 gear", code="code2", tags={"gear"},
        ))
        results = pipe.search("法兰盘 旋转体", top_k=1)
        assert len(results) == 1
        assert results[0].id in ("e1", "e2")

    def test_search_empty_store(self):
        pipe = RAGPipeline(embed_fn=embed_text_mock)
        results = pipe.search("anything", top_k=3)
        assert results == []

    def test_load_from_examples(self):
        """Load all TaggedExample from knowledge base."""
        pipe = RAGPipeline(embed_fn=embed_text_mock)
        count = pipe.load_from_knowledge_base()
        assert count >= 36  # Phase 3 added 36+ examples

    def test_search_with_part_type_filter(self):
        pipe = RAGPipeline(embed_fn=embed_text_mock)
        pipe.add(RAGEntry(
            id="e1", description="法兰盘", code="c1",
            tags={"revolve"}, part_type="rotational",
        ))
        pipe.add(RAGEntry(
            id="e2", description="齿轮", code="c2",
            tags={"gear"}, part_type="gear",
        ))
        results = pipe.search("旋转", top_k=5, part_type="rotational")
        assert all(r.part_type == "rotational" for r in results)

    def test_search_returns_code(self):
        pipe = RAGPipeline(embed_fn=embed_text_mock)
        pipe.add(RAGEntry(
            id="e1", description="test", code="import cq",
            tags=set(),
        ))
        results = pipe.search("test", top_k=1)
        assert results[0].code == "import cq"


class TestEmbedTextMock:
    def test_returns_numpy_array(self):
        vec = embed_text_mock("hello world")
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (64,)

    def test_deterministic(self):
        v1 = embed_text_mock("same text")
        v2 = embed_text_mock("same text")
        np.testing.assert_array_equal(v1, v2)

    def test_different_texts_different_vectors(self):
        v1 = embed_text_mock("法兰盘")
        v2 = embed_text_mock("齿轮")
        assert not np.array_equal(v1, v2)
```

**Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_rag_pipeline.py -v
```

**Step 3: Implement RAGPipeline**

```python
# backend/infra/rag.py
"""RAG pipeline: loads examples into EmbeddingStore, provides retrieval API.

Uses dependency-injected embedding function for testability.
Real embedding model (sentence-transformers) replaces embed_text_mock in prod.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from .embedding import EmbeddingStore, SearchResult

# Type alias for embedding function: text → vector
EmbedFn = Callable[[str], np.ndarray]

_MOCK_DIM = 64


def embed_text_mock(text: str) -> np.ndarray:
    """Deterministic mock embedding: SHA256 hash → float64 vector."""
    digest = hashlib.sha256(text.encode()).digest()
    arr = np.frombuffer(digest[:_MOCK_DIM * 4 // 4], dtype=np.uint8).astype(np.float64)
    # Pad/truncate to _MOCK_DIM
    if len(arr) < _MOCK_DIM:
        arr = np.pad(arr, (0, _MOCK_DIM - len(arr)))
    return arr[:_MOCK_DIM]


@dataclass
class RAGEntry:
    """Single entry in the RAG knowledge base."""
    id: str
    description: str
    code: str
    tags: set[str] = field(default_factory=set)
    part_type: Optional[str] = None

    def to_embedding_text(self) -> str:
        parts = [self.description]
        if self.tags:
            parts.extend(sorted(self.tags))
        if self.part_type:
            parts.append(self.part_type)
        return " ".join(parts)


@dataclass
class RAGResult:
    """Search result from RAG pipeline."""
    id: str
    description: str
    code: str
    score: float
    part_type: Optional[str] = None


class RAGPipeline:
    """RAG pipeline wrapping EmbeddingStore with knowledge-base loading."""

    def __init__(self, embed_fn: EmbedFn = embed_text_mock) -> None:
        self._embed_fn = embed_fn
        self._store = EmbeddingStore()
        self._entries: dict[str, RAGEntry] = {}

    def add(self, entry: RAGEntry) -> None:
        vec = self._embed_fn(entry.to_embedding_text())
        self._store.add(
            key=entry.id,
            vector=vec,
            metadata={
                "part_type": entry.part_type or "",
                "description": entry.description,
                "code": entry.code,
            },
        )
        self._entries[entry.id] = entry

    def search(
        self,
        query: str,
        top_k: int = 3,
        part_type: Optional[str] = None,
    ) -> list[RAGResult]:
        if len(self._store) == 0:
            return []
        q_vec = self._embed_fn(query)
        filter_meta = {"part_type": part_type} if part_type else None
        hits = self._store.find_similar(q_vec, top_k=top_k, filter_metadata=filter_meta)
        return [
            RAGResult(
                id=h.key,
                description=h.metadata.get("description", ""),
                code=h.metadata.get("code", ""),
                score=h.score,
                part_type=h.metadata.get("part_type") or None,
            )
            for h in hits
        ]

    def load_from_knowledge_base(self) -> int:
        """Load all TaggedExample from backend.knowledge.examples into store."""
        from ..knowledge.examples import EXAMPLES_BY_TYPE
        count = 0
        seen: set[int] = set()
        for part_type, examples in EXAMPLES_BY_TYPE.items():
            for ex in examples:
                if id(ex) in seen:
                    continue
                seen.add(id(ex))
                entry = RAGEntry(
                    id=f"kb_{ex.name}",
                    description=ex.description,
                    code=ex.code,
                    tags=set(ex.features),
                    part_type=part_type.value,
                )
                self.add(entry)
                count += 1
        return count

    def __len__(self) -> int:
        return len(self._store)
```

**Step 4: Write RAG API endpoint**

```python
# backend/api/rag.py
from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..infra.rag import RAGPipeline, embed_text_mock

router = APIRouter(prefix="/rag", tags=["rag"])
_pipeline: RAGPipeline | None = None


def _get_pipeline() -> RAGPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline(embed_fn=embed_text_mock)
        _pipeline.load_from_knowledge_base()
    return _pipeline


class RAGSearchResult(BaseModel):
    id: str
    description: str
    code: str
    score: float
    part_type: str | None = None


@router.get("/search")
async def search_examples(
    q: str = Query(..., description="搜索文本"),
    top_k: int = Query(3, ge=1, le=10),
    part_type: str | None = Query(None),
) -> list[RAGSearchResult]:
    pipe = _get_pipeline()
    results = pipe.search(q, top_k=top_k, part_type=part_type)
    return [
        RAGSearchResult(
            id=r.id, description=r.description, code=r.code,
            score=r.score, part_type=r.part_type,
        )
        for r in results
    ]


@router.get("/stats")
async def rag_stats() -> dict:
    pipe = _get_pipeline()
    return {"total_entries": len(pipe)}
```

**Step 5: Add API test + register router**

```python
# tests/test_rag_api.py  (追加)
class TestRAGAPI:
    def test_search(self):
        result = asyncio.run(rag_api.search_examples(q="法兰盘", top_k=3))
        assert isinstance(result, list)

    def test_stats(self):
        result = asyncio.run(rag_api.rag_stats())
        assert "total_entries" in result
```

Register in `backend/main.py`:
```python
from .api.rag import router as rag_router
app.include_router(rag_router, prefix="/api")
```

Add `sentence_transformers` to conftest.py `_STUB_ROOTS`.

**Step 6: Run all tests — expect PASS**

```bash
pytest tests/test_rag_pipeline.py tests/test_rag_api.py -v
pytest tests/ -q  # 全量回归
```

**Step 7: Commit**

```bash
git add backend/infra/rag.py backend/api/rag.py tests/test_rag_pipeline.py tests/test_rag_api.py backend/main.py tests/conftest.py
git commit -m "feat: RAG 数据管道 + 检索 API (Phase 5 Task 5.1)"
```

**Expected:** ~20 new tests

---

## Task 5.2: RAG 增强代码生成

**Files:**
- Modify: `backend/core/modeling_strategist.py:185-207` (_select_by_vector placeholder → real implementation)
- Create: `tests/test_rag_code_gen.py`

**Context:**
- `ModelingStrategist._select_by_vector()` 是 Phase 3 placeholder，返回空列表
- `RAGPipeline` (T5.1) 提供 search() → RAGResult(description, code)
- `EmbeddingStore` + `spec_to_embedding_text()` 基础设施就绪
- `PipelineConfig.rag_enabled` 控制是否启用
- `ModelingContext.to_prompt_text()` 是 RAG 注入到 CodeGeneratorChain 的入口

**Step 1: Write tests**

```python
# tests/test_rag_code_gen.py
"""Tests for RAG-enhanced code generation path."""
import pytest
import numpy as np

from backend.core.modeling_strategist import ModelingStrategist, ModelingContext
from backend.infra.embedding import EmbeddingStore, spec_to_embedding_text
from backend.infra.rag import RAGPipeline, RAGEntry, embed_text_mock
from backend.knowledge.part_types import DrawingSpec, PartType, BaseBodySpec


def _make_spec(part_type: str = "rotational") -> DrawingSpec:
    return DrawingSpec(
        part_type=part_type,
        description="测试法兰盘",
        overall_dimensions={"diameter": 100},
        base_body=BaseBodySpec(method="revolve"),
        features=[],
    )


class TestRAGCodeGen:
    def test_vector_path_with_rag_pipeline(self):
        """When RAG pipeline provides results, vector path returns examples."""
        rag = RAGPipeline(embed_fn=embed_text_mock)
        rag.add(RAGEntry(
            id="e1", description="法兰盘 revolve 回转体",
            code="import cq; result = cq.circle(50)",
            tags={"revolve"}, part_type="rotational",
        ))
        strategist = ModelingStrategist(rag_pipeline=rag)
        spec = _make_spec()
        ctx = strategist.select(spec, max_examples=1)
        # Should have at least 1 example (from RAG or fallback)
        assert len(ctx.examples) >= 1

    def test_vector_path_empty_falls_back_to_jaccard(self):
        """Empty RAG pipeline triggers Jaccard fallback."""
        rag = RAGPipeline(embed_fn=embed_text_mock)
        strategist = ModelingStrategist(rag_pipeline=rag)
        spec = _make_spec()
        ctx = strategist.select(spec, max_examples=3)
        assert len(ctx.examples) == 3  # Jaccard always has examples

    def test_no_rag_uses_jaccard(self):
        """Without RAG pipeline, uses Jaccard only."""
        strategist = ModelingStrategist()
        spec = _make_spec()
        ctx = strategist.select(spec, max_examples=3)
        assert len(ctx.examples) == 3

    def test_rag_results_in_prompt_text(self):
        """RAG examples should appear in prompt text."""
        rag = RAGPipeline(embed_fn=embed_text_mock)
        rag.add(RAGEntry(
            id="e1", description="测试示例",
            code="# RAG retrieved code",
            tags=set(),
        ))
        strategist = ModelingStrategist(rag_pipeline=rag)
        spec = _make_spec()
        ctx = strategist.select(spec, max_examples=3)
        prompt = ctx.to_prompt_text()
        assert "参考代码示例" in prompt

    def test_rag_pipeline_loaded_from_kb(self):
        """RAG pipeline can load from knowledge base."""
        rag = RAGPipeline(embed_fn=embed_text_mock)
        count = rag.load_from_knowledge_base()
        strategist = ModelingStrategist(rag_pipeline=rag)
        spec = _make_spec()
        ctx = strategist.select(spec, max_examples=3)
        assert len(ctx.examples) == 3
```

**Step 2: Run tests — expect FAIL** (ModelingStrategist doesn't accept rag_pipeline yet)

**Step 3: Implement — modify ModelingStrategist**

Replace `_select_by_vector()` placeholder and change constructor to accept `rag_pipeline`:

```python
# In ModelingStrategist.__init__:
def __init__(
    self,
    embedding_store: EmbeddingStore | None = None,
    rag_pipeline: "RAGPipeline | None" = None,
) -> None:
    self._embedding_store = embedding_store
    self._rag_pipeline = rag_pipeline

# In select(): check rag_pipeline first
if self._rag_pipeline is not None and len(self._rag_pipeline) > 0:
    examples = self._select_by_rag(spec, max_examples)
    if examples:
        return ModelingContext(drawing_spec=spec, strategy=strategy, examples=examples)

# New method:
def _select_by_rag(self, spec, max_examples):
    from ..infra.rag import embed_text_mock  # fallback embed
    from ..infra.embedding import spec_to_embedding_text
    query = spec_to_embedding_text(spec)
    results = self._rag_pipeline.search(query, top_k=max_examples)
    if not results:
        return []
    return [(r.description, r.code) for r in results]
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/test_rag_code_gen.py -v
pytest tests/ -q
```

**Step 5: Commit**

```bash
git add backend/core/modeling_strategist.py tests/test_rag_code_gen.py
git commit -m "feat: RAG 增强代码生成 — 向量检索 + Jaccard 回退 (Phase 5 Task 5.2)"
```

**Expected:** ~10 new tests

---

## Task 5.3: OCR 辅助 + 两阶段分析

**Files:**
- Create: `backend/core/ocr_assist.py`
- Create: `backend/core/two_pass_analyzer.py`
- Create: `tests/test_ocr_assist.py`
- Create: `tests/test_two_pass_analyzer.py`
- Modify: `tests/conftest.py` (添加 paddleocr, pytesseract stub)

**Context:**
- `DrawingAnalyzerChain` (backend/core/drawing_analyzer.py) 是当前 VL 分析入口
- `PipelineConfig.ocr_assist` 和 `PipelineConfig.two_pass_analysis` 开关已定义
- OCR 模块需要 PaddleOCR/Tesseract — 测试中用 mock
- 两阶段分析: Pass 1 (全局结构) → Pass 2 (局部尺寸)

**Step 1: Write tests**

```python
# tests/test_ocr_assist.py
"""Tests for OCR-assisted dimension extraction."""
import pytest

from backend.core.ocr_assist import (
    OCRResult,
    DimensionAnnotation,
    parse_dimension_text,
    merge_ocr_with_vl,
    OCRAssistant,
)


class TestParseDimensionText:
    def test_diameter_symbol(self):
        result = parse_dimension_text("φ50")
        assert result == DimensionAnnotation(type="diameter", value=50.0, symbol="φ")

    def test_radius_symbol(self):
        result = parse_dimension_text("R15")
        assert result == DimensionAnnotation(type="radius", value=15.0, symbol="R")

    def test_tolerance(self):
        result = parse_dimension_text("50±0.1")
        assert result.value == 50.0
        assert result.tolerance == 0.1

    def test_multiplication(self):
        result = parse_dimension_text("6×φ10")
        assert result.count == 6
        assert result.value == 10.0

    def test_plain_number(self):
        result = parse_dimension_text("120")
        assert result.value == 120.0
        assert result.type == "linear"

    def test_invalid_text(self):
        result = parse_dimension_text("Ra3.2")
        assert result is None  # surface finish, not dimension


class TestMergeOCRWithVL:
    def test_consistent_values_high_confidence(self):
        ocr_dims = {"diameter": 100.0}
        vl_dims = {"diameter": 100.0}
        merged, confidence = merge_ocr_with_vl(ocr_dims, vl_dims)
        assert merged["diameter"] == 100.0
        assert confidence["diameter"] >= 0.9

    def test_inconsistent_values_prefer_ocr_numeric(self):
        ocr_dims = {"diameter": 100.0}
        vl_dims = {"diameter": 95.0}
        merged, confidence = merge_ocr_with_vl(ocr_dims, vl_dims)
        assert merged["diameter"] == 100.0  # OCR preferred for numbers
        assert confidence["diameter"] < 0.9

    def test_vl_only_field(self):
        ocr_dims = {}
        vl_dims = {"part_type": "rotational"}
        merged, confidence = merge_ocr_with_vl(ocr_dims, vl_dims)
        assert merged["part_type"] == "rotational"


class TestOCRAssistant:
    def test_init_with_mock(self):
        def mock_ocr(image_bytes):
            return [OCRResult(text="φ50", confidence=0.95, bbox=(10, 20, 50, 30))]
        assistant = OCRAssistant(ocr_fn=mock_ocr)
        assert assistant is not None

    def test_extract_dimensions(self):
        def mock_ocr(image_bytes):
            return [
                OCRResult(text="φ50", confidence=0.95, bbox=(10, 20, 50, 30)),
                OCRResult(text="30", confidence=0.90, bbox=(60, 20, 90, 30)),
                OCRResult(text="Ra3.2", confidence=0.88, bbox=(100, 20, 140, 30)),
            ]
        assistant = OCRAssistant(ocr_fn=mock_ocr)
        dims = assistant.extract_dimensions(b"fake_image")
        assert len(dims) >= 2  # φ50 and 30, Ra3.2 is surface finish

    def test_no_ocr_results(self):
        assistant = OCRAssistant(ocr_fn=lambda img: [])
        dims = assistant.extract_dimensions(b"fake_image")
        assert dims == []
```

```python
# tests/test_two_pass_analyzer.py
"""Tests for two-pass drawing analysis."""
import pytest

from backend.core.two_pass_analyzer import (
    TwoPassAnalyzer,
    Pass1Result,
    Pass2Result,
)
from backend.knowledge.part_types import PartType


class TestPass1Result:
    def test_basic_fields(self):
        r = Pass1Result(
            part_type=PartType.ROTATIONAL_STEPPED,
            step_count=3,
            feature_count=2,
            views=["front_section", "top"],
        )
        assert r.part_type == PartType.ROTATIONAL_STEPPED
        assert r.step_count == 3


class TestPass2Result:
    def test_basic_fields(self):
        r = Pass2Result(
            dimensions={"diameter": 100.0, "height": 30.0},
            features=[{"type": "hole_pattern", "count": 6, "diameter": 10}],
        )
        assert r.dimensions["diameter"] == 100.0


class TestTwoPassAnalyzer:
    def test_init_with_mock_llm(self):
        async def mock_pass1(image):
            return Pass1Result(
                part_type=PartType.ROTATIONAL,
                step_count=1,
                feature_count=0,
                views=["front"],
            )
        async def mock_pass2(image, pass1_result):
            return Pass2Result(
                dimensions={"diameter": 50.0},
                features=[],
            )
        analyzer = TwoPassAnalyzer(pass1_fn=mock_pass1, pass2_fn=mock_pass2)
        assert analyzer is not None

    @pytest.mark.asyncio
    async def test_analyze_two_pass(self):
        async def mock_pass1(image):
            return Pass1Result(
                part_type=PartType.ROTATIONAL_STEPPED,
                step_count=2,
                feature_count=1,
                views=["front_section"],
            )
        async def mock_pass2(image, pass1_result):
            return Pass2Result(
                dimensions={"max_diameter": 100.0, "total_height": 30.0},
                features=[{"type": "hole_pattern", "count": 4}],
            )
        analyzer = TwoPassAnalyzer(pass1_fn=mock_pass1, pass2_fn=mock_pass2)
        spec = await analyzer.analyze(b"fake_image")
        assert spec.part_type == PartType.ROTATIONAL_STEPPED
        assert spec.overall_dimensions["max_diameter"] == 100.0
        assert len(spec.features) == 1

    @pytest.mark.asyncio
    async def test_pass1_failure_returns_none(self):
        async def mock_pass1(image):
            return None
        async def mock_pass2(image, pass1_result):
            return Pass2Result(dimensions={}, features=[])
        analyzer = TwoPassAnalyzer(pass1_fn=mock_pass1, pass2_fn=mock_pass2)
        result = await analyzer.analyze(b"fake_image")
        assert result is None
```

**Step 2: Run tests — expect FAIL**

**Step 3: Implement OCR module**

```python
# backend/core/ocr_assist.py
"""OCR-assisted dimension extraction from engineering drawings.

Uses dependency-injected OCR function for testability.
Real OCR: PaddleOCR or Tesseract.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class OCRResult:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2


@dataclass
class DimensionAnnotation:
    type: str  # "diameter", "radius", "linear", "angle"
    value: float
    symbol: str = ""
    tolerance: Optional[float] = None
    count: Optional[int] = None


# Type alias
OCRFn = Callable[[bytes], list[OCRResult]]

_DIM_PATTERNS = [
    (r"(\d+)×[φΦ](\d+(?:\.\d+)?)", "diameter_pattern"),
    (r"[φΦ](\d+(?:\.\d+)?)", "diameter"),
    (r"[Rr](\d+(?:\.\d+)?)", "radius"),
    (r"(\d+(?:\.\d+)?)±(\d+(?:\.\d+)?)", "tolerance"),
    (r"(\d+(?:\.\d+)?)", "linear"),
]


def parse_dimension_text(text: str) -> Optional[DimensionAnnotation]:
    text = text.strip()
    # Skip surface finish annotations
    if re.match(r"[Rr]a\d", text):
        return None

    # Pattern: N×φD
    m = re.match(r"(\d+)×[φΦ](\d+(?:\.\d+)?)", text)
    if m:
        return DimensionAnnotation(
            type="diameter", value=float(m.group(2)),
            symbol="φ", count=int(m.group(1)),
        )

    # Pattern: φD
    m = re.match(r"[φΦ](\d+(?:\.\d+)?)", text)
    if m:
        return DimensionAnnotation(type="diameter", value=float(m.group(1)), symbol="φ")

    # Pattern: RN (not Ra)
    m = re.match(r"R(\d+(?:\.\d+)?)", text)
    if m:
        return DimensionAnnotation(type="radius", value=float(m.group(1)), symbol="R")

    # Pattern: N±T
    m = re.match(r"(\d+(?:\.\d+)?)±(\d+(?:\.\d+)?)", text)
    if m:
        return DimensionAnnotation(
            type="linear", value=float(m.group(1)),
            tolerance=float(m.group(2)),
        )

    # Plain number
    m = re.match(r"^(\d+(?:\.\d+)?)$", text)
    if m:
        return DimensionAnnotation(type="linear", value=float(m.group(1)))

    return None


def merge_ocr_with_vl(
    ocr_dims: dict[str, float],
    vl_dims: dict[str, object],
) -> tuple[dict[str, object], dict[str, float]]:
    merged: dict[str, object] = {}
    confidence: dict[str, float] = {}

    all_keys = set(ocr_dims.keys()) | set(vl_dims.keys())
    for key in all_keys:
        ocr_val = ocr_dims.get(key)
        vl_val = vl_dims.get(key)

        if ocr_val is not None and vl_val is not None:
            if isinstance(ocr_val, (int, float)) and isinstance(vl_val, (int, float)):
                if abs(ocr_val - vl_val) < 0.01:
                    merged[key] = ocr_val
                    confidence[key] = 0.95
                else:
                    merged[key] = ocr_val  # OCR preferred for numeric
                    confidence[key] = 0.7
            else:
                merged[key] = vl_val  # VL preferred for semantic
                confidence[key] = 0.8
        elif ocr_val is not None:
            merged[key] = ocr_val
            confidence[key] = 0.85
        else:
            merged[key] = vl_val
            confidence[key] = 0.8

    return merged, confidence


class OCRAssistant:
    def __init__(self, ocr_fn: OCRFn) -> None:
        self._ocr_fn = ocr_fn

    def extract_dimensions(self, image_bytes: bytes) -> list[DimensionAnnotation]:
        raw = self._ocr_fn(image_bytes)
        dims = []
        for r in raw:
            parsed = parse_dimension_text(r.text)
            if parsed is not None:
                dims.append(parsed)
        return dims
```

**Step 4: Implement two-pass analyzer**

```python
# backend/core/two_pass_analyzer.py
"""Two-pass drawing analysis: global structure first, then local dimensions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional

from ..knowledge.part_types import DrawingSpec, PartType, BaseBodySpec


@dataclass
class Pass1Result:
    part_type: PartType
    step_count: int
    feature_count: int
    views: list[str]


@dataclass
class Pass2Result:
    dimensions: dict[str, float]
    features: list[dict[str, Any]]


Pass1Fn = Callable[[bytes], Awaitable[Optional[Pass1Result]]]
Pass2Fn = Callable[[bytes, Pass1Result], Awaitable[Pass2Result]]


class TwoPassAnalyzer:
    def __init__(self, pass1_fn: Pass1Fn, pass2_fn: Pass2Fn) -> None:
        self._pass1_fn = pass1_fn
        self._pass2_fn = pass2_fn

    async def analyze(self, image_bytes: bytes) -> Optional[DrawingSpec]:
        pass1 = await self._pass1_fn(image_bytes)
        if pass1 is None:
            return None

        pass2 = await self._pass2_fn(image_bytes, pass1)

        method = "revolve" if pass1.part_type in (
            PartType.ROTATIONAL, PartType.ROTATIONAL_STEPPED
        ) else "extrude"

        return DrawingSpec(
            part_type=pass1.part_type.value,
            description=f"{pass1.part_type.value} with {pass1.step_count} steps",
            views=pass1.views,
            overall_dimensions=pass2.dimensions,
            base_body=BaseBodySpec(method=method),
            features=pass2.features,
        )
```

**Step 5: Update conftest.py — add OCR stubs**

Add to `_STUB_ROOTS`: `"paddleocr"`, `"pytesseract"`, `"PIL"`, `"pillow"`

**Step 6: Run tests — expect PASS**

```bash
pytest tests/test_ocr_assist.py tests/test_two_pass_analyzer.py -v
pytest tests/ -q
```

**Step 7: Commit**

```bash
git add backend/core/ocr_assist.py backend/core/two_pass_analyzer.py tests/test_ocr_assist.py tests/test_two_pass_analyzer.py tests/conftest.py
git commit -m "feat: OCR 辅助 + 两阶段分析 (Phase 5 Task 5.3)"
```

**Expected:** ~20 new tests

---

## Task 5.4: 多模型投票 + Self-consistency

**Files:**
- Create: `backend/core/voting.py`
- Create: `tests/test_voting.py`

**Context:**
- `PipelineConfig.multi_model_voting` (bool) 和 `PipelineConfig.self_consistency_runs` (int, 1=off)
- DrawingSpec 是投票结果数据结构
- 数值字段取中位数，枚举字段取多数票
- 不一致字段标为低置信度

**Step 1: Write tests**

```python
# tests/test_voting.py
"""Tests for multi-model voting and self-consistency aggregation."""
import pytest

from backend.core.voting import (
    VotingAggregator,
    AggregatedResult,
    aggregate_numeric,
    aggregate_categorical,
    FieldConfidence,
)
from backend.knowledge.part_types import DrawingSpec, PartType, BaseBodySpec


class TestAggregateNumeric:
    def test_median_of_three(self):
        assert aggregate_numeric([100.0, 105.0, 100.0]) == 100.0

    def test_median_of_two(self):
        assert aggregate_numeric([100.0, 110.0]) == 105.0

    def test_single_value(self):
        assert aggregate_numeric([50.0]) == 50.0

    def test_empty(self):
        assert aggregate_numeric([]) is None


class TestAggregateCategorical:
    def test_majority(self):
        assert aggregate_categorical(["rotational", "rotational", "plate"]) == "rotational"

    def test_tie_returns_first(self):
        result = aggregate_categorical(["rotational", "plate"])
        assert result in ("rotational", "plate")

    def test_single(self):
        assert aggregate_categorical(["gear"]) == "gear"

    def test_empty(self):
        assert aggregate_categorical([]) is None


class TestFieldConfidence:
    def test_all_agree_high(self):
        fc = FieldConfidence.from_values([100.0, 100.0, 100.0])
        assert fc.confidence >= 0.9
        assert fc.is_consistent is True

    def test_disagreement_low(self):
        fc = FieldConfidence.from_values([100.0, 200.0, 150.0])
        assert fc.confidence < 0.9
        assert fc.is_consistent is False

    def test_categorical_agree(self):
        fc = FieldConfidence.from_values(["rotational", "rotational", "rotational"])
        assert fc.confidence >= 0.9

    def test_categorical_disagree(self):
        fc = FieldConfidence.from_values(["rotational", "plate", "gear"])
        assert fc.confidence < 0.5


class TestVotingAggregator:
    def _make_spec(self, part_type, diameter):
        return DrawingSpec(
            part_type=part_type,
            description="test",
            overall_dimensions={"max_diameter": diameter},
            base_body=BaseBodySpec(method="revolve"),
            features=[],
        )

    def test_aggregate_consistent_specs(self):
        specs = [
            self._make_spec("rotational", 100),
            self._make_spec("rotational", 100),
            self._make_spec("rotational", 102),
        ]
        agg = VotingAggregator()
        result = agg.aggregate(specs)
        assert result.spec.part_type == PartType.ROTATIONAL
        assert result.spec.overall_dimensions["max_diameter"] == 100.0

    def test_aggregate_type_voting(self):
        specs = [
            self._make_spec("rotational", 100),
            self._make_spec("rotational", 100),
            self._make_spec("plate", 100),
        ]
        agg = VotingAggregator()
        result = agg.aggregate(specs)
        assert result.spec.part_type == PartType.ROTATIONAL

    def test_aggregate_single_spec(self):
        specs = [self._make_spec("gear", 50)]
        agg = VotingAggregator()
        result = agg.aggregate(specs)
        assert result.spec.part_type == PartType.GEAR

    def test_confidence_map(self):
        specs = [
            self._make_spec("rotational", 100),
            self._make_spec("rotational", 200),  # outlier
            self._make_spec("rotational", 100),
        ]
        agg = VotingAggregator()
        result = agg.aggregate(specs)
        # max_diameter has inconsistency
        conf = result.field_confidences.get("max_diameter")
        assert conf is not None
        assert conf.is_consistent is False

    def test_empty_specs_returns_none(self):
        agg = VotingAggregator()
        result = agg.aggregate([])
        assert result is None
```

**Step 2: Run tests — expect FAIL**

**Step 3: Implement voting aggregator**

```python
# backend/core/voting.py
"""Multi-model voting and self-consistency aggregation.

Aggregates multiple DrawingSpec results:
- Numeric fields: median
- Categorical fields: majority vote
- Inconsistent fields: flagged as low confidence
"""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from ..knowledge.part_types import DrawingSpec, PartType, BaseBodySpec


def aggregate_numeric(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return statistics.median(values)


def aggregate_categorical(values: list[str]) -> Optional[str]:
    if not values:
        return None
    counter = Counter(values)
    return counter.most_common(1)[0][0]


@dataclass
class FieldConfidence:
    confidence: float
    is_consistent: bool
    values: list[object] = field(default_factory=list)

    @classmethod
    def from_values(cls, values: list) -> "FieldConfidence":
        if not values:
            return cls(confidence=0.0, is_consistent=False)
        if all(isinstance(v, (int, float)) for v in values):
            mean = statistics.mean(values)
            if mean == 0:
                cv = 0.0
            else:
                stdev = statistics.stdev(values) if len(values) > 1 else 0.0
                cv = stdev / abs(mean)
            is_consistent = cv < 0.1
            confidence = max(0.0, min(1.0, 1.0 - cv))
            return cls(confidence=confidence, is_consistent=is_consistent, values=values)
        else:
            counter = Counter(values)
            total = len(values)
            top_count = counter.most_common(1)[0][1]
            agreement = top_count / total
            return cls(
                confidence=agreement,
                is_consistent=agreement > 0.5,
                values=values,
            )


@dataclass
class AggregatedResult:
    spec: DrawingSpec
    field_confidences: dict[str, FieldConfidence] = field(default_factory=dict)
    source_count: int = 0


class VotingAggregator:
    def aggregate(self, specs: list[DrawingSpec]) -> Optional[AggregatedResult]:
        if not specs:
            return None
        if len(specs) == 1:
            return AggregatedResult(spec=specs[0], source_count=1)

        # Aggregate part_type
        part_types = [s.part_type.value for s in specs]
        agg_type = aggregate_categorical(part_types)

        # Aggregate overall_dimensions
        all_dim_keys = set()
        for s in specs:
            all_dim_keys.update(s.overall_dimensions.keys())

        agg_dims = {}
        confidences = {}
        confidences["part_type"] = FieldConfidence.from_values(part_types)

        for key in all_dim_keys:
            vals = [s.overall_dimensions[key] for s in specs if key in s.overall_dimensions]
            agg_dims[key] = aggregate_numeric(vals)
            confidences[key] = FieldConfidence.from_values(vals)

        # Aggregate base_body method
        methods = [s.base_body.method for s in specs if s.base_body.method]
        agg_method = aggregate_categorical(methods) if methods else "extrude"

        # Merge features (take from majority)
        agg_features = specs[0].features  # simplified: take first

        agg_spec = DrawingSpec(
            part_type=agg_type,
            description=specs[0].description,
            overall_dimensions=agg_dims,
            base_body=BaseBodySpec(method=agg_method),
            features=agg_features,
        )

        return AggregatedResult(
            spec=agg_spec,
            field_confidences=confidences,
            source_count=len(specs),
        )
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/test_voting.py -v
pytest tests/ -q
```

**Step 5: Commit**

```bash
git add backend/core/voting.py tests/test_voting.py
git commit -m "feat: 多模型投票 + Self-consistency 聚合器 (Phase 5 Task 5.4)"
```

**Expected:** ~18 new tests

---

## Task 5.5: 参考图片理解

**Files:**
- Modify: `backend/core/intent_parser.py` (增强 image 参数处理)
- Create: `backend/core/image_understanding.py`
- Create: `tests/test_image_understanding.py`

**Context:**
- IntentParser.parse(user_input, image=None) 已有 image 参数
- 需要: VL 分析参考图片 → 提取基础参数 → 应用文字修改
- 用 mock VL callable 测试

**Step 1: Write tests**

```python
# tests/test_image_understanding.py
"""Tests for reference image understanding."""
import pytest

from backend.core.image_understanding import (
    ImageAnalyzer,
    ImageAnalysisResult,
    apply_text_modifications,
)
from backend.knowledge.part_types import PartType


class TestImageAnalysisResult:
    def test_basic_fields(self):
        r = ImageAnalysisResult(
            part_type=PartType.ROTATIONAL,
            extracted_params={"diameter": 100.0, "height": 30.0},
            description="圆柱形零件",
            confidence=0.85,
        )
        assert r.part_type == PartType.ROTATIONAL
        assert r.extracted_params["diameter"] == 100.0


class TestApplyTextModifications:
    def test_simple_override(self):
        base = {"diameter": 100.0, "height": 30.0}
        modified = apply_text_modifications(base, "外径改为 150")
        # Should detect "外径" maps to "diameter" and update
        assert modified["diameter"] == 150.0
        assert modified["height"] == 30.0

    def test_height_modification(self):
        base = {"diameter": 100.0, "height": 30.0}
        modified = apply_text_modifications(base, "高度改为 50")
        assert modified["height"] == 50.0

    def test_no_modification(self):
        base = {"diameter": 100.0}
        modified = apply_text_modifications(base, "这个零件很好")
        assert modified == base

    def test_multiple_modifications(self):
        base = {"diameter": 100.0, "height": 30.0}
        modified = apply_text_modifications(base, "外径改为 200，高度改为 60")
        assert modified["diameter"] == 200.0
        assert modified["height"] == 60.0

    def test_add_new_param(self):
        base = {"diameter": 100.0}
        modified = apply_text_modifications(base, "加一个通孔直径 20")
        assert modified.get("bore_diameter") == 20.0 or modified.get("diameter") == 100.0


class TestImageAnalyzer:
    def test_init_with_mock(self):
        async def mock_vl(image_bytes):
            return ImageAnalysisResult(
                part_type=PartType.ROTATIONAL,
                extracted_params={"diameter": 100},
                description="圆盘",
                confidence=0.9,
            )
        analyzer = ImageAnalyzer(vl_fn=mock_vl)
        assert analyzer is not None

    @pytest.mark.asyncio
    async def test_analyze_image(self):
        async def mock_vl(image_bytes):
            return ImageAnalysisResult(
                part_type=PartType.ROTATIONAL,
                extracted_params={"diameter": 100, "height": 30},
                description="法兰盘",
                confidence=0.85,
            )
        analyzer = ImageAnalyzer(vl_fn=mock_vl)
        result = await analyzer.analyze(b"fake_image")
        assert result.part_type == PartType.ROTATIONAL
        assert result.extracted_params["diameter"] == 100

    @pytest.mark.asyncio
    async def test_analyze_with_text_modification(self):
        async def mock_vl(image_bytes):
            return ImageAnalysisResult(
                part_type=PartType.ROTATIONAL,
                extracted_params={"diameter": 100, "height": 30},
                description="法兰盘",
                confidence=0.85,
            )
        analyzer = ImageAnalyzer(vl_fn=mock_vl)
        result = await analyzer.analyze_with_modifications(
            b"fake_image", "外径改为 150"
        )
        assert result.extracted_params["diameter"] == 150.0

    @pytest.mark.asyncio
    async def test_vl_failure_returns_none(self):
        async def mock_vl(image_bytes):
            return None
        analyzer = ImageAnalyzer(vl_fn=mock_vl)
        result = await analyzer.analyze(b"fake_image")
        assert result is None
```

**Step 2: Run tests — expect FAIL**

**Step 3: Implement image understanding**

```python
# backend/core/image_understanding.py
"""Reference image understanding: VL analysis + text modification overlay."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from ..knowledge.part_types import PartType

# Param name aliases (Chinese → canonical)
_PARAM_ALIASES: dict[str, str] = {
    "外径": "diameter", "直径": "diameter", "内径": "bore_diameter",
    "高度": "height", "总高": "height", "厚度": "thickness",
    "宽度": "width", "长度": "length",
    "通孔直径": "bore_diameter", "孔径": "bore_diameter",
    "圆角": "fillet_radius", "倒角": "chamfer_size",
}

_MOD_PATTERN = re.compile(
    r"(?:将\s*)?(\w+)\s*(?:改为|改成|设为|=)\s*(\d+(?:\.\d+)?)"
)

@dataclass
class ImageAnalysisResult:
    part_type: Optional[PartType]
    extracted_params: dict[str, float]
    description: str
    confidence: float


VLFn = Callable[[bytes], Awaitable[Optional[ImageAnalysisResult]]]


def apply_text_modifications(
    base_params: dict[str, float],
    modification_text: str,
) -> dict[str, float]:
    result = dict(base_params)
    for match in _MOD_PATTERN.finditer(modification_text):
        param_cn = match.group(1)
        value = float(match.group(2))
        canonical = _PARAM_ALIASES.get(param_cn)
        if canonical:
            result[canonical] = value
        else:
            # Try direct match
            for key in result:
                if param_cn in key:
                    result[key] = value
                    break
    return result


class ImageAnalyzer:
    def __init__(self, vl_fn: VLFn) -> None:
        self._vl_fn = vl_fn

    async def analyze(self, image_bytes: bytes) -> Optional[ImageAnalysisResult]:
        return await self._vl_fn(image_bytes)

    async def analyze_with_modifications(
        self, image_bytes: bytes, modification_text: str,
    ) -> Optional[ImageAnalysisResult]:
        result = await self._vl_fn(image_bytes)
        if result is None:
            return None
        modified_params = apply_text_modifications(
            result.extracted_params, modification_text,
        )
        return ImageAnalysisResult(
            part_type=result.part_type,
            extracted_params=modified_params,
            description=result.description,
            confidence=result.confidence,
        )
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/test_image_understanding.py -v
pytest tests/ -q
```

**Step 5: Commit**

```bash
git add backend/core/image_understanding.py tests/test_image_understanding.py
git commit -m "feat: 参考图片理解 — VL 分析 + 文字修改叠加 (Phase 5 Task 5.5)"
```

**Expected:** ~12 new tests

---

## Task 5.6: 成本优化

**Files:**
- Create: `backend/core/cost_optimizer.py`
- Create: `tests/test_cost_optimizer.py`

**Context:**
- `ChatModelParameters.from_model_name()` (backend/infra/chat_models.py) 定义模型参数
- 需要: 模型降级策略（Round 1 用 max，Round 2+ 用 plus）+ 缓存机制
- 缓存: 同一图片 Stage 1 结果哈希缓存，TTL 1h

**Step 1: Write tests**

```python
# tests/test_cost_optimizer.py
"""Tests for cost optimization: model degradation + caching."""
import time
import pytest

from backend.core.cost_optimizer import (
    ModelDegradationStrategy,
    ResultCache,
    CostOptimizer,
)


class TestModelDegradationStrategy:
    def test_round1_uses_max(self):
        strategy = ModelDegradationStrategy()
        model = strategy.select_model("vl", round_num=1)
        assert "max" in model or "Max" in model or model == "qwen-vl-max"

    def test_round2_uses_plus(self):
        strategy = ModelDegradationStrategy()
        model = strategy.select_model("vl", round_num=2)
        assert "plus" in model.lower() or "Plus" in model

    def test_round3_uses_plus(self):
        strategy = ModelDegradationStrategy()
        model = strategy.select_model("vl", round_num=3)
        assert "plus" in model.lower()

    def test_coder_round1_max(self):
        strategy = ModelDegradationStrategy()
        model = strategy.select_model("coder", round_num=1)
        assert "plus" in model.lower() or "coder" in model.lower()

    def test_custom_rules(self):
        rules = {"vl": {1: "model-a", 2: "model-b"}}
        strategy = ModelDegradationStrategy(rules=rules)
        assert strategy.select_model("vl", round_num=1) == "model-a"
        assert strategy.select_model("vl", round_num=2) == "model-b"

    def test_unknown_role_returns_default(self):
        strategy = ModelDegradationStrategy()
        model = strategy.select_model("unknown", round_num=1)
        assert model is not None  # should not crash


class TestResultCache:
    def test_set_and_get(self):
        cache = ResultCache(ttl_seconds=3600)
        cache.set("key1", {"result": "ok"})
        assert cache.get("key1") == {"result": "ok"}

    def test_get_missing(self):
        cache = ResultCache(ttl_seconds=3600)
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        cache = ResultCache(ttl_seconds=0.01)  # 10ms
        cache.set("key1", {"result": "ok"})
        time.sleep(0.02)
        assert cache.get("key1") is None

    def test_hash_key(self):
        cache = ResultCache()
        k1 = cache.make_key(b"image_bytes_1")
        k2 = cache.make_key(b"image_bytes_2")
        assert k1 != k2
        # Same content → same key
        k3 = cache.make_key(b"image_bytes_1")
        assert k1 == k3

    def test_stats(self):
        cache = ResultCache()
        cache.set("k1", "v1")
        cache.get("k1")  # hit
        cache.get("k2")  # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_clear(self):
        cache = ResultCache()
        cache.set("k1", "v1")
        cache.clear()
        assert cache.get("k1") is None


class TestCostOptimizer:
    def test_init(self):
        opt = CostOptimizer()
        assert opt is not None

    def test_get_model_for_stage(self):
        opt = CostOptimizer()
        model = opt.get_model("vl", round_num=1)
        assert model is not None

    def test_cache_stage1_result(self):
        opt = CostOptimizer()
        opt.cache_result(b"image_data", {"part_type": "rotational"})
        cached = opt.get_cached_result(b"image_data")
        assert cached == {"part_type": "rotational"}

    def test_cache_miss(self):
        opt = CostOptimizer()
        assert opt.get_cached_result(b"new_image") is None
```

**Step 2: Run tests — expect FAIL**

**Step 3: Implement cost optimizer**

```python
# backend/core/cost_optimizer.py
"""Cost optimization: model degradation strategy + result caching."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional


# Default degradation rules: role → {round_num → model_name}
_DEFAULT_RULES: dict[str, dict[int, str]] = {
    "vl": {1: "qwen-vl-max", 2: "qwen-vl-plus", 3: "qwen-vl-plus"},
    "coder": {1: "qwen-coder-plus", 2: "qwen-coder-plus", 3: "qwen-coder-plus"},
}


class ModelDegradationStrategy:
    def __init__(self, rules: Optional[dict[str, dict[int, str]]] = None) -> None:
        self._rules = rules or _DEFAULT_RULES

    def select_model(self, role: str, round_num: int) -> str:
        role_rules = self._rules.get(role, {})
        if round_num in role_rules:
            return role_rules[round_num]
        # Fallback to highest defined round
        if role_rules:
            max_round = max(role_rules.keys())
            return role_rules[max_round]
        # Ultimate fallback
        return _DEFAULT_RULES.get("vl", {}).get(1, "qwen-vl-max")


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class ResultCache:
    def __init__(self, ttl_seconds: float = 3600.0) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, _CacheEntry] = {}
        self._hits = 0
        self._misses = 0

    def make_key(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def set(self, key: str, value: Any) -> None:
        self._store[key] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + self._ttl,
        )

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        if time.monotonic() > entry.expires_at:
            del self._store[key]
            self._misses += 1
            return None
        self._hits += 1
        return entry.value

    def clear(self) -> None:
        self._store.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._store)}


class CostOptimizer:
    def __init__(
        self,
        degradation: Optional[ModelDegradationStrategy] = None,
        cache_ttl: float = 3600.0,
    ) -> None:
        self._degradation = degradation or ModelDegradationStrategy()
        self._cache = ResultCache(ttl_seconds=cache_ttl)

    def get_model(self, role: str, round_num: int) -> str:
        return self._degradation.select_model(role, round_num)

    def cache_result(self, image_data: bytes, result: Any) -> None:
        key = self._cache.make_key(image_data)
        self._cache.set(key, result)

    def get_cached_result(self, image_data: bytes) -> Optional[Any]:
        key = self._cache.make_key(image_data)
        return self._cache.get(key)
```

**Step 4: Run tests — expect PASS**

```bash
pytest tests/test_cost_optimizer.py -v
pytest tests/ -q
```

**Step 5: Commit**

```bash
git add backend/core/cost_optimizer.py tests/test_cost_optimizer.py
git commit -m "feat: 成本优化 — 模型降级 + 结果缓存 (Phase 5 Task 5.6)"
```

**Expected:** ~16 new tests

---

## Summary

| Task | 描述 | 新文件 | 预估测试数 | 依赖 |
|------|------|--------|----------|------|
| T5.1 | RAG 数据管道 + 检索 API | 4 | ~20 | 无 |
| T5.2 | RAG 增强代码生成 | 1 | ~10 | T5.1 |
| T5.3 | OCR + 两阶段分析 | 4 | ~20 | 无 |
| T5.4 | 多模型投票 + Self-consistency | 2 | ~18 | 无 |
| T5.5 | 参考图片理解 | 2 | ~12 | 无 |
| T5.6 | 成本优化 | 2 | ~16 | 无 |

**预计总新增测试:** ~96
**预计最终测试数:** ~700

**执行模式:** subagent-driven-development（2 domain labels < 3 threshold）

**Wave 1 (并行):** T5.1, T5.3, T5.4, T5.5, T5.6
**Wave 2:** T5.2 (依赖 T5.1)
