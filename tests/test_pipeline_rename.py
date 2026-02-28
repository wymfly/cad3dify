"""Verify pipeline functions are accessible by new capability-descriptive names."""


def test_new_names_importable() -> None:
    from backend.pipeline.pipeline import (
        analyze_vision_spec,
        generate_step_from_spec,
        analyze_and_generate_step,
    )
    assert callable(analyze_vision_spec)
    assert callable(generate_step_from_spec)
    assert callable(analyze_and_generate_step)


def test_old_names_still_work() -> None:
    from backend.pipeline.pipeline import (
        analyze_drawing,
        generate_from_drawing_spec,
        generate_step_v2,
    )
    assert callable(analyze_drawing)
    assert callable(generate_from_drawing_spec)
    assert callable(generate_step_v2)


def test_new_and_old_are_same_function() -> None:
    from backend.pipeline.pipeline import (
        analyze_vision_spec, analyze_drawing,
        generate_step_from_spec, generate_from_drawing_spec,
        analyze_and_generate_step, generate_step_v2,
    )
    assert analyze_vision_spec is analyze_drawing
    assert generate_step_from_spec is generate_from_drawing_spec
    assert analyze_and_generate_step is generate_step_v2
