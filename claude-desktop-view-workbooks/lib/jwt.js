import jwt from "jsonwebtoken";
import { randomUUID } from "node:crypto";

const sign = (payload, config) =>
  jwt.sign(payload, config.embedClientSecret, {
    algorithm: "HS256",
    keyid: config.embedClientId,
  });

// The JWT that opens a workbook. It carries a unique jti and Sigma accepts it
// once, so a fresh one is made for every request.
export function createEmbedJwt(config) {
  const now = Math.floor(Date.now() / 1000);
  const claims = {
    sub: config.embedUserEmail,
    iss: config.embedClientId,
    jti: randomUUID(),
    iat: now,
    exp: now + config.sessionLength,
  };

  // These claims describe embed users. Sigma rejects them for existing Sigma
  // users ("Cannot update user attributes for internal users"), so they are
  // sent only when set.
  if (config.accountType) claims.account_type = config.accountType;
  if (config.teams.length) claims.teams = config.teams;
  if (Object.keys(config.userAttributes).length) {
    claims.user_attributes = config.userAttributes;
  }

  return sign(claims, config);
}
