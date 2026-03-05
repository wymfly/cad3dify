## ADDED Requirements

### Requirement: Visual DAG pipeline editor
The frontend SHALL provide a PipelineConfigurator component that displays the pipeline as a vertical DAG flowchart. Each node is rendered as a card showing: name, display_name, enabled status, current strategy.

#### Scenario: DAG renders enabled nodes
- **WHEN** the pipeline config has 8 enabled nodes
- **THEN** the DAG shows 8 connected node cards in dependency order with edges between them

#### Scenario: Disabled nodes shown as placeholders
- **WHEN** `orientation_optimizer` is disabled
- **THEN** it appears as a greyed-out semi-transparent card in its topological position, with an enable toggle

### Requirement: Node detail panel
Clicking a node in the DAG SHALL open a detail panel showing: enable/disable toggle, strategy selector (card-style mutual exclusive), parameter form (dynamic based on current strategy), input/output asset keys, description, estimated duration, dependency info.

#### Scenario: Strategy selection changes parameters
- **WHEN** user switches `mesh_repair` strategy from "pymeshlab" to "trimesh_voxel"
- **THEN** the parameter form updates to show `voxel_pitch` field instead of `pymeshlab_filter_script`

#### Scenario: Parameter tooltip
- **WHEN** user hovers the ⓘ icon next to a parameter field
- **THEN** a tooltip shows the parameter's description from the Pydantic Field metadata

### Requirement: Preset selector
The UI SHALL provide preset buttons (fast, balanced, full_print, custom). Selecting a preset SHALL populate all node configs from the preset definition. Modifying any node parameter SHALL auto-switch the preset to "custom".

#### Scenario: Preset application
- **WHEN** user selects "full_print" preset
- **THEN** all node enabled/strategy/param states update to match the full_print preset config

#### Scenario: Custom mode on modification
- **WHEN** user is on "balanced" preset and changes `analyze_dfam.strategy` to "sampling"
- **THEN** the preset indicator switches to "custom"

### Requirement: Real-time dependency validation
The UI SHALL validate the pipeline config in real-time (via `POST /api/v1/pipeline/validate` or client-side logic) and display validation status in a bottom status bar.

#### Scenario: Valid config
- **WHEN** all dependencies are satisfied
- **THEN** status bar shows "✓ 管线配置有效 · N 个节点启用 · 预计耗时 X-Ys"

#### Scenario: Dependency error
- **WHEN** user disables `mesh_repair` but `slice_to_gcode` is enabled (requires watertight_mesh)
- **THEN** status bar shows error: "slice_to_gcode 需要 watertight_mesh，请启用 mesh_repair"
- **AND** both nodes are highlighted with error indicators in the DAG

### Requirement: Runtime pipeline monitoring
During job execution, the same DAG component SHALL switch to monitoring mode, showing real-time node status updates from SSE events (`node.started`, `node.completed`, `node.failed`).

#### Scenario: Node completes
- **WHEN** `node.completed` SSE event arrives for `analyze_intent` with `elapsed_ms=2300`
- **THEN** the `analyze_intent` card shows ✅ icon and "2.3s" duration

#### Scenario: Node executing
- **WHEN** `node.started` SSE event arrives for `generate_step_text`
- **THEN** the `generate_step_text` card shows a pulsing ⏳ icon

#### Scenario: Click completed node for details
- **WHEN** user clicks a completed node card in monitoring mode
- **THEN** a panel shows the node's reasoning summary and output asset previews
