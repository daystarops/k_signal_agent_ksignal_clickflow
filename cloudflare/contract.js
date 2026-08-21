/**
 * The correction endpoint's contract, in one place.
 *
 * These live outside `worker.js` because a Worker entrypoint module may only export its handler:
 * workerd reads every named export as a service entry and refuses anything that is not a function,
 * so exporting a limits table from the entrypoint fails the runtime at startup rather than at
 * deploy time. Keeping them here also lets the tests assert against the same values the Worker
 * enforces instead of restating them.
 */

export const CORRECTIONS_PATH = "/api/corrections";
export const FORM_CONTENT_TYPE = "application/x-www-form-urlencoded";

// A correction is a paragraph of prose plus a little routing metadata. 16 KiB of urlencoded body
// is already several times the largest legitimate submission, so anything above it is refused
// before the body is read into memory or parsed.
export const MAX_BODY_BYTES = 16 * 1024;

export const LIMITS = {
  comment: 4000,
  name: 120,
  // The maximum length of an addr-spec in RFC 5321.
  email: 254,
  issue_id: 32,
  card_id: 64,
  article_slug: 160,
  source_page: 512,
  consent_state: 64,
};

// Deliberately permissive: this is a syntax gate that rejects obvious junk, not an attempt to
// decide whether a mailbox exists. A correction is worth keeping even if we cannot reply to it.
export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const DEFAULT_ALLOWED_ORIGINS = "https://k-signal.com";

// Checkbox semantics: an unchecked box is not submitted at all, so presence normally means true.
// These values are still read as false because a hand-built or replayed request can send them.
export const FALSY_CHECKBOX_VALUES = new Set(["", "0", "false", "off", "no"]);

// The copy the article page already shows. The Worker repeats it only on the no-JS path, where
// there is no page left to write a status into.
export const SUCCESS_COPY = "Got it — thanks for sharpening the signal.";
export const FAILURE_COPY = "Couldn’t save that. Try again.";

/** The column order the Worker binds. */
export const COLUMNS = [
  "id",
  "created_at",
  "status",
  "issue_id",
  "card_id",
  "article_slug",
  "source_page",
  "name",
  "email",
  "comment",
  "context_correction",
  "consent_state",
];

export const INSERT_CORRECTION =
  "INSERT INTO corrections (" + COLUMNS.join(", ") + ") VALUES (" +
  COLUMNS.map(() => "?").join(", ") + ")";
