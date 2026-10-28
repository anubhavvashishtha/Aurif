import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Switch } from "@/components/ui/switch";
import { PageHeader, Panel } from "@/components/aurif/ui";
import { rotateKey, updateSite, useActiveSite } from "@/lib/aurif-store";
import { aurifHead } from "@/lib/aurif-meta";

export const Route = createFileRoute("/dashboard/credentials")({ head: () => aurifHead("Site credentials", "Manage site details, welcome message, blocked agents and site key."), component: Credentials });

function Credentials() {
  const site = useActiveSite();
  const [form, setForm] = useState({
    name: "",
    url: "",
    welcome: "",
    blockedAgents: "",
    blockAnonymousAgents: true,
    requireHumanCaptcha: true,
  });
  useEffect(() => {
    setForm({
      name: site.name,
      url: site.url,
      welcome: site.welcome,
      blockedAgents: site.blockedAgents,
      blockAnonymousAgents: site.blockAnonymousAgents,
      requireHumanCaptcha: site.requireHumanCaptcha,
    });
  }, [site.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const f = (k: "name" | "url" | "welcome" | "blockedAgents") => ({
    value: form[k],
    onChange: (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value }),
  });

  return (
    <>
      <PageHeader title="Site credentials" description="Changing the welcome message changes what agents see in AI page summaries." />
      <Panel className="space-y-5 p-5">
        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-1.5"><Label>Site name</Label><Input {...f("name")} /></div>
          <div className="space-y-1.5"><Label>Site URL</Label><Input {...f("url")} /></div>
        </div>
        <div className="space-y-1.5"><Label>Agent welcome message</Label><Textarea rows={3} {...f("welcome")} /></div>
        <div className="space-y-1.5">
          <Label>Blocked agent IDs</Label>
          <Input className="font-mono text-xs" placeholder="agent-a/1.0, agent-b/2.1" {...f("blockedAgents")} />
          <p className="text-xs text-muted-foreground">Comma-separated. These agents are denied at handshake.</p>
        </div>
        <div className="flex items-start justify-between gap-4 rounded-lg border p-4">
          <div>
            <Label>Block anonymous AI scrapers</Label>
            <p className="mt-1 text-xs text-muted-foreground">
              When on, curl / Playwright / bot user-agents hitting the customer site or product API get 403.
              They must use Aurif handshake + <code className="font-mono">/ai/*</code>.
            </p>
          </div>
          <Switch
            checked={form.blockAnonymousAgents}
            onCheckedChange={(v) => setForm({ ...form, blockAnonymousAgents: v })}
            aria-label="Block anonymous AI scrapers"
          />
        </div>
        <div className="flex items-start justify-between gap-4 rounded-lg border p-4">
          <div>
            <Label>Require human CAPTCHA on storefront</Label>
            <p className="mt-1 text-xs text-muted-foreground">
              Humans draw letters/numbers on a pad (vision-checked). Agents use Aurif endpoints instead.
            </p>
          </div>
          <Switch
            checked={form.requireHumanCaptcha}
            onCheckedChange={(v) => setForm({ ...form, requireHumanCaptcha: v })}
            aria-label="Require human CAPTCHA on storefront"
          />
        </div>
        <div className="flex justify-end">
          <Button
            onClick={async () => {
              await updateSite(site.id, form);
              toast.success("Changes saved");
            }}
          >
            Save changes
          </Button>
        </div>
      </Panel>

      <Panel className="mt-6 p-5">
        <Label>Site key</Label>
        <div className="mt-1.5 flex flex-wrap items-center gap-3">
          <code className="flex-1 truncate rounded-md border bg-muted px-3 py-2 font-mono text-xs">{site.siteKey}</code>
          <AlertDialog>
            <AlertDialogTrigger asChild><Button variant="destructive">Rotate site key</Button></AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Rotate site key?</AlertDialogTitle>
                <AlertDialogDescription>Agents sending the old key will be rejected immediately. This cannot be undone.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={async () => {
                    await rotateKey(site.id);
                    toast.success("Site key rotated");
                  }}
                >
                  Rotate key
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">Rotating the key rejects agents sending the old key.</p>
      </Panel>
    </>
  );
}
