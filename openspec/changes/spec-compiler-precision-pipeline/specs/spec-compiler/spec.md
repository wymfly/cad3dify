## ADDED Requirements

### Requirement: SpecCompiler provides unified code compilation dispatch

The system SHALL provide a `SpecCompiler` class at `backend/core/spec_compiler.py` that accepts a part specification (IntentSpec or DrawingSpec) and confirmed parameters, and produces a STEP file through a template-first-then-LLM-fallback strategy.

#### Scenario: Template match succeeds and renders STEP
- **WHEN** `SpecCompiler.compile()` is called with `matched_template="cylinder_simple"` and `confirmed_params={"diameter": 50, "height": 100}`
- **THEN** the compiler calls `TemplateEngine.render("cylinder_simple", params)` to produce CadQuery code
- **AND** executes the code via `SafeExecutor` to produce a STEP file at the specified output path
- **AND** returns a `CompileResult` with `method="template"`, `template_name="cylinder_simple"`, and `step_path` set

#### Scenario: Template match fails and falls back to LLM generation
- **WHEN** `SpecCompiler.compile()` is called with `matched_template=None`
- **THEN** the compiler invokes the V2 CodeGeneratorChain via `generate_step_from_text()` to produce CadQuery code from the intent description
- **AND** returns a `CompileResult` with `method="llm_fallback"` and `step_path` set

#### Scenario: LLM fallback also fails
- **WHEN** both template rendering and LLM generation fail
- **THEN** the compiler raises `CompilationError` with the original exception chained
- **AND** the error message includes which methods were attempted

### Requirement: Template routing uses part_type semantic matching

The system SHALL replace keyword-based template matching with part_type-based semantic routing using `TemplateEngine.find_matches(part_type)`.

#### Scenario: part_type routes to correct template candidates
- **WHEN** IntentParser returns `part_type="rotational"` and known_params include `diameter` and `height`
- **THEN** `SpecCompiler` calls `TemplateEngine.find_matches("rotational")` to get all rotational templates
- **AND** ranks candidates by parameter coverage (ratio of user-known params to template params)
- **AND** selects the highest-scoring template as `matched_template`

#### Scenario: No templates match the part_type
- **WHEN** `TemplateEngine.find_matches(part_type)` returns an empty list
- **THEN** `matched_template` is set to `None`
- **AND** the text-path proceeds to LLM fallback

#### Scenario: Multiple templates match with same score
- **WHEN** two or more templates have identical parameter coverage scores
- **THEN** the template with fewer total parameters is preferred (simpler model)

### Requirement: EngineeringStandards recommendations integrated into analysis

The system SHALL call `EngineeringStandards.recommend_params()` during intent analysis and include recommendations in the state for display to users.

#### Scenario: Recommendations generated for known part_type
- **WHEN** `analyze_intent_node` completes intent parsing with `part_type="rotational"` and `known_params={"diameter": 50}`
- **THEN** the node calls `EngineeringStandards.recommend_params("rotational", {"diameter": 50})`
- **AND** includes the returned `list[ParamRecommendation]` in the state as `recommendations`
- **AND** dispatches `job.intent_analyzed` SSE event with `recommendations` field

#### Scenario: Recommendations tolerate unknown part_type
- **WHEN** `EngineeringStandards.recommend_params()` is called with an unsupported part_type
- **THEN** the node returns an empty recommendations list
- **AND** does not fail or affect the rest of the analysis flow
