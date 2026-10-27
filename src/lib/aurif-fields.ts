export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export interface ResponseField { key: string; label: string; type: string; agentVisible: boolean }
export interface RequestField { key: string; label: string; agentAllowed: boolean }

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