import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Select,
  Button,
  Space,
  Typography,
  Spin,
  message,
  Descriptions,
  Tag,
} from 'antd';
import { SaveOutlined, UndoOutlined } from '@ant-design/icons';
import type { RoleConfig, ModelOption } from '../../types/llmConfig.ts';
import { getLLMConfig, updateLLMConfig } from '../../services/api.ts';

const { Text } = Typography;

/** 管道分组配置 */
const GROUP_META: Record<string, { title: string; color: string }> = {
  precision: { title: '精密建模管道', color: 'blue' },
  organic: { title: '创意雕塑管道', color: 'green' },
};

export default function ModelConfigPanel() {
  const [roles, setRoles] = useState<Record<string, RoleConfig>>({});
  const [models, setModels] = useState<ModelOption[]>([]);
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getLLMConfig();
      setRoles(data.roles);
      setModels(data.available_models);
      // 初始化选择状态
      const initial: Record<string, string> = {};
      for (const [key, cfg] of Object.entries(data.roles)) {
        initial[key] = cfg.current_model;
      }
      setSelections(initial);
    } catch {
      message.error('加载模型配置失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const resp = await updateLLMConfig(selections);
      setRoles(resp.roles);
      // 同步 selections
      const updated: Record<string, string> = {};
      for (const [key, cfg] of Object.entries(resp.roles)) {
        updated[key] = cfg.current_model;
      }
      setSelections(updated);
      message.success('模型配置已保存');
    } catch {
      message.error('保存模型配置失败');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    const initial: Record<string, string> = {};
    for (const [key, cfg] of Object.entries(roles)) {
      initial[key] = cfg.current_model;
    }
    setSelections(initial);
  };

  const hasChanges = Object.entries(selections).some(
    ([key, val]) => roles[key] && val !== roles[key].current_model,
  );

  const modelOptions = models.map((m) => ({
    label: m.display_name,
    value: m.name,
  }));

  // 按 group 分组 roles
  const grouped: Record<string, Array<[string, RoleConfig]>> = {};
  for (const [key, cfg] of Object.entries(roles)) {
    const group = cfg.group || 'other';
    if (!grouped[group]) grouped[group] = [];
    grouped[group].push([key, cfg]);
  }

  if (loading) {
    return (
      <Card title="模型配置" size="small">
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin tip="加载配置中..." />
        </div>
      </Card>
    );
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {Object.entries(grouped).map(([group, entries]) => {
        const meta = GROUP_META[group] ?? { title: group, color: 'default' };
        return (
          <Card
            key={group}
            title={
              <Space>
                <Tag color={meta.color}>{meta.title}</Tag>
              </Space>
            }
            size="small"
          >
            <Descriptions column={1} size="small" bordered>
              {entries.map(([roleKey, cfg]) => {
                const isDefault = selections[roleKey] === cfg.default_model;
                return (
                  <Descriptions.Item
                    key={roleKey}
                    label={
                      <Space>
                        <Text strong>{cfg.display_name}</Text>
                        {isDefault && (
                          <Tag color="default" style={{ fontSize: 11 }}>
                            默认
                          </Tag>
                        )}
                      </Space>
                    }
                  >
                    <Select
                      style={{ width: 320 }}
                      value={selections[roleKey]}
                      options={modelOptions}
                      onChange={(val) =>
                        setSelections((prev) => ({ ...prev, [roleKey]: val }))
                      }
                    />
                  </Descriptions.Item>
                );
              })}
            </Descriptions>
          </Card>
        );
      })}

      <Space>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          onClick={handleSave}
          loading={saving}
          disabled={!hasChanges}
        >
          保存配置
        </Button>
        <Button
          icon={<UndoOutlined />}
          onClick={handleReset}
          disabled={!hasChanges}
        >
          重置
        </Button>
      </Space>
    </Space>
  );
}
