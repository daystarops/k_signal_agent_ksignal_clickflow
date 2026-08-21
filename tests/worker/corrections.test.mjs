/**
 * Contract tests for the K-Signal corrections Worker.
 *
 * D1 is stubbed rather than emulated: what these tests are for is the request contract — what is
 * accepted, what is refused, what reaches the database and in what shape. That the SQL itself is
 * valid against the real schema is proved separately, by applying the migration to a local D1 and
 * driving the built site through `wrangler dev`.
 *
 * Run: node --test tests/worker/
 */

import assert from "node:assert/strict";
import test from "node:test";

import { COLUMNS, LIMITS, MAX_BODY_BYTES } from "../../cloudflare/contract.js";
import worker from "../../cloudflare/worker.js";

const ORIGIN = "https://k-signal.com";
const ENDPOINT = ORIGIN + "/api/corrections";

function stubDatabase({ failWith = null } = {}) {
  const rows = [];
  return {
    rows,
    statements: [],
    prepare(sql) {
      this.statements.push(sql);
      return {
        bind: (...values) => ({
          run: async () => {
            if (failWith) throw new Error(failWith);
            rows.push(Object.fromEntries(COLUMNS.map((column, index) => [column, values[index]])));
            return { success: true };
          },
        }),
      };
    },
  };
}

function stubAssets() {
  return { fetch: async () => new Response("static asset", { status: 200 }) };
}

function environment(overrides = {}) {
  return { DB: stubDatabase(), ASSETS: stubAssets(), ...overrides };
}

/** A complete, valid submission. Individual tests override or delete fields. */
function validFields() {
  return {
    issue_id: "002",
    card_id: "01",
    article_slug: "samjeon-nix-samsung-hynix",
    source_page: "/articles/samjeon-nix-samsung-hynix/",
    signal_id: "",
    consent_state: "",
    "bot-field": "",
    name: "",
    email: "",
    comment: "The Korean phrase here reads closer to resignation than anger.",
  };
}

function submit(env, fields, options = {}) {
  const {
    method = "POST",
    contentType = "application/x-www-form-urlencoded",
    origin = ORIGIN,
    accept = "*/*",
    body = fields === null ? "" : new URLSearchParams(fields).toString(),
    headers: extra = {},
  } = options;

  const headers = { Accept: accept, ...extra };
  if (contentType !== null) headers["Content-Type"] = contentType;
  if (origin !== null) headers.Origin = origin;

  const request = new Request(ENDPOINT, {
    method,
    headers,
    body: method === "GET" || method === "HEAD" ? undefined : body,
  });
  return worker.fetch(request, env);
}

test("a valid submission is stored once and answered with its id", async () => {
  const env = environment();
  const response = await submit(env, validFields());

  assert.equal(response.status, 201);
  const payload = await response.json();
  assert.equal(payload.ok, true);
  assert.match(payload.id, /^[0-9a-f-]{36}$/);

  assert.equal(env.DB.rows.length, 1);
  const row = env.DB.rows[0];
  assert.equal(row.id, payload.id);
  assert.equal(row.status, "pending");
  assert.equal(row.article_slug, "samjeon-nix-samsung-hynix");
  assert.equal(row.comment, validFields().comment);
  assert.equal(row.context_correction, 0);
  assert.doesNotThrow(() => new Date(row.created_at).toISOString());
  // Empty optional fields become NULL rather than empty strings, so a reviewer can tell "not
  // given" from "given as blank" without a second convention.
  assert.equal(row.name, null);
  assert.equal(row.email, null);
});

test("the insert is a prepared statement, not interpolated SQL", async () => {
  const env = environment();
  await submit(env, { ...validFields(), comment: "Robert'); DROP TABLE corrections;--" });

  assert.equal(env.DB.statements.length, 1);
  const sql = env.DB.statements[0];
  assert.match(sql, /^INSERT INTO corrections /);
  assert.equal(sql.match(/\?/g).length, COLUMNS.length);
  assert.ok(!sql.includes("DROP TABLE"));
  assert.equal(env.DB.rows[0].comment, "Robert'); DROP TABLE corrections;--");
});

test("a missing comment is refused", async () => {
  const env = environment();
  const fields = validFields();
  delete fields.comment;
  const response = await submit(env, fields);

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { ok: false, error: "comment_required" });
  assert.equal(env.DB.rows.length, 0);
});

test("a whitespace-only comment is refused", async () => {
  const env = environment();
  const response = await submit(env, { ...validFields(), comment: "   \n\t  " });

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { ok: false, error: "comment_required" });
  assert.equal(env.DB.rows.length, 0);
});

test("a comment is stored trimmed", async () => {
  const env = environment();
  await submit(env, { ...validFields(), comment: "  trimmed on both sides  " });
  assert.equal(env.DB.rows[0].comment, "trimmed on both sides");
});

