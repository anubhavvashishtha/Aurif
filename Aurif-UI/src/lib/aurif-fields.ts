export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export interface ResponseField { key: string; label: string; type: string; agentVisible: boolean }
export interface RequestField { key: string; label: string; agentAllowed: boolean }

export type FieldTreeNode = {
  segment: string;
  key: string;
  label: string;
  type: string;
  agentVisible: boolean;
  children: FieldTreeNode[];
};

/** Build a nested tree from dotted response field keys (`meta.price`, `meta.products[].name`). */
export function buildFieldTree(fields: ResponseField[]): FieldTreeNode[] {
  const roots: FieldTreeNode[] = [];
  const byKey = new Map<string, FieldTreeNode>();
  const fieldByKey = new Map(fields.map((f) => [f.key, f]));

  for (const f of fields) {
    const parts = f.key.split(".");
    let parentPath = "";
    let siblings = roots;
    for (let i = 0; i < parts.length; i++) {
      const segment = parts[i]!;
      const path = parentPath ? `${parentPath}.${segment}` : segment;
      let node = byKey.get(path);
      if (!node) {
        const own = fieldByKey.get(path);
        node = {
          segment,
          key: path,
          label: own?.label ?? segment.replace("[]", ""),
          type: own?.type ?? (i < parts.length - 1 ? "object" : f.type),
          agentVisible: own?.agentVisible ?? true,
          children: [],
        };
        byKey.set(path, node);
        siblings.push(node);
      }
      if (path === f.key) {
        node.type = f.type;
        node.label = f.label;
        node.agentVisible = f.agentVisible;
      }
      siblings = node.children;
      parentPath = path;
    }
  }
  return roots;
}

/** Every expandable key — used so nested schema differences are visible by default. */
export function collectExpandableKeys(nodes: FieldTreeNode[]): string[] {
  const keys: string[] = [];
  const walk = (list: FieldTreeNode[]) => {
    for (const n of list) {
      if (n.children.length) {
        keys.push(n.key);
        walk(n.children);
      }
    }
  };
  walk(nodes);
  return keys;
}

// Apply dotted paths and [] array paths without mutating the owner payload.
function omitPath(value: JsonValue, parts: string[]): void {
  if (!value || typeof value !== "object" || Array.isArray(value)) return;
  const [part, ...rest] = parts;
  if (!part) return;
  const array = part.endsWith("[]");
  const key = array ? part.slice(0, -2) : part;
  if (!rest.length) { delete value[key]; return; }
  const child = value[key];
  if (array && Array.isArray(child)) child.forEach((item) => omitPath(item, rest));
  else if (child !== undefined) omitPath(child, rest);
}

export function redactResponse(payload: JsonValue, fields: ResponseField[]): JsonValue {
  const result: JsonValue = JSON.parse(JSON.stringify(payload));
  fields.filter((f) => !f.agentVisible).forEach((f) => omitPath(result, f.key.split(".")));
  return result;
}

export function filterRequest(payload: JsonValue, fields: RequestField[]): JsonValue {
  return redactResponse(payload, fields.map((f) => ({ ...f, type: "", agentVisible: f.agentAllowed })));
}

export function agentResponse(endpoint: { agentAccess: boolean; responseFields: ResponseField[] }, payload: JsonValue) {
  return endpoint.agentAccess
    ? { status: 200, body: redactResponse(payload, endpoint.responseFields) }
    : { status: 403, body: { error: "agent_access_off" } };
}