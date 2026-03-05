## MODIFIED Requirements

### Requirement: HITL via supports_hitl descriptor flag
Nodes requiring human-in-the-loop confirmation SHALL declare `supports_hitl=True` in their `@register_node` descriptor. The `PipelineBuilder` SHALL automatically collect these into `interrupt_before` when compiling the graph. No manual `interrupt_before` list maintenance is needed.

#### Scenario: HITL node auto-detected
- **WHEN** `confirm_with_user` is registered with `supports_hitl=True`
- **THEN** `graph.compile(interrupt_before=["confirm_with_user"])` is called automatically by `PipelineBuilder`

#### Scenario: Multiple HITL nodes
- **WHEN** two nodes have `supports_hitl=True` (e.g., `confirm_with_user` and a hypothetical `confirm_print_settings`)
- **THEN** both appear in `interrupt_before` list
