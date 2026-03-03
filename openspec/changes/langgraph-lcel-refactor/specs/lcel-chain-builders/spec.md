## ADDED Requirements

### Requirement: Vision analysis LCEL chain replaces DrawingAnalyzerChain

The system SHALL provide `build_vision_analysis_chain()` in `backend/graph/chains/vision_chain.py` that returns an LCEL `Runnable` equivalent to `DrawingAnalyzerChain`. The chain SHALL accept `{"image_type": str, "image_data": str}` and return `{"result": DrawingSpec | None, "reasoning": str | None}`.

#### Scenario: Vision chain produces identical prompt to SequentialChain
- **WHEN** `build_vision_analysis_chain()` is called and the resulting chain receives `{"image_type": "png", "image_data": "<base64>"}`
- **THEN** the formatted prompt sent to the LLM SHALL be byte-identical to what `DrawingAnalyzerChain().invoke(ImageData(...))` would produce
- **AND** the LLM instance SHALL be obtained via `get_model_for_role("vision_analyzer").create_chat_model()`

#### Scenario: Vision chain parses LLM output to DrawingSpec
- **WHEN** the LLM returns a response containing a `\`\`\`json` code block with valid DrawingSpec fields
- **THEN** the chain SHALL parse it into a `DrawingSpec` Pydantic model via `_parse_drawing_spec()`
- **AND** return `{"result": <DrawingSpec>, "reasoning": <str|None>}`

#### Scenario: Vision chain returns None on parse failure
- **WHEN** the LLM returns malformed output that cannot be parsed as JSON
- **THEN** the chain SHALL return `{"result": None, "reasoning": <str|None>}`
- **AND** log an error via loguru

#### Scenario: Vision chain supports async invocation
- **WHEN** the chain is invoked via `await chain.ainvoke(inputs)`
- **THEN** the LLM call SHALL be fully async (no `asyncio.to_thread()` wrapper)

### Requirement: Code generation LCEL chain replaces CodeGeneratorChain

The system SHALL provide `build_code_gen_chain()` in `backend/graph/chains/code_gen_chain.py` that returns an LCEL `Runnable`. The chain SHALL accept `{"modeling_context": str}` and return `{"result": str | None}`.

#### Scenario: Code gen chain produces CadQuery code
- **WHEN** the chain receives a modeling context string (from `ModelingContext.to_prompt_text()`)
- **THEN** it SHALL invoke the LLM obtained via `get_model_for_role("code_generator").create_chat_model()`
- **AND** parse the response via `_parse_code()` to extract a Python code block
- **AND** return `{"result": "<code>"}` or `{"result": None}` if no code block found

#### Scenario: Code gen chain is async
- **WHEN** the chain is invoked via `await chain.ainvoke(inputs)`
- **THEN** the entire call chain (prompt formatting → LLM → parsing) SHALL be async

### Requirement: VL comparison LCEL chain replaces SmartCompareChain

The system SHALL provide `build_compare_chain(structured: bool = False)` in `backend/graph/chains/compare_chain.py` that returns an LCEL `Runnable`. The chain SHALL accept the same 6-field input dict as `SmartCompareChain` and return `{"result": str | None}`.

#### Scenario: Compare chain sends two images to VL model
- **WHEN** the chain receives `{"drawing_spec": ..., "code": ..., "original_image_type": ..., "original_image_data": ..., "rendered_image_type": ..., "rendered_image_data": ...}`
- **THEN** the formatted prompt SHALL include two `ImagePromptTemplate` entries (original + rendered)
- **AND** the LLM SHALL be obtained via `get_model_for_role("refiner_vl").create_chat_model()`

#### Scenario: Compare chain detects PASS (text mode)
- **WHEN** `build_compare_chain(structured=False)` is used (default)
- **AND** the VL model returns a response containing "PASS" (case-insensitive) and the response length is < 20 characters
- **THEN** the chain SHALL return `{"result": None}` (no differences found)
- **AND** the PASS detection SHALL use `"PASS" in text.upper() and len(text.strip()) < 20` — matching existing `_extract_comparison()` behavior

