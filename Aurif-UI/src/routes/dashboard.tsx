import { createFileRoute, Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { ModelStatusBanner } from "@/components/aurif/model-status-banner";
import { SideNav, Topbar } from "@/components/aurif/ui";
import { bootstrap, useAurif } from "@/lib/aurif-store";

export const Route = createFileRoute("/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — Aurif" },
      { name: "description", content: "Monitor AI agents, control endpoints and manage site credentials." },
      { property: "og:title", content: "Dashboard — Aurif" },
      { property: "og:description", content: "Aurif owner dashboard for AI access control." },
    ],
  }),
  ssr: false,
  component: DashboardLayout,
});

function DashboardLayout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const user = useAurif((s) => s.user);
  const ready = useAurif((s) => s.ready);
  useEffect(() => {
    void bootstrap();
  }, []);
  useEffect(() => {
    if (ready && !user) navigate({ to: "/", replace: true });
  }, [navigate, ready, user]);
  if (!ready || !user) {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Loading…</div>;
  }
  return (
    <div className="min-h-screen bg-background bg-wash">
      <Topbar />
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 md:flex-row md:gap-10 md:px-6 md:py-10">
        <SideNav />
        <main key={pathname} className="animate-rise min-w-0 flex-1">
          <ModelStatusBanner />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
