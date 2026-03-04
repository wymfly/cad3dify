import { Switch, Slider, InputNumber, Select, Input, Typography, Divider } from 'antd';

const { Text } = Typography;

interface JsonSchemaProperty {
  type?: string;
  anyOf?: Array<{ type?: string }>;
  description?: string;
  minimum?: number;
  maximum?: number;
  enum?: string[];
  default?: unknown;
  'x-sensitive'?: boolean;
  'x-group'?: string;
  'x-scope'?: string;
}

interface SchemaFormProps {
  schema: {
    properties?: Record<string, JsonSchemaProperty>;
    [key: string]: unknown;
  };
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  scope?: 'engineering' | 'system' | 'all';
}

/** Fields handled by NodeConfigCard header — skip in SchemaForm */
const SKIP_FIELDS = new Set(['enabled', 'strategy']);

/** Convert snake_case to human-readable label */
function humanize(name: string): string {
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Resolve Pydantic v2 anyOf types (e.g. str | None → "string") */
function resolveType(prop: JsonSchemaProperty): string | undefined {
  if (prop.type) return prop.type;
  if (prop.anyOf) {
    const types = prop.anyOf.map((s) => s.type).filter((t) => t && t !== 'null');
    return types[0];
  }
  return undefined;
}

function renderField(
  name: string,
  prop: JsonSchemaProperty,
  value: unknown,
  onChange: (val: unknown) => void,
) {
  // Sensitive → Password
  if (prop['x-sensitive']) {
    return (
      <Input.Password
        value={(value as string) ?? (prop.default as string) ?? ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={prop.description ?? humanize(name)}
        size="small"
      />
    );
  }

  const type = resolveType(prop);

  // Boolean → Switch
  if (type === 'boolean') {
    return (
      <Switch
        size="small"
        checked={(value as boolean) ?? (prop.default as boolean) ?? false}
        onChange={onChange}
      />
    );
  }

  // Integer/Number with min+max → Slider
  if ((type === 'integer' || type === 'number') &&
      prop.minimum != null && prop.maximum != null) {
    return (
      <Slider
        min={prop.minimum}
        max={prop.maximum}
        step={type === 'number' ? (prop.maximum! - prop.minimum!) / 100 : 1}
        value={(value as number) ?? (prop.default as number) ?? prop.minimum}
        onChange={onChange}
      />
    );
  }

  // Integer/Number without range → InputNumber
  if (type === 'integer' || type === 'number') {
    return (
      <InputNumber
        size="small"
        value={(value as number) ?? (prop.default as number)}
        onChange={(val) => onChange(val)}
        min={prop.minimum}
        max={prop.maximum}
        style={{ width: '100%' }}
      />
    );
  }

  // String with enum → Select
  if (type === 'string' && prop.enum) {
    return (
      <Select
        size="small"
        value={(value as string) ?? (prop.default as string) ?? prop.enum[0]}
        onChange={onChange}
        options={prop.enum.map((e) => ({ label: humanize(e), value: e }))}
        style={{ width: '100%' }}
      />
    );
  }

  // String without enum → Input
  if (type === 'string') {
    return (
      <Input
        size="small"
        value={(value as string) ?? (prop.default as string) ?? ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={prop.description ?? humanize(name)}
      />
    );
  }

  // Unsupported (object, array, null, etc.) → placeholder
  if (value == null && prop.default == null) {
    return <Text type="secondary" style={{ fontSize: 11, fontStyle: 'italic' }}>未设置</Text>;
  }

  return (
    <Text type="secondary" style={{ fontSize: 11 }}>
      {JSON.stringify(value ?? prop.default)}
    </Text>
  );
}

export default function SchemaForm({ schema, value, onChange, scope = 'engineering' }: SchemaFormProps) {
  const properties = schema.properties ?? {};
  const requiredFields = new Set((schema.required as string[] | undefined) ?? []);

  const fields = Object.entries(properties).filter(([name, prop]) => {
    if (SKIP_FIELDS.has(name)) return false;
    if (scope === 'all') return true;
    const fieldScope = prop['x-scope'] ?? 'engineering';
    return fieldScope === scope;
  });

  // Group by x-group
  const groups: Record<string, [string, JsonSchemaProperty][]> = {};
  for (const entry of fields) {
    const group = entry[1]['x-group'] ?? '_default';
    if (!groups[group]) groups[group] = [];
    groups[group].push(entry);
  }

  const handleChange = (fieldName: string, fieldValue: unknown) => {
    onChange({ ...value, [fieldName]: fieldValue });
  };

  if (fields.length === 0) return null;

  return (
    <div style={{ padding: '4px 0' }}>
      {Object.entries(groups).map(([group, groupFields]) => (
        <div key={group}>
          {group !== '_default' && (
            <Divider orientation="left" plain style={{ margin: '4px 0', fontSize: 11 }}>
              {group}
            </Divider>
          )}
          {groupFields.map(([name, prop]) => (
            <div key={name} style={{ marginBottom: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <Text type="secondary" style={{ fontSize: 11, flex: '0 0 auto' }}>
                  {requiredFields.has(name) && <span style={{ color: '#ff4d4f', marginRight: 2 }}>*</span>}
                  {prop.description ?? humanize(name)}
                </Text>
                <div style={{ flex: 1, maxWidth: 180 }}>
                  {renderField(name, prop, value[name], (v) => handleChange(name, v))}
                </div>
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