test("an overlong comment is refused", async () => {
  const env = environment();
  const response = await submit(env, { ...validFields(), comment: "x".repeat(LIMITS.comment + 1) });

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { ok: false, error: "comment_too_long" });
  assert.equal(env.DB.rows.length, 0);
});

test("a comment exactly at the limit is accepted", async () => {
  const env = environment();
  const response = await submit(env, { ...validFields(), comment: "x".repeat(LIMITS.comment) });

  assert.equal(response.status, 201);
  assert.equal(env.DB.rows.length, 1);
});

test("a malformed email is refused", async () => {
  for (const email of ["not-an-email", "no@tld", "two@@at.example", "spaced out@example.com"]) {
    const env = environment();
    const response = await submit(env, { ...validFields(), email });

    assert.equal(response.status, 400, email);
    assert.deepEqual(await response.json(), { ok: false, error: "email_invalid" }, email);
    assert.equal(env.DB.rows.length, 0, email);
  }
});

test("an overlong email is refused before it is parsed", async () => {
  const env = environment();
  const email = "x".repeat(LIMITS.email) + "@example.com";
  const response = await submit(env, { ...validFields(), email });

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { ok: false, error: "email_too_long" });
});

test("optional name and email are accepted and trimmed", async () => {
  const env = environment();
  const response = await submit(env, {
    ...validFields(),
    name: "  Jae-won  ",
    email: "  reader@example.com  ",
  });

  assert.equal(response.status, 201);
  assert.equal(env.DB.rows[0].name, "Jae-won");
  assert.equal(env.DB.rows[0].email, "reader@example.com");
});

test("an overlong name is refused", async () => {
  const env = environment();
  const response = await submit(env, { ...validFields(), name: "x".repeat(LIMITS.name + 1) });

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { ok: false, error: "name_too_long" });
});

test("an overlong metadata field is refused", async () => {
  const env = environment();
  const response = await submit(env, {
    ...validFields(),
    source_page: "/" + "x".repeat(LIMITS.source_page),
  });

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { ok: false, error: "source_page_too_long" });
  assert.equal(env.DB.rows.length, 0);
});

test("a ticked context-correction checkbox is stored as 1", async () => {
  const env = environment();
  await submit(env, { ...validFields(), context_correction: "yes" });
  assert.equal(env.DB.rows[0].context_correction, 1);
});

test("an absent context-correction checkbox is stored as 0", async () => {
  const env = environment();
  const fields = validFields();
  assert.ok(!("context_correction" in fields));
  await submit(env, fields);
  assert.equal(env.DB.rows[0].context_correction, 0);
});

test("an explicitly falsy checkbox value is stored as 0", async () => {
  for (const value of ["", "0", "false", "off", "no"]) {
    const env = environment();
    await submit(env, { ...validFields(), context_correction: value });
    assert.equal(env.DB.rows[0].context_correction, 0, value);
  }
});

test("a filled honeypot looks like success and stores nothing", async () => {
  const env = environment();
  const response = await submit(env, { ...validFields(), "bot-field": "https://spam.example" });

  assert.equal(response.status, 201);
  // Deliberately indistinguishable in status and shape from a real success, minus the id there is
  // no row to name. A bot must not be able to detect the trap by diffing responses.
  assert.deepEqual(await response.json(), { ok: true });
  assert.equal(env.DB.rows.length, 0);
});

test("a honeypot of only whitespace is treated as untouched", async () => {
  const env = environment();
  const response = await submit(env, { ...validFields(), "bot-field": "   " });

  assert.equal(response.status, 201);
  assert.equal(env.DB.rows.length, 1);
});

test("an unsupported method is refused with 405 and an Allow header", async () => {
  for (const method of ["GET", "PUT", "DELETE", "PATCH"]) {
    const env = environment();
    const response = await submit(env, validFields(), { method });

    assert.equal(response.status, 405, method);
    assert.equal(response.headers.get("Allow"), "POST", method);
    assert.deepEqual(await response.json(), { ok: false, error: "method_not_allowed" }, method);
    assert.equal(env.DB.rows.length, 0, method);
  }
});

test("an unsupported content type is refused with 415", async () => {
  for (const contentType of ["application/json", "text/plain", "multipart/form-data", null]) {
    const env = environment();
    const response = await submit(env, validFields(), { contentType });

    assert.equal(response.status, 415, String(contentType));
    assert.deepEqual(await response.json(), { ok: false, error: "unsupported_media_type" });
    assert.equal(env.DB.rows.length, 0);
  }
});

test("the form content type is accepted with a charset parameter", async () => {
  const env = environment();
  const response = await submit(env, validFields(), {
    contentType: "application/x-www-form-urlencoded; charset=UTF-8",
  });
  assert.equal(response.status, 201);
});

test("an untrusted Origin is refused and stores nothing", async () => {
  for (const origin of ["https://evil.example", "http://k-signal.com", "https://k-signal.com.evil.example"]) {
    const env = environment();
    const response = await submit(env, validFields(), { origin });

    assert.equal(response.status, 403, origin);
    assert.deepEqual(await response.json(), { ok: false, error: "forbidden_origin" }, origin);
    assert.equal(env.DB.rows.length, 0, origin);
  }
});

