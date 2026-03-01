## ADDED Requirements

### Requirement: analyze_organic_node builds OrganicSpec via LLM

The system SHALL implement `analyze_organic_node` as a LangGraph node that invokes `OrganicSpecBuilder.build()` to translate user prompt, extract shape category, and suggest bounding box, storing the result in `CadJobState.organic_spec`.

#### Scenario: Text prompt analyzed successfully
- **WHEN** `analyze_organic_node` executes with `input_text="一个小熊雕塑"`
- **THEN** `OrganicSpecBuilder.build()` is called with the prompt
- **AND** the result is stored in `state["organic_spec"]` as a dict
- **AND** a `job.organic_spec_ready` SSE event is dispatched with the full spec in payload
- **AND** the node returns `status="awaiting_confirmation"`

#### Scenario: LLM timeout triggers failure
- **WHEN** `OrganicSpecBuilder.build()` does not complete within 60 seconds
- **THEN** `asyncio.wait_for` raises `TimeoutError`
- **AND** the node returns `{"status": "failed", "error": "Organic spec 构建超时（60s）", "failure_reason": "timeout"}`
- **AND** a `job.failed` SSE event is dispatched

#### Scenario: LLM fallback on failure
- **WHEN** the LLM call inside `OrganicSpecBuilder` fails (network error, rate limit, etc.)
- **THEN** `OrganicSpecBuilder._fallback()` returns the original prompt as `prompt_en` with `shape_category="general"`
- **AND** the node continues with the fallback spec (does not fail the job)

### Requirement: generate_organic_mesh_node invokes MeshProvider

The system SHALL implement `generate_organic_mesh_node` as a LangGraph node that creates a MeshProvider instance and calls `provider.generate()` to produce a raw mesh file.

#### Scenario: Mesh generated successfully
- **WHEN** `generate_organic_mesh_node` executes with confirmed organic spec
- **THEN** a MeshProvider is created based on `state["organic_provider"]`
- **AND** `provider.generate(spec, reference_image, on_progress=callback)` is called with an `on_progress` callback
- **AND** the callback dispatches `job.generating` keepalive SSE events every 15-30s during the 3-5 minute generation period to prevent SSE connection timeout
- **AND** the raw mesh path is stored in `state["raw_mesh_path"]`
- **AND** a `job.generating` SSE event is dispatched with `stage="mesh_generation"`

#### Scenario: Idempotent skip when mesh exists
- **WHEN** `state["raw_mesh_path"]` is set and the file exists on disk
- **THEN** the node returns `{}` immediately without calling the provider

#### Scenario: Provider failure
- **WHEN** `provider.generate()` raises an exception (API error, timeout, etc.)
- **THEN** the node returns `{"status": "failed", "error": str(exc), "failure_reason": "generation_error"}`
- **AND** a `job.failed` SSE event is dispatched

#### Scenario: Reference image loaded from upload
- **WHEN** `state["organic_reference_image"]` contains a file_id
- **THEN** the node reads the uploaded image bytes from `outputs/organic/uploads/{file_id}.*`
- **AND** passes the bytes to `provider.generate()` as `reference_image` parameter

### Requirement: postprocess_organic_node executes full post-processing pipeline

The system SHALL implement `postprocess_organic_node` as a single LangGraph node that sequentially executes load, repair, scale, boolean cuts, validate, export (GLB/STL/3MF), and printability check, dispatching per-step SSE events.

#### Scenario: Full post-processing pipeline succeeds
- **WHEN** `postprocess_organic_node` executes with a valid `raw_mesh_path`
- **THEN** the node wraps CPU-bound mesh operations (pymeshlab, trimesh, manifold3d) via `asyncio.to_thread` to avoid blocking the event loop
- **AND** executes steps in order: load → repair → scale → boolean → validate → export → printability
- **AND** each step dispatches a `job.post_processing` SSE event with `{step, step_status, message, progress}`
- **AND** the final state includes `model_url`, `mesh_stats`, `printability`, `organic_warnings`, `organic_result`

#### Scenario: Boolean cuts skipped in draft mode
- **WHEN** `organic_quality_mode` is `"draft"` or no `engineering_cuts` are defined in the spec
- **THEN** the boolean step dispatches `{step: "boolean", step_status: "skipped"}`
- **AND** processing continues to validate step

#### Scenario: Boolean cuts fail gracefully
- **WHEN** `manifold3d` raises an exception during boolean operations
- **THEN** the node catches the exception and adds a warning to `organic_warnings`
- **AND** the boolean step dispatches `{step: "boolean", step_status: "failed"}`
- **AND** processing continues with the pre-boolean mesh (graceful degradation)

#### Scenario: Export produces GLB, STL, and 3MF
- **WHEN** the validate step completes
- **THEN** the mesh is exported to `outputs/{job_id}/model.glb`, `model.stl`, and `model.3mf`
- **AND** `organic_result` contains `model_url`, `stl_url`, and `threemf_url` with correct paths
- **AND** if 3MF export fails, `threemf_url` is set to `null` and a warning is logged

#### Scenario: Printability check runs on exported mesh
- **WHEN** export completes
- **THEN** `PrintabilityChecker.check()` runs on the STL file
- **AND** material and time estimates are included in the printability result
- **AND** if printability check fails, `printability` is set to `null` (non-fatal)
