"""Compatibility tests: ensure public API is importable from both old and new paths."""


def test_cad3dify_public_api_importable():
    """cad3dify 公共 API 仍可通过旧路径导入"""
    from cad3dify import generate_step_v2
    from cad3dify import generate_step_from_2d_cad_image
    from cad3dify import ImageData

    assert callable(generate_step_v2)
    assert callable(generate_step_from_2d_cad_image)
    assert ImageData is not None


def test_backend_knowledge_import():
    """backend.knowledge 新路径可导入核心数据模型"""
    from backend.knowledge.part_types import DrawingSpec, PartType, BaseBodySpec

    assert DrawingSpec is not None
    assert PartType is not None
    assert BaseBodySpec is not None


def test_backend_validators_import():
    """backend.core.validators 新路径可导入"""
    from backend.core.validators import (
        validate_code_params,
        validate_bounding_box,
        validate_step_geometry,
        ValidationResult,
        BBoxResult,
        GeometryResult,
    )

    assert callable(validate_code_params)
    assert callable(validate_bounding_box)
    assert callable(validate_step_geometry)


def test_backend_knowledge_examples_import():
    """backend.knowledge.examples 新路径可导入"""
    from backend.knowledge.examples import (
        TaggedExample,
        EXAMPLES_BY_TYPE,
        get_tagged_examples,
    )

    assert TaggedExample is not None
    assert isinstance(EXAMPLES_BY_TYPE, dict)
    assert callable(get_tagged_examples)


def test_backend_pipeline_import():
    """backend.pipeline 新路径可导入"""
    from backend.pipeline.pipeline import generate_step_v2, generate_step_from_2d_cad_image

    assert callable(generate_step_v2)
    assert callable(generate_step_from_2d_cad_image)