#### Scenario: Compare chain detects FAIL with issues (text mode)
- **WHEN** `build_compare_chain(structured=False)` is used (default)
- **AND** the VL model returns a response describing differences
- **THEN** the chain SHALL return `{"result": "<comparison_text>"}` with the full VL output

#### Scenario: Structured mode returns parsed JSON feedback
- **WHEN** `build_compare_chain(structured=True)` is used
- **THEN** the chain SHALL use `_STRUCTURED_COMPARE_PROMPT` instead of `_COMPARE_PROMPT`
- **AND** the output parser SHALL parse the VL response as JSON via `parse_vl_feedback()`
- **AND** PASS detection SHALL use the parsed `feedback.passed` boolean field (NOT the text length heuristic)
- **AND** return `{"result": None}` if `feedback.passed is True`
- **AND** return `{"result": feedback.to_fix_instructions()}` if `feedback.passed is False`

### Requirement: Code fix LCEL chain replaces SmartFixChain

The system SHALL provide `build_fix_chain()` in `backend/graph/chains/fix_chain.py` that returns an LCEL `Runnable`. The chain SHALL accept `{"code": str, "fix_instructions": str}` and return `{"result": str | None}`.

#### Scenario: Fix chain produces corrected code
- **WHEN** the chain receives code and fix instructions
- **THEN** it SHALL invoke the LLM obtained via `get_model_for_role("refiner_coder").create_chat_model()`
- **AND** parse the response via `_parse_code()` to extract a Python code block
- **AND** return `{"result": "<fixed_code>"}` or `{"result": None}`

#### Scenario: Fix chain is async
- **WHEN** the chain is invoked via `await chain.ainvoke(inputs)`
- **THEN** the entire call chain SHALL be async

### Requirement: All chain builders follow consistent factory pattern

The system SHALL ensure all `build_*_chain()` functions follow a consistent pattern: `def build_xxx_chain(**kwargs) -> Runnable` (**synchronous** factory — no `async def`). The factory assembles an LCEL pipeline (`prompt | llm | parser`) and returns a `Runnable`. Callers invoke the chain asynchronously via `await chain.ainvoke(inputs)`.

#### Scenario: Factory function returns composable Runnable
- **WHEN** any `build_*_chain()` is called
- **THEN** the returned object SHALL be a LangChain `Runnable` supporting `.ainvoke()`, `.invoke()`, `.with_retry()`, and `.with_fallbacks()`
- **AND** the factory function itself SHALL be synchronous (`def`, not `async def`)

#### Scenario: Factory function does not cache LLM instances
- **WHEN** `build_vision_analysis_chain()` is called twice
- **THEN** each call SHALL create a new LLM instance via `get_model_for_role()`
- **AND** the caller is responsible for caching if needed

### Requirement: Callers are responsible for input adaptation

The system SHALL document the expected input format for each chain builder. Callers (LangGraph nodes) SHALL perform input adaptation before calling `chain.ainvoke()`:
- `build_vision_analysis_chain()`: caller must decompose `ImageData` into `{"image_type": str, "image_data": str}` (replacing `DrawingAnalyzerChain.prep_inputs()`)
- `build_code_gen_chain()`: caller must convert `ModelingContext` to `{"modeling_context": str}` via `.to_prompt_text()` (replacing `CodeGeneratorChain.prep_inputs()`)
- `build_compare_chain()` / `build_fix_chain()`: input is already flat dict, no adaptation needed

#### Scenario: Vision node adapts ImageData before chain invocation
- **WHEN** `analyze_vision_node` calls the vision chain
- **THEN** it SHALL decompose `ImageData` to `{"image_type": image.type, "image_data": image.data}` before `chain.ainvoke()`
- **AND** SHALL validate that `image_data` is non-empty (replacing the `assert isinstance(image, ImageData)` guard in `DrawingAnalyzerChain.prep_inputs()`)
