## ADDED Requirements

### Requirement: Parametric real-time preview API

The system SHALL provide an API endpoint that accepts template name and parameter values, and returns a draft-quality GLB model for real-time preview in the frontend, with tiered response time targets based on complexity.

#### Scenario: Successful preview generation (simple part)
- **WHEN** a user calls POST /preview/parametric with template_name="flange" and params={outer_diameter: 50, height: 30, ...}
- **THEN** the system renders the template via Jinja2, executes CadQuery in draft quality mode, converts to GLB, and returns the GLB URL
- **AND** the total response time is under 1 second for simple parts (< 10 features)

#### Scenario: Successful preview generation (medium complexity)
- **WHEN** CadQuery execution takes 1-3 seconds (10-30 features)
- **THEN** the preview is still returned successfully
- **AND** the frontend shows a loading indicator during the wait

#### Scenario: Parameter validation failure
- **WHEN** the provided parameters fail template constraint validation
- **THEN** the API returns HTTP 422 with specific constraint violation messages
- **AND** no CadQuery execution is attempted

#### Scenario: Complex part exceeds timeout
- **WHEN** CadQuery execution exceeds 5 seconds (complex geometry with > 30 features)
- **THEN** the API returns HTTP 408 with message "预览超时，请直接生成完整模型"
- **AND** the execution is cancelled

### Requirement: Preview caching

The system SHALL cache preview results keyed by (template_name, params_hash) to avoid redundant CadQuery executions.

#### Scenario: Cache hit
- **WHEN** a preview request matches a cached (template_name, params_hash) combination
- **THEN** the cached GLB URL is returned immediately without CadQuery execution
- **AND** response time is under 50ms

#### Scenario: Cache invalidation
- **WHEN** a template's YAML definition is updated
- **THEN** all cached previews for that template are invalidated

### Requirement: Frontend real-time preview integration

The frontend SHALL trigger preview requests on parameter changes with debouncing, and hot-swap the GLB model in the Three.js viewer.

#### Scenario: Parameter change triggers preview
- **WHEN** a user adjusts a parameter slider in ParamForm
- **THEN** after a 300ms debounce period, the frontend sends a preview request
- **AND** upon receiving the GLB URL, the Three.js viewer replaces the current model with the new preview

#### Scenario: Rapid parameter changes
- **WHEN** a user rapidly adjusts multiple parameters within 300ms
- **THEN** only the final parameter state triggers a preview request (debounce coalesces intermediate changes)

### Requirement: Draft quality mode for preview

The template engine SHALL support a draft quality mode that reduces mesh resolution for faster CadQuery execution and smaller GLB files.

#### Scenario: Draft vs production quality
- **WHEN** draft quality mode is enabled
- **THEN** CadQuery uses reduced tessellation settings (fewer faces, ~70% reduction)
- **AND** the resulting GLB file is smaller (faster transfer)
- **AND** the visual appearance is acceptable for parameter adjustment (smooth enough to judge proportions)
