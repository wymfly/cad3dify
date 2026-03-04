## 1. 后端：运行时节点跳过

- [ ] 1.1 修改 `_wrap_node()` 添加 enabled 检查：在 `builder.py:108-180` 的 `wrapped()` 函数开头，检查 `state.get("pipeline_config", {}).get(node_name, {}).get("enabled", True)`，为 false 时返回 `{}` 并 log INFO
- [ ] 1.2 移除 resolver 的编译时过滤：在 `resolver.py:64-72` 中，删除 `if not node_config.get("enabled", True): continue` 逻辑，使所有节点都编译进图
- [ ] 1.3 编写测试 `test_runtime_skip`：mock 一个节点 enabled=false，验证 `_wrap_node()` 返回空 dict 且不执行策略逻辑
- [ ] 1.4 编写测试 `test_resolver_includes_disabled`：验证 `resolve_all()` 不再过滤 disabled 节点

## 2. 后端：策略可用性 API

- [ ] 2.1 在 `pipeline_config.py` 新增 `GET /pipeline/strategy-availability` 端点：遍历 registry 所有节点的 strategies，调用 `check_available()`，返回 `{node: {strategy: {available, reason}}}`
- [ ] 2.2 编写测试 `test_strategy_availability`：mock `check_available()` 返回 true/false，验证响应格式正确
- [ ] 2.3 编写测试 `test_strategy_availability_error`：mock 策略实例化抛异常，验证返回 `{available: false, reason: "..."}`

## 3. 后端：config_schema 增强

- [ ] 3.1 在 `registry.py` 增强 schema 生成逻辑：从 Pydantic Field metadata 提取 `description`、`ge/le → minimum/maximum`、`json_schema_extra` 中的 `x-group`
- [ ] 3.2 添加 `x-sensitive` 自动检测：字段名含 `api_key`/`secret`/`password` 时在 schema 中注入 `x-sensitive: true`
- [ ] 3.3 编写测试 `test_schema_generation`：创建包含各种 Field metadata 的 config_model，验证生成的 schema 包含 description/minimum/maximum/x-group/x-sensitive

## 4. 后端：confirm 端点扩展

- [ ] 4.1 在 `ConfirmRequest`（`jobs.py:113-120`）中新增 `pipeline_config_updates: dict[str, dict] | None = None` 字段
- [ ] 4.2 在 `confirm_job()` 端点（`jobs.py:579-665`）中，resume 前 deep-merge `pipeline_config_updates` 到 state 的 `pipeline_config`
- [ ] 4.3 编写测试 `test_confirm_config_merge`：通过 graph 创建 Job，HITL 确认时传入 `pipeline_config_updates`，验证 state 正确合并

## 5. 后端：旧 API 标记废弃

- [ ] 5.1 为 `GET /pipeline/presets` 和 `GET /pipeline/tooltips` 添加 `Deprecation` 和 `Sunset` 响应头

## 6. 前端：SchemaForm 组件

- [ ] 6.1 创建 `frontend/src/components/SchemaForm/index.tsx`：接收 `config_schema` + `value` + `onChange`，按 type 映射渲染控件（boolean→Switch, integer+min/max→Slider, integer→InputNumber, string+enum→Select, string→Input, x-sensitive→Password）
- [ ] 6.2 实现 `x-group` 分组渲染：按 `x-group` 值分组字段，每组一个折叠区域
- [ ] 6.3 跳过 `enabled` 和 `strategy` 字段（由 NodeConfigCard header 渲染）
- [ ] 6.4 编写组件测试：验证各类型控件正确渲染、sensitive 字段用 Password、分组正确

## 7. 前端：NodeConfigCard 重构

- [ ] 7.1 重构 `CustomPanel.tsx` 从列表改为卡片式：每个节点一张折叠卡片（Ant Design Collapse）
- [ ] 7.2 卡片 Header：`[Switch enabled] [节点名] [策略 Select]`，策略不可用时 `disabled + Tooltip`
- [ ] 7.3 卡片 Body：集成 SchemaForm（动态参数表单）+ FallbackChainTag（fallback chain 顺序展示）
- [ ] 7.4 集成策略可用性：页面加载时调用 `GET /pipeline/strategy-availability`，缓存到 state，策略 Select 中不可用选项 disabled + Tooltip 提示原因

## 8. 前端：ValidationBanner

- [ ] 8.1 创建 `frontend/src/components/PipelineConfigBar/ValidationBanner.tsx`：监听 config 变更，debounce 300ms 后调用 `POST /pipeline/validate`
- [ ] 8.2 有效时显示绿色 ✓ + 节点数 + 拓扑；无效时红色 ✗ + 错误原因
- [ ] 8.3 集成到 PipelineConfigBar 容器（`index.tsx`），放在 PresetSelector 和 CustomPanel 之间

## 9. 前端：HITL ConfirmDialog 扩展

- [ ] 9.1 在 ConfirmDialog 中添加 Collapse "高级配置" 区域，复用 NodeConfigCard（仅展示后续未执行的节点）
- [ ] 9.2 confirm 请求中包含 `pipeline_config_updates` 字段

## 10. 前端类型与 API 对齐

- [ ] 10.1 在前端类型定义中新增 `StrategyAvailability` 接口，与后端 API 响应对齐
- [ ] 10.2 在 API 调用层添加 `getStrategyAvailability()` 函数
- [ ] 10.3 `tsc --noEmit` + lint 通过

## 11. E2E 测试

- [ ] 11.1 测试：预设选择 → 创建 Job → 节点按预设参数执行
- [ ] 11.2 测试：禁用节点 → validate 显示警告 → 启用后创建成功
- [ ] 11.3 测试：自定义参数 → 创建 Job → 节点读取到修改后的参数
- [ ] 11.4 测试：策略灰化 — mock API key 缺失 → tooltip 展示原因
- [ ] 11.5 测试：HITL 中改策略 → confirm 后后续节点用新策略
