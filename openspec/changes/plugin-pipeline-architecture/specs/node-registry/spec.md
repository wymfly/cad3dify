## ADDED Requirements

### Requirement: Node self-registration via decorator
The system SHALL provide a `@register_node` decorator that registers a node function with its `NodeDescriptor` metadata into a global `NodeRegistry` singleton upon module import.

#### Scenario: Register a new node
- **WHEN** a Python module containing `@register_node(name="orientation_optimizer", ...)` is imported
- **THEN** `NodeRegistry` contains a `NodeDescriptor` with name `"orientation_optimizer"` and all declared metadata

#### Scenario: Duplicate node name rejected
- **WHEN** two nodes are registered with the same `name`
- **THEN** the system raises `ValueError` with a message identifying the duplicate name

### Requirement: NodeDescriptor metadata
Each `NodeDescriptor` SHALL contain: `name`, `display_name`, `requires` (list of asset keys with AND/OR syntax), `produces` (list of asset keys), `input_types` (list of applicable input types), `config_model` (Pydantic BaseModel subclass), `strategies` (dict of name→class), `default_strategy`, `is_entry` (bool), `supports_hitl` (bool), `non_fatal` (bool), `description` (str), `estimated_duration` (str|None).

#### Scenario: Descriptor with all fields
- **WHEN** a node is registered with all metadata fields
- **THEN** `registry.get("node_name")` returns a `NodeDescriptor` with all fields accessible

#### Scenario: Descriptor with defaults
- **WHEN** a node is registered with only `name`, `requires`, `produces`
- **THEN** the descriptor has `is_entry=False`, `supports_hitl=False`, `non_fatal=False`, `input_types=["text","drawing","organic"]`, `strategies={}`, `config_model=BaseNodeConfig`

### Requirement: Automatic node discovery
The system SHALL provide a `discover_nodes()` function that imports all Python modules in `backend/graph/nodes/` to trigger `@register_node` decorators.

#### Scenario: All node modules loaded
- **WHEN** `discover_nodes()` is called
- **THEN** every `.py` file in `backend/graph/nodes/` (excluding `__init__.py`) has been imported and its `@register_node` decorators have executed

### Requirement: Registry query methods
`NodeRegistry` SHALL provide `find_producers(asset_key)` returning all nodes that produce a given asset, and `find_consumers(asset_key)` returning all nodes that require a given asset.

#### Scenario: Find producers of step_model
- **WHEN** `registry.find_producers("step_model")` is called
- **THEN** it returns descriptors for `generate_step_text` and `generate_step_drawing`
