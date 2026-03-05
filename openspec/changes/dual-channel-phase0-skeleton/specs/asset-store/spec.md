## ADDED Requirements

### Requirement: AssetStore Protocol for file persistence

The system SHALL provide an `AssetStore` Protocol with `save()` and `load()` methods, abstracting the underlying storage backend. The `save()` method returns an opaque URI string; `load()` only accepts URIs produced by the same store implementation. URIs from different store implementations are NOT interchangeable.

#### Scenario: Save asset returns URI
- **WHEN** `asset_store.save(job_id="j1", name="mesh", data=b"...", fmt="obj")` is called
- **THEN** the file SHALL be persisted to storage
- **AND** a URI string SHALL be returned (e.g., `"file:///workspace/jobs/j1/mesh.obj"`)

#### Scenario: Load asset by URI
- **WHEN** `asset_store.load("file:///workspace/jobs/j1/mesh.obj")` is called
- **THEN** the file content SHALL be returned as `bytes`

#### Scenario: Load nonexistent URI raises error
- **WHEN** `asset_store.load("file:///nonexistent/path.obj")` is called
- **THEN** `FileNotFoundError` SHALL be raised

### Requirement: LocalAssetStore implements file:/// storage

The system SHALL provide `LocalAssetStore` implementing `AssetStore`, storing files under a configurable workspace directory.

#### Scenario: Files stored in workspace subdirectory
- **WHEN** `LocalAssetStore(workspace="/workspace")` saves `(job_id="j1", name="mesh", data=..., fmt="obj")`
- **THEN** the file SHALL be written to `/workspace/jobs/j1/mesh.obj`
- **AND** the returned URI SHALL be `"file:///workspace/jobs/j1/mesh.obj"`

#### Scenario: Workspace directory created automatically
- **WHEN** `LocalAssetStore` saves a file and the target directory does not exist
- **THEN** the directory SHALL be created automatically (including parents)

#### Scenario: Workspace from environment variable
- **WHEN** `LocalAssetStore` is created without explicit `workspace` parameter
- **AND** environment variable `CADPILOT_WORKSPACE` is set to `/data/cadpilot`
- **THEN** the workspace SHALL be `/data/cadpilot`

#### Scenario: Workspace defaults to current directory
- **WHEN** `LocalAssetStore` is created without explicit `workspace` parameter
- **AND** environment variable `CADPILOT_WORKSPACE` is not set
- **THEN** the workspace SHALL default to the current working directory

#### Scenario: Save overwrites existing file
- **WHEN** `LocalAssetStore.save(job_id="j1", name="mesh", data=new_data, fmt="obj")` is called
- **AND** the file `/workspace/jobs/j1/mesh.obj` already exists
- **THEN** the file SHALL be overwritten with `new_data`
- **AND** the same URI SHALL be returned

#### Scenario: Path traversal prevented
- **WHEN** `LocalAssetStore.save(job_id="../../../etc", name="passwd", data=b"...", fmt="txt")` is called
- **THEN** the save SHALL raise `ValueError` because the resolved path escapes the workspace boundary
- **AND** no file SHALL be written

### Requirement: AssetStore integrates with NodeContext

`NodeContext` SHALL optionally hold an `AssetStore` instance, enabling nodes to persist large files via `ctx.save_asset()` which calls `AssetStore.save()` and then `ctx.put_asset()` to register metadata.

#### Scenario: Node saves asset through context
- **WHEN** a node calls `ctx.save_asset(name="watertight_mesh", data=mesh_bytes, fmt="obj", metadata={"vertices": 12000})`
- **THEN** `AssetStore.save()` SHALL be called to persist the file
- **AND** `ctx.put_asset()` SHALL be called with the returned URI as `path`
- **AND** the asset SHALL appear in `ctx.to_state_diff()["assets"]`

#### Scenario: NodeContext without AssetStore falls back to put_asset
- **WHEN** `NodeContext` is created without an `AssetStore` (backward compatibility)
- **AND** a node calls `ctx.put_asset(key, path, format)` directly
- **THEN** behavior SHALL be identical to current implementation (no change)

#### Scenario: save_asset returns URI
- **WHEN** a node calls `ctx.save_asset(name="mesh", data=mesh_bytes, fmt="obj")`
- **THEN** the returned value SHALL be the URI string from `AssetStore.save()`

**Usage guidance**: `save_asset(name, data, fmt)` is for nodes that produce in-memory bytes and need persistence. `put_asset(key, path, format)` is for nodes where the file already exists on disk. Both register metadata in `AssetRegistry`.
