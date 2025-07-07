const jwt = require("jsonwebtoken");
const { v4: uuidv4 } = require("uuid");

/**
 * generateJwt - Generates a signed Sigma JWT for embedding.
 *
 * This JWT grants access to a specific embed URL for a specified user (`sub`),
 * scoped to either "view" or "build" permissions.
 *
 * The JWT must be signed using your Sigma-issued shared secret and include
 * your client ID as the issuer (`iss`).
 *
 * Sigma Docs: https://help.sigmacomputing.com/docs/authenticate-embed-users
 *
 * @param {Object} options
 * @param {string} options.embedUrl - The fully qualified Sigma embed URL.
 * @param {string} options.mode - Either "view" or "build".
 * @param {string} options.sub - Email or memberId of the user.
 * @returns {string} A signed JWT token.
 */
function generateJwt({ embedUrl, mode, sub }) {
  if (!sub) {
    throw new Error("Missing 'sub' (user identifier) — must be passed explicitly.");
  }

  const payload = {
    iss: process.env.CLIENT_ID, // Sigma embed client ID
    sub,
    aud: "https://sigmacomputing.com/iam",
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 60 * 5, // 5-minute TTL
    jti: uuidv4(), // unique token ID
    scope: "embed",
    embed: {
      url: embedUrl,
      permissions: mode === "build" ? ["build", "view"] : ["view"],
    },
  };

  const secret = process.env.SECRET;
  const kid = process.env.KEY_ID || process.env.CLIENT_ID;

  if (!secret || !kid) {
    throw new Error("Missing SECRET or KEY_ID environment variables");
  }

  return jwt.sign(payload, secret, {
    algorithm: "HS256",
    header: { kid },
  });
}

module.exports = generateJwt;
