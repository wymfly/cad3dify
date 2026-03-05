## ADDED Requirements

### Requirement: SystemConfigStore 持久化

系统 SHALL 提供 `SystemConfigStore` 单例，将系统级配置参数持久化到 JSON 文件（`backend/data/system_config.json`）。

存储格式 SHALL 为按节点名分组的嵌套 dict：
```json
{
  "generate_raw_mesh": {"hunyuan3d_api_key": "sk-...", "hunyuan3d_endpoint": "https://..."},
  "mesh_healer": {"retopo_endpoint": "https://..."}
}
```

写入操作 SHALL 使用原子写入（临时文件 + `os.replace`）保证文件完整性。
读写操作 SHALL 线程安全（使用 `threading.Lock`）。

#### Scenario: 保存系统配置
- **WHEN** 调用 `SystemConfigStore.save(data)` 传入节点配置数据
- **THEN** 数据以 JSON 格式写入 `backend/data/system_config.json`

#### Scenario: 读取系统配置
- **WHEN** 调用 `SystemConfigStore.load()`
- **THEN** 返回 JSON 文件中的完整配置 dict；文件不存在时返回空 dict

#### Scenario: 原子写入保证
- **WHEN** 写入过程中发生异常
- **THEN** 原有文件内容不受影响（不会出现半写状态）

#### Scenario: 读取单节点配置
- **WHEN** 调用 `SystemConfigStore.get_node("generate_raw_mesh")`
- **THEN** 返回该节点的 system 配置 dict；节点无配置时返回空 dict

### Requirement: 系统配置 REST API

系统 SHALL 提供 3 个 REST API 端点管理系统配置：

1. `GET /api/v1/pipeline/system-config-schema` — 返回每个节点的 system scope 字段 schema
2. `GET /api/v1/pipeline/system-config` — 返回当前系统配置值
3. `PUT /api/v1/pipeline/system-config` — 保存系统配置

schema 端点 SHALL 只返回 `x-scope: "system"` 的字段 schema，按节点名分组。
PUT 端点 SHALL 校验只接受 system scope 字段，拒绝 engineering scope 字段。
PUT 端点 SHALL 使用节点的 config_model 验证字段值类型，拒绝不合法的值。
GET 端点 SHALL 对 `x-sensitive` 字段做掩码处理（如 `"sk-****1234"`），不返回原始密钥值。

#### Scenario: 获取系统配置 schema
- **WHEN** 调用 `GET /api/v1/pipeline/system-config-schema`
- **THEN** 返回 `{node_name: {properties: {...system_fields_only...}}}` 格式，不包含 engineering 字段

#### Scenario: 获取当前系统配置（含掩码）
- **WHEN** 调用 `GET /api/v1/pipeline/system-config`
- **THEN** 返回当前系统配置值，其中 x-sensitive 字段的值做掩码处理（如 `"sk-****1234"`）

#### Scenario: PUT 类型校验
- **WHEN** 调用 `PUT /api/v1/pipeline/system-config` 传入 `{"generate_raw_mesh": {"timeout": "not_a_number"}}`
- **THEN** 返回 400 错误，因为 timeout 不是 system 字段
- **AND** 即使字段属于 system scope，值类型不匹配也返回 422 验证错误

#### Scenario: 保存系统配置
- **WHEN** 调用 `PUT /api/v1/pipeline/system-config` 传入合法配置
- **THEN** 配置保存到 system_config.json，返回 200

#### Scenario: 拒绝非 system 字段
- **WHEN** 调用 `PUT /api/v1/pipeline/system-config` 传入包含 engineering 字段（如 timeout）的数据
- **THEN** 返回 400 错误，拒绝保存

### Requirement: NodeContext 运行时合并

`NodeContext.from_state()` SHALL 在构建节点 config 对象前，合并系统配置作为 defaults。

配置合并优先级 SHALL 为：Pydantic model default < system_config.json < per-request pipeline_config。

合并对节点实现 SHALL 完全透明——节点代码不需要感知系统配置的存在。

#### Scenario: 系统配置提供默认值
- **WHEN** system_config.json 中 generate_raw_mesh 配置了 `hunyuan3d_api_key`
- **AND** per-request pipeline_config 未指定该字段
- **THEN** NodeContext 使用 system_config.json 中的 api_key 值

#### Scenario: per-request 覆盖系统配置
- **WHEN** system_config.json 中 generate_raw_mesh 配置了 `hunyuan3d_endpoint: "https://a"`
- **AND** per-request pipeline_config 指定 `hunyuan3d_endpoint: "https://b"`
- **THEN** NodeContext 使用 per-request 的值 `"https://b"`

#### Scenario: 无系统配置时正常运行
- **WHEN** system_config.json 不存在或为空
- **THEN** NodeContext 行为与当前完全一致（仅使用 Pydantic default + per-request config）
