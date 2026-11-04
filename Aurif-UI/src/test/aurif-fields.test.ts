import { describe, expect, it } from "vitest";
import { agentResponse, filterRequest } from "@/lib/aurif-fields";

describe("Aurif field rules", () => {
  it("omits hidden price from agent JSON", () => {
    const body = agentResponse({ agentAccess: true, responseFields: [{ key: "meta.price", label: "", type: "number", agentVisible: false }] }, { meta: { name: "Tote", price: 48 } }).body;
    expect(body).toEqual({ meta: { name: "Tote" } });
  });
  it("blocks a disabled endpoint with 403", () => {
    expect(agentResponse({ agentAccess: false, responseFields: [] }, { title: "Home" })).toEqual({ status: 403, body: { error: "agent_access_off" } });
  });
  it("ignores disallowed request fields", () => {
    expect(filterRequest({ quantity: 1, email: "a@b.co" }, [{ key: "email", label: "", agentAllowed: false }])).toEqual({ quantity: 1 });
  });
});