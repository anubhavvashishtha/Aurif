"""Muse as a normal browsing/scraping agent — returns step-by-step JSON for the dashboard."""

from __future__ import annotations

import base64
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

import config
import muse_client


def api_base() -> str:
    """Origin for Muse's own API calls. Local default is http://127.0.0.1:8787."""
    return config.api_public_url()


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.title = ""
        self._in_title = False
        self.chunks: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript"):
            self._skip += 1
        if t == "title":
            self._in_title = True
        if t == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if t == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join((data or "").split())
        if not text:
            return
        if self._in_title and not self.title:
            self.title = text
        if self._skip:
            return
        self.chunks.append(text)


def agent_headers(
    *,
    human_token: str | None = None,
    site_key: str | None = None,
    session: str | None = None,
) -> dict[str, str]:
    headers = {
        "User-Agent": "MuseBot/1.0 (+https://example.local/bot)",
        "X-Demo-As-Agent": "1",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }
    if human_token:
        headers["X-Aurif-Human"] = human_token
        headers["Cookie"] = f"aurif_human={human_token}"
    if site_key:
        headers["X-Aurif-Site-Key"] = site_key
    if session:
        headers["X-Aurif-Session"] = session
    return headers


def _request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 12.0,
) -> tuple[int, dict[str, str], str]:
    data = None
    req_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
            return int(res.status), {k.lower(): v for k, v in res.headers.items()}, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return int(e.code), {k.lower(): v for k, v in e.headers.items()}, raw
    except Exception as e:
        return 0, {}, str(e)


