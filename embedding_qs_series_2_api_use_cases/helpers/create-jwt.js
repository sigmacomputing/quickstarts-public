const jwt = require("jsonwebtoken");
const { v4: uuidv4 } = require("uuid");

/**
 * generateJwt - Generates a signed Sigma JWT for embedding.
 *
 * @param {Object} options
 * @param {string} options.embedUrl - The fully qualified Sigma embed URL.
 * @param {string} options.mode - "view" or "build" (fallback if permissions not given)
 * @param {string} options.sub - Email or memberId of the user.
 * @param {string[]} [options.permissions] - Optional explicit permissions array (e.g., ["build"])
 * @returns {string} A signed JWT token.
 */
function generateJwt({ embedUrl, mode, sub, permissions }) {
  if (!sub) {
    throw new Error("Missing 'sub' (user identifier) — must be passed explicitly.");
  }

  const finalPermissions =
    permissions || 
    (mode === "admin" ? ["build", "view", "admin"] : 
     mode === "build" ? ["build"] : ["view"]);

  const payload = {
    iss: process.env.CLIENT_ID,
    sub,
    aud: process.env.JWT_AUDIENCE || "https://sigmacomputing.com/iam",
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 60 * 5,
    jti: uuidv4(),
    scope: "embed",
    embed: {
      url: embedUrl,
      permissions: finalPermissions,
    },
  };

  const secret = process.env.SECRET;
  const kid = process.env.KEY_ID || process.env.CLIENT_ID;

  if (!secret || !kid) {
    throw new Error("Missing SECRET or KEY_ID environment variables");
  }

  if (process.env.DEBUG === "true") {
    console.log("JWT payload:", payload);
    console.log("JWT for:", payload.sub);
  }

  return jwt.sign(payload, secret, {
    algorithm: "HS256",
    header: { kid },
  });
}

module.exports = generateJwt;
