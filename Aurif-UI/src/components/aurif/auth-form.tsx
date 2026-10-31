import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { login, signup } from "@/lib/aurif-store";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState(mode === "login" ? "owner@aurif.dev" : "");
  const [password, setPassword] = useState(mode === "login" ? "demo1234" : "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        const err = await (mode === "login" ? login : signup)(email.trim(), password);
        setBusy(false);
        if (err) return setError(err);
        navigate({ to: "/dashboard" });
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="password">Password</Label>
        <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Button type="submit" className="w-full" disabled={busy}>
        {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
      </Button>
      {mode === "login" && (
        <p className="rounded-md border border-dashed bg-card px-3 py-2 text-xs text-muted-foreground">
          Demo: <span className="font-mono text-foreground">owner@aurif.dev</span> /{" "}
          <span className="font-mono text-foreground">demo1234</span>
        </p>
      )}
    </form>
  );
}
