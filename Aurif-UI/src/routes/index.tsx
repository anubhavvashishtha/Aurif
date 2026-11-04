import { createFileRoute, Link } from "@tanstack/react-router";
import { AuthCard } from "@/components/aurif/ui";
import { AuthForm } from "@/components/aurif/auth-form";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Log in — Aurif" },
      { name: "description", content: "Sign in to Aurif, the permission layer for AI agents visiting your website." },
      { property: "og:title", content: "Log in — Aurif" },
      { property: "og:description", content: "Control which AI agents can read and act on your website." },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  return (
    <AuthCard
      title="Welcome back"
      subtitle="Log in to manage AI access to your sites."
      footer={<>New to Aurif? <Link to="/signup" className="font-medium text-primary hover:underline">Create an account</Link></>}
    >
      <AuthForm mode="login" />
    </AuthCard>
  );
}
