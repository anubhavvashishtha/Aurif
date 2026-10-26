import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Panel, ToggleRow } from "@/components/aurif/ui";
import { toggleEndpoint, useActiveSite } from "@/lib/aurif-store";

export const Route = createFileRoute("/dashboard/endpoints")({ component: Endpoints });

function Endpoints() {
  const site = useActiveSite();
  const groups = [
    { title: "Pages", items: site.endpoints.filter((e) => e.kind === "page") },
    { title: "Actions", items: site.endpoints.filter((e) => e.kind === "action") },
  ];
  return (
    <>
      <PageHeader
        title="Endpoint control"
        description="Off = agents get blocked (403) and cannot read that output. Humans are unaffected."
      />
      <div className="space-y-6">
        {groups.map((g) => g.items.length > 0 && (
          <section key={g.title}>
            <h2 className="mb-2 text-lg text-ink">{g.title}</h2>
            <Panel className="divide-y">
              {g.items.map((e) => (
                <ToggleRow key={e.id} label={e.label} kind={e.kind} refId={e.ref} checked={e.agentAccess}
                  onChange={(v) => toggleEndpoint(site.id, e.id, v)} />
              ))}
            </Panel>
          </section>
        ))}
      </div>
    </>
  );
}