test("no CORS headers are ever returned", async () => {
  const env = environment();
  const response = await submit(env, validFields());
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), null);
});

test("an absent Origin is allowed, because a no-JS form navigation may omit it", async () => {
  const env = environment();
  const response = await submit(env, validFields(), { origin: null });

  assert.equal(response.status, 201);
  assert.equal(env.DB.rows.length, 1);
});

test("the allowed-origin seam admits a development origin", async () => {
  const env = environment({
    CORRECTION_ALLOWED_ORIGINS: "https://k-signal.com, http://localhost:8787",
  });
  const response = await submit(env, validFields(), { origin: "http://localhost:8787" });

  assert.equal(response.status, 201);
  assert.equal(env.DB.rows.length, 1);
});

test("configuring a development origin does not admit an arbitrary one", async () => {
  const env = environment({ CORRECTION_ALLOWED_ORIGINS: "http://localhost:8787" });
  const response = await submit(env, validFields(), { origin: "https://evil.example" });
  assert.equal(response.status, 403);
});

test("an oversized body is refused before it is parsed", async () => {
  const env = environment();
  const body = "comment=" + "x".repeat(MAX_BODY_BYTES + 1);
  const response = await submit(env, null, {
    body,
    headers: { "Content-Length": String(body.length) },
  });

  assert.equal(response.status, 413);
  assert.deepEqual(await response.json(), { ok: false, error: "payload_too_large" });
  assert.equal(env.DB.rows.length, 0);
});

test("an oversized body with no declared length is still refused", async () => {
  const env = environment();
  const response = await submit(env, null, { body: "comment=" + "x".repeat(MAX_BODY_BYTES + 1) });

  assert.equal(response.status, 413);
  assert.equal(env.DB.rows.length, 0);
});

test("a database failure is reported as a sanitised 500", async () => {
  const leak = "D1_ERROR: no such column: corrections.internal_moderation_note";
  const env = environment({ DB: stubDatabase({ failWith: leak }) });
  const response = await submit(env, validFields());

  assert.equal(response.status, 500);
  const text = await response.text();
  assert.deepEqual(JSON.parse(text), { ok: false, error: "internal_error" });
  // Nothing about the schema, the driver, or the stack reaches the reader.
  assert.ok(!text.includes("D1_ERROR"));
  assert.ok(!text.includes("internal_moderation_note"));
  assert.ok(!text.includes("corrections"));
});

test("a no-JS browser navigation gets a minimal HTML acknowledgement, not raw JSON", async () => {
  const env = environment();
  const response = await submit(env, validFields(), {
    accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  });

  assert.equal(response.status, 201);
  assert.match(response.headers.get("Content-Type"), /^text\/html/);
  const body = await response.text();
  assert.ok(body.includes("Got it — thanks for sharpening the signal."));
  assert.equal(env.DB.rows.length, 1);
});

test("a no-JS validation failure gets HTML too, and still stores nothing", async () => {
  const env = environment();
  const response = await submit(env, { ...validFields(), comment: "" }, { accept: "text/html" });

  assert.equal(response.status, 400);
  assert.match(response.headers.get("Content-Type"), /^text\/html/);
  assert.ok((await response.text()).includes("Couldn’t save that. Try again."));
  assert.equal(env.DB.rows.length, 0);
});

test("a scripted submission gets JSON, because fetch does not ask for HTML", async () => {
  const env = environment();
  const response = await submit(env, validFields(), { accept: "application/json" });
  assert.match(response.headers.get("Content-Type"), /^application\/json/);
});

test("responses are never cached", async () => {
  const env = environment();
  const response = await submit(env, validFields());
  assert.equal(response.headers.get("Cache-Control"), "no-store");
});

test("a non-API request is delegated to the static asset binding", async () => {
  const env = environment();
  let delegated = null;
  env.ASSETS = {
    fetch: async (request) => {
      delegated = new URL(request.url).pathname;
      return new Response("static asset", { status: 200 });
    },
  };

  const response = await worker.fetch(
    new Request(ORIGIN + "/articles/samjeon-nix-samsung-hynix/"),
    env,
  );

  assert.equal(response.status, 200);
  assert.equal(await response.text(), "static asset");
  assert.equal(delegated, "/articles/samjeon-nix-samsung-hynix/");
  assert.equal(env.DB.rows.length, 0);
});

test("an unknown API path is a JSON 404 and never touches the asset binding", async () => {
  const env = environment();
  env.ASSETS = {
    fetch: async () => assert.fail("an /api/ path must not fall through to static assets"),
  };

  const response = await worker.fetch(new Request(ORIGIN + "/api/nope"), env);
  assert.equal(response.status, 404);
  assert.deepEqual(await response.json(), { ok: false, error: "not_found" });
});
