import { createFileRoute, Link } from "@tanstack/react-router";
import { AuthCard } from "@/components/aurif/ui";
import { AuthForm } from "@/components/aurif/auth-form";

export const Route = createFileRoute("/signup")({
  head: () => ({
    meta: [
      { title: "Sign up — Aurif" },
      { name: "description", content: "Create an Aurif account and start controlling AI agent access to your site." },
      { property: "og:title", content: "Sign up — Aurif" },
      { property: "og:description", content: "Create an Aurif account for AI access control." },
    ],
  }),
  component: () => (
    <AuthCard
      title="Create your account"
      subtitle="Install Aurif on your site, then decide what agents can see."
      footer={<>Already have an account? <Link to="/" className="font-medium text-primary hover:underline">Log in</Link></>}
    >
      <AuthForm mode="signup" />
    </AuthCard>
  ),
});
