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
  return sign(
    {
      sub: config.embedUserEmail,
      iss: config.embedClientId,
      jti: randomUUID(),
      iat: now,
      exp: now + config.sessionLength,
      account_type: config.accountType || undefined,
      teams: config.teams,
      user_attributes: config.userAttributes,
    },
    config,
  );
}

// The assertion exchanged for an API token that acts as the embed user.
// It is used immediately, so it expires quickly.
export function createApiAssertion(config) {
  const now = Math.floor(Date.now() / 1000);
  return sign(
    {
      iss: config.embedClientId,
      sub: config.embedUserEmail,
      aud: "https://sigmacomputing.com/iam",
      iat: now,
      exp: now + 300,
      jti: randomUUID(),
      scope: "embed",
      embed: {
        url: `${config.appUrl}/${config.orgSlug}/workbook/search`,
        permissions: ["view"],
      },
    },
    config,
  );
}
