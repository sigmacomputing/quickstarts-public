// Azure Functions (Node 20+, classic model)
// HS256 JWT signing with built-in crypto (no external deps)
const crypto = require("crypto");

/** base64url helper */
function b64url(input) {
  return Buffer.from(input)
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

/** create HS256 JWT (adds kid to header) */
function signHS256(payload, secret, kid) {
  const header = { alg: "HS256", typ: "JWT" };
  if (kid) header.kid = kid;

  const encHeader = b64url(JSON.stringify(header));
  const encPayload = b64url(JSON.stringify(payload));
  const data = `${encHeader}.${encPayload}`;

  const sig = crypto
    .createHmac("sha256", secret)
    .update(data)
    .digest("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");

  return `${data}.${sig}`;
}

module.exports = async function (context, req) {
  try {
    // ---- config from app settings ----
    const {
      BASE_URL,
      CLIENT_ID,
      SECRET,
      ACCOUNT_TYPE = "Embed",
      TEAM = "",
      SESSION_LENGTH = "300",
      DEV_EMAIL = ""
    } = process.env;

    if (!BASE_URL || !CLIENT_ID || !SECRET) {
      context.res = { status: 500, body: { error: "config_missing" } };
      return;
    }

    // ---- caller identity (QS-friendly) ----
    // Use ?email=... or body.email, else fall back to DEV_EMAIL
    const email =
      (req.query && req.query.email) ||
      (req.body && req.body.email) ||
      DEV_EMAIL;

    if (!email) {
      context.res = { status: 401, body: { error: "email_required" } };
      return;
    }

    // ---- JWT claims (Sigma-compatible) ----
    const now = Math.floor(Date.now() / 1000);
    const maxSession = Math.min(parseInt(SESSION_LENGTH, 10) || 300, 60 * 60 * 24 * 30); // <= 30 days
    const jti =
      (crypto.randomUUID && crypto.randomUUID()) ||
      [...crypto.randomBytes(16)]
        .map(b => b.toString(16).padStart(2, "0"))
        .join("");

    const teams = TEAM ? [TEAM] : [];

    const payload = {
      sub: email,               // subject (user)
      iss: CLIENT_ID,           // your embed client id
      iat: now,                 // issued at
      exp: now + maxSession,    // expiry
      jti,                      // unique token id
      account_type: ACCOUNT_TYPE,
      teams
      // Add other optional claims if needed:
      // aud: "sigma",
      // email: email
    };

    const token = signHS256(payload, SECRET, CLIENT_ID);

    // Build Sigma embed URL (workbook URL with :jwt & :embed=true)
    const join = BASE_URL.includes("?") ? "&" : "?";
    const embedUrl = `${BASE_URL}${join}:jwt=${encodeURIComponent(token)}&:embed=true`;

    // Optional CORS reflect (QS-friendly)
    const origin = req.headers?.origin;
    const headers = {
      "content-type": "application/json",
      "cache-control": "no-store"
    };
    if (origin) headers["access-control-allow-origin"] = origin;

    context.res = {
      status: 200,
      headers,
      body: JSON.stringify({ embedUrl, expires_in: maxSession })
    };
  } catch (err) {
    context.log.error(err);
    context.res = { status: 500, body: { error: "jwt_mint_failed" } };
  }
};
