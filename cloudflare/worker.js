/**
 * K-Signal Cloudflare Worker.
 *
 * The publication is a static site served by Workers Static Assets. This Worker exists for one
 * dynamic route — the public "Correct the read" endpoint that replaces Netlify Forms — and
 * delegates everything else back to the asset binding. The deploy configuration only routes
 * `/api/*` here (`assets.run_worker_first`), so ordinary publication traffic never reaches this
 * code; the `env.ASSETS.fetch` fallback below is a safety net for a misconfiguration, not a
 * request path the site depends on.
 */

import {
  COLUMNS,
  CORRECTIONS_PATH,
  DEFAULT_ALLOWED_ORIGINS,
  EMAIL_PATTERN,
  FAILURE_COPY,
  FALSY_CHECKBOX_VALUES,
  FORM_CONTENT_TYPE,
  INSERT_CORRECTION,
  LIMITS,
  MAX_BODY_BYTES,
  SUCCESS_COPY,
} from "./contract.js";

const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
};

function json(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...JSON_HEADERS, ...headers },
  });
}

/**
 * A browser that submits the form with JavaScript disabled navigates to this response, so it gets
 * a minimal acknowledgement page instead of raw JSON. This is intentionally not a confirmation
 * route: no template, no styling, no redirect target to keep in sync with the publication.
 */
function acknowledgement(status, message) {
  const body =
    '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    "<title>Correction received · K-Signal</title></head>" +
    "<body><p>" + message + '</p><p><a href="/">Back to K-Signal</a></p></body></html>';
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}

function wantsHtml(request) {
  return (request.headers.get("Accept") || "").includes("text/html");
}

function allowedOrigins(env) {
  return (env.CORRECTION_ALLOWED_ORIGINS || DEFAULT_ALLOWED_ORIGINS)
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

/**
 * Same-origin endpoint. An absent `Origin` is allowed because a no-JS form navigation does not
 * always carry one; a present `Origin` must be one we publish from. No CORS headers are ever
 * returned, so a cross-origin caller cannot read the response either way.
 */
function originAllowed(request, env) {
  const origin = request.headers.get("Origin");
  if (!origin) return true;
  return allowedOrigins(env).includes(origin);
}

function bounded(params, field) {
  const value = (params.get(field) || "").trim();
  if (value.length > LIMITS[field]) return { error: field + "_too_long" };
  return { value: value || null };
}

function readCheckbox(params, field) {
  if (!params.has(field)) return 0;
  return FALSY_CHECKBOX_VALUES.has((params.get(field) || "").trim().toLowerCase()) ? 0 : 1;
}

/**
 * Turn a submitted form into a row, or into a stable machine-readable error code.
 *
 * The metadata fields describe where the correction came from so a reviewer can find the article
 * again. They are bounded but never trusted: nothing here grants access to anything, so a forged
 * `article_slug` costs a reviewer a moment of confusion and nothing more.
 *
 * `signal_id` is accepted by the transport and deliberately not stored: issue_builder emits it
 * empty on every card, and a reviewer has `article_slug` and `card_id` to locate the story.
 */
function buildRow(params) {
  const comment = (params.get("comment") || "").trim();
  if (!comment) return { error: "comment_required" };
  if (comment.length > LIMITS.comment) return { error: "comment_too_long" };

  const name = bounded(params, "name");
  if (name.error) return name;

  const email = bounded(params, "email");
  if (email.error) return email;
  if (email.value !== null && !EMAIL_PATTERN.test(email.value)) return { error: "email_invalid" };

  const metadata = {};
  for (const field of ["issue_id", "card_id", "article_slug", "source_page", "consent_state"]) {
    const read = bounded(params, field);
    if (read.error) return read;
    metadata[field] = read.value;
  }

  return {
    row: {
      id: crypto.randomUUID(),
      created_at: new Date().toISOString(),
      status: "pending",
      issue_id: metadata.issue_id,
      card_id: metadata.card_id,
      article_slug: metadata.article_slug,
      source_page: metadata.source_page,
      name: name.value,
      email: email.value,
      comment,
      context_correction: readCheckbox(params, "context_correction"),
      consent_state: metadata.consent_state,
    },
  };
}

async function handleCorrections(request, env) {
  if (request.method !== "POST") {
    return json(405, { ok: false, error: "method_not_allowed" }, { Allow: "POST" });
  }

  const contentType = (request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
  if (contentType !== FORM_CONTENT_TYPE) {
    return json(415, { ok: false, error: "unsupported_media_type" });
  }

  if (!originAllowed(request, env)) {
    return json(403, { ok: false, error: "forbidden_origin" });
  }

  const declared = Number(request.headers.get("Content-Length"));
  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) {
    return json(413, { ok: false, error: "payload_too_large" });
  }

  let params;
  try {
    const body = await request.text();
    // A chunked request has no Content-Length to pre-check, so the read length is checked too.
    if (body.length > MAX_BODY_BYTES) {
      return json(413, { ok: false, error: "payload_too_large" });
    }
    params = new URLSearchParams(body);
  } catch (error) {
    return json(400, { ok: false, error: "malformed_body" });
  }

  // The honeypot is answered exactly like a real submission so an automated client cannot learn
  // which field is the trap by comparing responses. Nothing is written.
  if ((params.get("bot-field") || "").trim()) {
    return wantsHtml(request) ? acknowledgement(201, SUCCESS_COPY) : json(201, { ok: true });
  }

  const built = buildRow(params);
  if (built.error) {
    return wantsHtml(request)
      ? acknowledgement(400, FAILURE_COPY)
      : json(400, { ok: false, error: built.error });
  }

  const row = built.row;
  try {
    await env.DB.prepare(INSERT_CORRECTION)
      .bind(...COLUMNS.map((column) => row[column]))
      .run();
  } catch (error) {
    // The D1 message can name columns and constraints, so it stays in the Worker log and never
    // reaches the reader.
    console.error("corrections insert failed", error);
    return wantsHtml(request)
      ? acknowledgement(500, FAILURE_COPY)
      : json(500, { ok: false, error: "internal_error" });
  }

  return wantsHtml(request) ? acknowledgement(201, SUCCESS_COPY) : json(201, { ok: true, id: row.id });
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname === CORRECTIONS_PATH) {
      return handleCorrections(request, env);
    }
    if (pathname.startsWith("/api/")) {
      return json(404, { ok: false, error: "not_found" });
    }
    // Only reachable if `run_worker_first` is ever widened past `/api/*`; the publication is
    // served by the asset binding, not by this code.
    return env.ASSETS.fetch(request);
  },
};