def _json_body(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return None


def parse_page(html: str, *, limit: int = 1200) -> dict[str, Any]:
    parser = _PageParser()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    body = re.sub(r"\s+", " ", " ".join(parser.chunks)).strip()
    if len(body) > limit:
        body = body[: limit - 1].rstrip() + "…"
    return {"title": parser.title, "text": body, "links": parser.links[:40]}


def make_captcha_drawing(target: str) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        tiny = base64.b64encode(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        ).decode()
        return f"data:image/png;base64,{tiny}"

    img = Image.new("RGB", (420, 180), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((8, 8, 411, 171), outline=(210, 210, 210), width=2)
    text = (target or "?").strip().upper() or "?"
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((48, 64), text, fill=(20, 20, 20), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def shop_path_from_message(message: str, products: dict[str, dict[str, Any]]) -> str:
    url_match = re.search(r"https?://\S+", message)
    if url_match:
        raw = url_match.group(0).rstrip(".,)")
        path = re.sub(r"^https?://[^/]+", "", raw) or "/"
        if not path.startswith("/"):
            path = "/" + path
        return path.split("?")[0] or "/"
    path_match = re.search(r"(?:^|\s)(/[A-Za-z0-9_./-]*)", message)
    if path_match:
        return path_match.group(1).rstrip("/") or "/"
    lowered = message.lower()
    best_slug = ""
    best_len = 0
    for slug, product in products.items():
        candidates = {slug.replace("-", " "), str(product.get("name") or "").lower()}
        for name in candidates:
            if name and name in lowered and len(name) > best_len:
                best_slug = slug
                best_len = len(name)
    if best_slug:
        return f"/products/{best_slug}"
    for guess, token in (("/shop", "shop"), ("/shop", "product"), ("/cart", "cart"), ("/", "home")):
        if token in lowered:
            return guess
    return "/"


def _absolute(url: str, base: str) -> str:
    return urllib.parse.urljoin(base if base.endswith("/") else base + "/", url)


def _summarize_fetch(status: int, body: str, content_type: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"status": status}
    if "json" in (content_type or "") or (body or "").lstrip().startswith(("{", "[")):
        parsed = _json_body(body)
        if parsed is not None:
            out["json"] = parsed
            return out
    page = parse_page(body)
    out["title"] = page.get("title")
    out["text"] = (page.get("text") or "")[:700]
    out["links"] = page.get("links") or []
    return out


def _step(n: int, action: str, *, result: str, detail: str = "", **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"step": n, "action": action, "result": result}
    if detail:
        row["detail"] = detail
    for k, v in extra.items():
        if v is not None and v != "":
            row[k] = v
    return row


def _fields_from_product(product: dict[str, Any]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    for key in ("name", "title", "summary", "price", "compare_at", "rating", "sku", "highlights"):
        val = product.get(key)
        if val is None or val == "":
            continue
        fields.append({"label": key.replace("_", " ").capitalize(), "value": str(val)})
    return fields


def _try_captcha() -> dict[str, Any]:
    """Attempt human verification like a bot. Returns passed/token/steps/agent_access."""
    out: dict[str, Any] = {"passed": False, "human_token": None, "steps": [], "agent_access": None}
    gate_status, _, gate_raw = _request(f"{api_base()}/api/public/gate", headers=agent_headers())
    gate = _json_body(gate_raw) if gate_status else {}
    if isinstance(gate, dict) and gate.get("require_human_captcha") is False:
        out["passed"] = True
        out["steps"].append(
            {"action": "check_captcha_required", "result": "skipped", "detail": "Human CAPTCHA is off"}
        )
        return out

    ch_status, _, ch_raw = _request(f"{api_base()}/api/public/human-challenge", headers=agent_headers())
    challenge = _json_body(ch_raw) if ch_status else {}
    if not isinstance(challenge, dict):
        out["steps"].append({"action": "fetch_captcha", "result": "failed", "detail": "No challenge returned"})
        return out
    if challenge.get("required") is False:
        out["passed"] = True
        out["steps"].append({"action": "fetch_captcha", "result": "skipped", "detail": "Challenge not required"})
        return out

    target = str(challenge.get("target") or "")
    prompt = str(challenge.get("prompt") or f'Draw "{target}"')
    if not (target or challenge.get("challenge_id")):
        out["steps"].append({"action": "fetch_captcha", "result": "failed", "detail": "Empty challenge"})
        return out

    out["steps"].append(
        {
            "action": "fetch_captcha",
            "result": "shown",
            "detail": prompt,
            "target": target,
            "challenge_id": challenge.get("challenge_id"),
        }
    )

    wrong = "X" if target.upper() != "X" else "Y"
    drawing = make_captcha_drawing(wrong)
    v_status, _, v_raw = _request(
        f"{api_base()}/api/public/human-verify",
        method="POST",
        headers=agent_headers(),
        body={"challenge_id": challenge.get("challenge_id"), "image": drawing},
    )
    verdict = _json_body(v_raw) if isinstance(_json_body(v_raw), dict) else {}
    if not isinstance(verdict, dict):
        verdict = {}

    if v_status == 200 and verdict.get("ok"):
        # Still treat as failed human proof for bot-rendered drawings.
        out["steps"].append(
            {
                "action": "solve_captcha",
                "result": "rejected",
                "detail": "Bot drawing was not accepted as human",
                "drew": wrong,
                "asked_for": target,
            }
        )
    else:
        out["steps"].append(
            {
                "action": "solve_captcha",
                "result": "rejected",
                "detail": str(verdict.get("error") or verdict.get("reason") or "drawing rejected"),
                "drew": wrong,
                "asked_for": target,
                "verdict": {
                    "match": verdict.get("match"),
                    "human_like": verdict.get("human_like"),
                    "read_as": verdict.get("read_as"),
                },
            }
        )

    hint = verdict.get("agent_access") if isinstance(verdict.get("agent_access"), dict) else None
    if hint:
        out["agent_access"] = hint
        out["steps"].append(
            {
                "action": "agent_access_modal",
                "result": "shown",
                "detail": hint.get("message") or "Use API with site key",
                "api_steps": hint.get("steps") or [],
            }
        )
    else:
        out["steps"].append(
            {
                "action": "agent_access_modal",
                "result": "shown",
                "detail": "To access as an agent, call the API with the required site key",
            }
        )
    return out


def browse_as_agent(
    *,
    site: dict[str, Any],
    path: str,
    products: dict[str, dict[str, Any]],
    message: str,
    site_key: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Browse/scrape like a normal agent and return structured steps for the dashboard."""
    base = (site.get("url") or config.customer_site_url()).rstrip("/")
    # Older seeds stored the API origin in the site URL. Send Muse to the storefront.
    if ":8787" in base or base == config.api_public_url().rstrip("/"):
        base = config.customer_site_url()
    target_url = f"{base}{path if path.startswith('/') else '/' + path}"
    site_key = (site_key or "").strip() or None
    model_info = muse_client.resolve_model(model)
    if provider:
        model_info["provider"] = provider

    steps: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    fields: list[dict[str, str]] = []
    denied = False
    n = 0

    def add(action: str, *, result: str, detail: str = "", **extra: Any) -> None:
        nonlocal n
        n += 1
        steps.append(_step(n, action, result=result, detail=detail, **extra))

    add(
        "open_url",
        result="started",
        detail=f"Opening {target_url}",
        url=target_url,
        site_key_used=bool(site_key),
        model=model_info.get("id"),
        provider=model_info.get("provider"),
    )

    headers = agent_headers(site_key=site_key)
    status, resp_headers, body = _request(target_url, headers=headers)
    summary = _summarize_fetch(status, body, resp_headers.get("content-type", ""))
    findings.append({"url": target_url, **summary})

    blocked = (
        status == 403
        or resp_headers.get("x-aurif-gate") == "anonymous_agent_blocked"
        or "Automated agents are blocked" in (body or "")
        or "anonymous_agent_blocked" in (body or "")
    )
    page_ok = False
    if status == 0:
        denied = True
        add("open_url", result="failed", detail="Could not reach the page", status=status)
    elif blocked:
        denied = True
        add(
            "open_url",
            result="blocked",
            detail="Storefront blocked automated access",
            status=status,
            saw=(summary.get("text") or "")[:240],
        )
    else:
        page_ok = True
        title = summary.get("title") or ""
        text = summary.get("text") or ""
        if title:
            fields.append({"label": "Title", "value": title})
        add(
            "open_url",
            result="ok",
            detail="Page HTML loaded",
            status=status,
            title=title or None,
            saw=(text or "")[:420] or None,
        )

    captcha = _try_captcha()
    for raw_step in captcha.get("steps") or []:
        n += 1
        steps.append({"step": n, **raw_step})
    captcha_passed = bool(captcha.get("passed"))
    human_token = captcha.get("human_token")
    if not captcha_passed:
        denied = True

    # Continue only if site key is on, or UI+captcha both succeeded.
    can_continue = bool(site_key) or (page_ok and captcha_passed)
    if not captcha_passed and not site_key:
        can_continue = False
        add("stop", result="stopped", detail="No site key enabled — stopped after CAPTCHA / storefront block")

    session_token: str | None = None
    if can_continue:
        if site_key and not captcha_passed:
            add(
                "switch_to_api",
                result="started",
                detail="Site key is on — trying credentialed API after failed human check",
            )
            actions = [
                {"method": "GET", "url": f"{api_base()}/ai/help", "use_site_key": False},
                {
                    "method": "POST",
                    "url": f"{api_base()}/ai/handshake",
                    "use_site_key": True,
                    "body": {
                        "purpose": message[:240],
                        "requested_scopes": ["view"],
                        "site_key": site_key,
                    },
                },
                {
                    "method": "GET",
                    "url": f"{api_base()}/ai/page?path={urllib.parse.quote(path)}",
                    "use_site_key": True,
                },
            ]
        else:
            add("follow_up", result="started", detail="Trying follow-up fetches for product data")
            actions = [
                {"method": "GET", "url": f"{api_base()}/api/products", "use_site_key": bool(site_key)},
            ]

        for action in actions:
            url = str(action.get("url") or "").strip()
            if not url:
                continue
            if url.startswith("/"):
                if url.startswith("/api") or url.startswith("/ai") or url.startswith("/.well-known"):
                    url = _absolute(url, api_base())
                else:
                    url = _absolute(url, base)
            method = str(action.get("method") or "GET").upper()
            use_key = bool(action.get("use_site_key")) and bool(site_key)
            body_obj = action.get("body") if isinstance(action.get("body"), dict) else None
            hdrs = agent_headers(
                human_token=human_token if isinstance(human_token, str) else None,
                site_key=site_key if use_key else None,
                session=session_token,
            )
            if method == "POST" and use_key and body_obj is not None and site_key:
                body_obj = {**body_obj, "site_key": site_key}

            st, rh, raw = _request(url, method=method, headers=hdrs, body=body_obj)
            summ = _summarize_fetch(st, raw, rh.get("content-type", ""))
            findings.append({"url": url, "method": method, **summ})
            parsed = summ.get("json")

            if isinstance(parsed, dict) and parsed.get("session_token"):
                session_token = str(parsed.get("session_token"))

            if st >= 400:
                denied = True
                err = ""
                if isinstance(parsed, dict):
                    err = str(parsed.get("error") or parsed.get("message") or parsed.get("summary") or "")
                add(
                    "request",
                    result="failed",
                    detail=err or f"HTTP {st}",
                    method=method,
                    url=url,
                    status=st,
                    site_key_sent=use_key,
                )
                continue

            saw = None
            if isinstance(parsed, dict):
                if isinstance(parsed.get("products"), list):
                    slug_m = re.match(r"^/products/([^/]+)/?$", path)
                    wanted = None
                    if slug_m:
                        slug = slug_m.group(1)
                        wanted = next(
                            (
                                p
                                for p in parsed["products"]
                                if isinstance(p, dict) and (p.get("slug") == slug or p.get("id") == slug)
                            ),
                            None,
                        )
                    if wanted:
                        fields = _fields_from_product(wanted) or fields
                        saw = {f["label"]: f["value"] for f in fields}
                        denied = False
                    else:
                        names = [
                            str(p.get("name"))
                            for p in parsed["products"][:8]
                            if isinstance(p, dict) and p.get("name")
                        ]
                        if names:
                            fields.append({"label": "Products", "value": ", ".join(names)})
                            saw = {"Products": ", ".join(names)}
                            denied = False
                elif parsed.get("title") or parsed.get("meta") or parsed.get("summary"):
                    page_fields: list[dict[str, str]] = []
                    for key in ("title", "summary"):
                        if parsed.get(key):
                            page_fields.append({"label": key.capitalize(), "value": str(parsed.get(key))})
                    meta = parsed.get("meta") if isinstance(parsed.get("meta"), dict) else {}
                    for key in ("name", "price", "compare_at", "rating", "sku", "highlights"):
                        if meta.get(key) is not None and meta.get(key) != "":
                            page_fields.append(
                                {
                                    "label": key.replace("_", " ").capitalize(),
                                    "value": str(meta.get(key)),
                                }
                            )
                    if page_fields:
                        fields = page_fields
                        saw = {f["label"]: f["value"] for f in page_fields}
                        denied = False
                elif parsed.get("ok") and parsed.get("session_token"):
                    saw = {"session": "received", "scopes": parsed.get("granted_scopes")}
                elif "endpoints" in parsed or "help" in str(parsed.get("note") or "").lower() or parsed.get("protocol"):
                    saw = {"help": True, "keys": list(parsed.keys())[:8]}

            add(
                "request",
                result="ok",
                detail="Got a response",
                method=method,
                url=url,
                status=st,
                site_key_sent=use_key,
                saw=saw,
            )

    reply = _compose_reply(
        message=message,
        steps=steps,
        fields=fields,
        denied=denied,
        model=model_info.get("id"),
        provider=model_info.get("provider"),
    )

    return {
        "ok": True,
        "denied": denied,
        "reply": reply,
        "steps": steps,
        "path": path,
        "url": target_url,
        "status": status,
        "captcha": {"attempted": True, "passed": captcha_passed},
        "fields": fields,
        "model": model_info,
        "site_response": {
            "url": target_url,
            "site_key_used": bool(site_key),
            "findings": findings,
            "agent_access": captcha.get("agent_access"),
        },
    }


def _field_map(fields: list[dict[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in fields:
        label = str(f.get("label") or "").strip()
        value = str(f.get("value") or "").strip()
        if label and value:
            out[label.lower()] = value
    return out


def _asked_keys(message: str) -> list[str]:
    lowered = message.lower()
    if any(w in lowered for w in ("price", "cost", "how much")):
        return ["price", "compare at", "compare_at"]
    if any(w in lowered for w in ("rating", "review", "stars")):
        return ["rating"]
    if any(w in lowered for w in ("name", "title", "called", "what product")):
        return ["name", "title"]
    if "sku" in lowered:
        return ["sku"]
    return []


def _answer_from_fields(message: str, fields: list[dict[str, str]]) -> str | None:
    """Direct answer only when the asked field is actually present."""
    if not fields:
        return None
    m = _field_map(fields)

    def pick(*keys: str) -> str | None:
        for k in keys:
            if k in m:
                return m[k]
        return None

    asked = _asked_keys(message)
    if asked:
        value = pick(*asked)
        if not value:
            return None
        name = pick("name", "title")
        key = asked[0]
        if key in ("price", "compare at", "compare_at"):
            return f"The price of {name} is {value}." if name else f"The price is {value}."
        if key == "rating":
            return f"The rating for {name} is {value}." if name else f"The rating is {value}."
        if key in ("name", "title"):
            return f"The product name is {value}."
        if key == "sku":
            return f"The SKU is {value}."
        return f"{key.capitalize()}: {value}."

    # Broad ask ("what can you see") — short field dump, no story.
    preferred = ["name", "title", "price", "rating", "sku"]
    bits = [f"{k.capitalize()}: {m[k]}" for k in preferred if k in m]
    if not bits:
        return None
    return "; ".join(bits) + "."


def _failure_reason(steps: list[dict[str, Any]]) -> str:
    fail_reqs = [s for s in steps if s.get("action") == "request" and s.get("result") == "failed"]
    if fail_reqs:
        detail = str(fail_reqs[-1].get("detail") or "access denied")
        return f"I couldn't get that — {detail}."
    if any(s.get("action") == "solve_captcha" and s.get("result") == "rejected" for s in steps):
        if not any(s.get("action") == "switch_to_api" for s in steps):
            return "I couldn't get that — human verification blocked me."
    if any(s.get("action") == "open_url" and s.get("result") == "blocked" for s in steps):
        return "I couldn't get that — the storefront blocked automated access."
    return "I couldn't get the data you asked for."


def _compose_reply(
    *,
    message: str,
    steps: list[dict[str, Any]],
    fields: list[dict[str, str]],
    denied: bool,
    model: str | None = None,
    provider: str | None = None,
) -> str:
    """If we can answer, answer only. Otherwise one short failure line."""
    deterministic = _answer_from_fields(message, fields) if fields else None
    if deterministic:
        # Optional model phrasing — fall back instantly if the model is weird/slow/fails.
        try:
            facts = {f["label"]: f["value"] for f in fields}
            polished = muse_client.complete(
                [
                    {
                        "role": "user",
                        "content": (
                            "Answer the user in ONE short sentence using only these facts. "
                            "No steps, no story, no JSON.\n"
                            f"Question: {message}\nFacts: {json.dumps(facts)}"
                        ),
                    }
                ],
                model=model,
                provider=provider,
                max_tokens=60,
                temperature=0.1,
            ).strip()
            words = polished.split()
            bad = any(
                w in polished.lower()
                for w in ("rewrite", "steps", "json", "as an ai", "prompt")
            )
            if polished and 3 <= len(words) <= 40 and not bad:
                return polished
        except Exception:
            pass
        return deterministic

    asked = _asked_keys(message)
    if asked and fields:
        label = asked[0].replace("_", " ")
        return f"I reached the page, but {label} was not available to agents."

    if denied or not fields:
        return _failure_reason(steps)

    return "I checked the page, but couldn't find an answer to that."
