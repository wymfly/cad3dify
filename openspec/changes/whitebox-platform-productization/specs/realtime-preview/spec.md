## ADDED Requirements

### Requirement: Debounce parametric preview
The frontend SHALL send parameter preview requests with a 500ms debounce. Each parameter change resets the debounce timer.

#### Scenario: Parameter change triggers preview
- **WHEN** user adjusts a parameter value in ParamForm
- **THEN** the system SHALL wait 500ms after the last change, then send `POST /api/v1/preview/parametric` with current parameters

#### Scenario: Rapid parameter changes
- **WHEN** user adjusts multiple parameters within 500ms
- **THEN** only the final state SHALL be sent as a preview request (earlier intermediate states are discarded)

#### Scenario: Preview request format
- **WHEN** a preview request is sent
- **THEN** it SHALL include `template_name` and `params` (the current parameter values)

### Requirement: Backend preview rendering with timeout
The backend SHALL render a GLB preview from template parameters with a 5-second hard timeout. Timeout SHALL NOT block the user workflow.

#### Scenario: Successful preview
- **WHEN** `POST /api/v1/preview/parametric` receives valid parameters
- **THEN** the server SHALL execute the CadQuery template, export to GLB, and return the GLB file within 5 seconds

#### Scenario: Preview timeout
- **WHEN** CadQuery execution exceeds 5 seconds
- **THEN** the server SHALL abort rendering and return HTTP 408 with error code `PREVIEW_TIMEOUT`

#### Scenario: Preview validation failure
- **WHEN** parameters fail template validation
- **THEN** the server SHALL return HTTP 422 with error code `VALIDATION_FAILED` and details listing each invalid parameter

### Requirement: 3D viewer hot update
The Viewer3D component SHALL hot-update the displayed model when a new preview GLB is received, without full page reload.

#### Scenario: GLB hot swap
- **WHEN** a new preview GLB response is received
- **THEN** Viewer3D SHALL replace the current model with the new GLB and maintain the current camera position and zoom level

#### Scenario: Loading state during preview
- **WHEN** a preview request is in-flight
- **THEN** Viewer3D SHALL display a subtle loading indicator (e.g., spinner overlay) without hiding the current model

#### Scenario: Preview error display
- **WHEN** a preview request returns timeout or error
- **THEN** Viewer3D SHALL display "预览不可用" message overlay while keeping the last successfully rendered model visible

### Requirement: Preview caching
The backend SHALL cache preview results to avoid redundant CadQuery executions for identical parameter sets.

#### Scenario: Cache hit
- **WHEN** a preview request arrives with parameters identical to a recent request
- **THEN** the server SHALL return the cached GLB without re-executing CadQuery

#### Scenario: Cache eviction
- **WHEN** the preview cache exceeds its size limit (default: 50 entries)
- **THEN** the least-recently-used entry SHALL be evicted

### Requirement: Preview availability indication
The ParamForm SHALL indicate whether real-time preview is available for the current template.

#### Scenario: Preview supported
- **WHEN** user opens ParamForm for a template that supports preview
- **THEN** the form SHALL display a "实时预览" badge and enable automatic preview updates

#### Scenario: Preview not supported
- **WHEN** user opens ParamForm for a template without preview support (e.g., complex assembly templates)
- **THEN** the form SHALL display "预览不可用" and provide a manual "生成预览" button instead
