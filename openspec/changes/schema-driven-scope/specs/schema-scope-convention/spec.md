## ADDED Requirements

### Requirement: x-scope JSON Schema extension

每个节点的 config_model 字段 SHALL 支持 `x-scope` JSON Schema 扩展标记，值为 `"system"` 或 `"engineering"`。未标注的字段默认视为 `"engineering"`。

标注方式 SHALL 使用 Pydantic Field 的 `json_schema_extra` 参数，与已有的 `x-sensitive` 模式一致：
```python
field_name: type = Field(default=..., json_schema_extra={"x-scope": "system"})
```

对于已有 `x-sensitive` 的字段，SHALL 合并到同一个 dict：
```python
api_key: str | None = Field(default=None, json_schema_extra={"x-sensitive": True, "x-scope": "system"})
```

#### Scenario: 字段显式标注 x-scope=system
- **WHEN** config model 字段声明 `json_schema_extra={"x-scope": "system"}`
- **THEN** `config_schema` 的对应 property 中包含 `"x-scope": "system"`

#### Scenario: 字段未标注 x-scope
- **WHEN** config model 字段未声明 x-scope
- **THEN** `config_schema` 的对应 property 中不包含 `x-scope` 键，前端视为 engineering

#### Scenario: x-sensitive 与 x-scope 合并
- **WHEN** 字段声明 `json_schema_extra={"x-sensitive": True, "x-scope": "system"}`
- **THEN** `config_schema` 中该 property 同时包含 `"x-sensitive": true` 和 `"x-scope": "system"`

### Requirement: enhance_config_schema 自动推断安全网

`enhance_config_schema()` SHALL 对未显式标注 x-scope 的字段自动推断：

1. 已包含 `x-sensitive: true` 的字段 → 自动添加 `x-scope: "system"`
2. 字段名匹配 `_endpoint$` 的字段 → 自动添加 `x-scope: "system"`
3. 字段名精确匹配 `prusaslicer_path` 或 `orcaslicer_path` 的字段 → 自动添加 `x-scope: "system"`
4. 字段名为 `neural_enabled` 的字段 → 自动添加 `x-scope: "system"`

> 注：不使用宽泛的 `_path$` 匹配，避免误标未来的工程路径参数。`health_check_path` 由显式标注覆盖。

已显式标注 x-scope 的字段 SHALL NOT 被自动推断覆盖。

#### Scenario: x-sensitive 字段自动获得 system scope
- **WHEN** 字段包含 `x-sensitive: true` 且未显式标注 x-scope
- **THEN** enhance_config_schema 自动添加 `x-scope: "system"`

#### Scenario: endpoint 字段自动推断
- **WHEN** 字段名以 `_endpoint` 结尾且未显式标注 x-scope
- **THEN** enhance_config_schema 自动添加 `x-scope: "system"`

#### Scenario: CLI path 字段自动推断
- **WHEN** 字段名为 `prusaslicer_path` 或 `orcaslicer_path` 且未显式标注 x-scope
- **THEN** enhance_config_schema 自动添加 `x-scope: "system"`

#### Scenario: 非 CLI path 字段不被自动推断
- **WHEN** 字段名为 `health_check_path` 且已显式标注 `x-scope: "system"`
- **THEN** enhance_config_schema 保留显式标注，不依赖自动推断

#### Scenario: 显式标注不被覆盖
- **WHEN** 字段显式标注 `x-scope: "engineering"` 且字段名以 `_path` 结尾
- **THEN** enhance_config_schema 保留显式标注 `x-scope: "engineering"`，不覆盖为 system

### Requirement: 现有节点 system 字段标注

以下节点的 config model 中指定字段 SHALL 标注 `x-scope: "system"`：

- **generate_raw_mesh**: `hunyuan3d_api_key`, `hunyuan3d_endpoint`, `tripo3d_api_key`, `spar3d_endpoint`, `trellis_endpoint`
- **neural (base)**: `neural_enabled`, `neural_endpoint`, `health_check_path`
- **mesh_healer**: `retopo_endpoint`
- **slice_to_gcode**: `prusaslicer_path`, `orcaslicer_path`

其余字段（timeout, output_format, voxel_resolution, layer_height, fill_density 等）SHALL NOT 标注 x-scope，默认作为 engineering 参数。

#### Scenario: generate_raw_mesh 的 API key 是 system scope
- **WHEN** 查询 generate_raw_mesh 节点的 config_schema
- **THEN** `hunyuan3d_api_key` property 包含 `"x-scope": "system"` 和 `"x-sensitive": true`

#### Scenario: generate_raw_mesh 的 timeout 是 engineering scope
- **WHEN** 查询 generate_raw_mesh 节点的 config_schema
- **THEN** `timeout` property 不包含 `x-scope` 键
