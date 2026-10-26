# Aurif product north star

**Status:** Locked pitch — do not dilute this framing without an explicit product decision.

## One-liner

Permissioned AI browsing for the open web.

## Pitch

We’re building an AI access layer for the web — a plugin websites install so AI agents can identify themselves, get permissioned access, and navigate the site through a controlled, machine-friendly interface instead of being blocked or scraping blindly.

Think Google Docs sharing, but for websites and AI agents: the site knows it’s talking to an AI, decides what that AI can view or do, and exposes structured paths (APIs, action endpoints, simplified layouts) so the agent can complete tasks for the user safely. Sites keep control over data and actions; users stop hitting “your AI got blocked”; attack surface shrinks because AI traffic is authenticated and scoped instead of anonymous and adversarial.

## Elevator

Sites plug us in. AI agents declare themselves and request access. We verify identity, apply the site’s AI policy (view / act / limited data), and route the agent through AI-friendly surfaces — endpoints and action hooks — so agents help users without unrestricted scraping or brittle UI automation.

## Analogy

Someone opens your Google Doc and requests view/edit access. You grant a role. They work inside the rules you set. Same idea for websites and AI agents.

## Flow

1. An AI agent arrives at a site with Aurif installed.
2. It identifies itself and plugs in (handshake / credentials / agent identity).
3. The website knows this visitor is an AI, not a human.
4. Instead of blocking, the site grants a controlled AI mode: machine-readable structure, dedicated endpoints, clearer actions.
5. The site controls what data and actions the AI can use.

## Positioning

| Adjacent idea | Difference |
|---------------|------------|
| robots.txt / bot blocking | Those say stay out. Aurif says come in with a badge. |
| CAPTCHA | Assumes AI is the enemy. Aurif treats AI as a new client type. |
| Public APIs alone | APIs help developers. Aurif is a runtime access + discovery protocol for agents. |
| Cloudflare-style AI bot labels | Labels are mostly detect/block/allow. Aurif adds permissioned interaction and an AI-native path. |

## Product layers

| Layer | Role |
|-------|------|
| Site SDK / script | Handshake AI traffic; advertise AI capabilities |
| Agent identity | Who is this agent (vendor, session, user consent)? |
| Access policy | View vs act; which pages/data/actions; rate limits |
| AI surface | Dedicated endpoints, action schema, optional simplified UI |
| Audit | Log what the AI saw and did |
