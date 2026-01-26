// helpers/pkce.js
// PKCE (Proof Key for Code Exchange) utilities for OAuth 2.0
// Implements RFC 7636 for secure authorization code flow

const crypto = require('crypto');

/**
 * Generates a base64url-encoded random string
 * @param {number} length - Length of random bytes to generate
 * @returns {string} Base64url-encoded string
 */
function base64URLEncode(buffer) {
  return buffer
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

/**
 * Generates a cryptographically secure random code verifier
 * Per RFC 7636: 43-128 characters from [A-Z, a-z, 0-9, -, ., _, ~]
 * @returns {string} Random code verifier
 */
function generateCodeVerifier() {
  const randomBytes = crypto.randomBytes(32); // 32 bytes = 43 chars in base64url
  return base64URLEncode(randomBytes);
}

/**
 * Generates a code challenge from a code verifier using SHA-256
 * @param {string} verifier - The code verifier
 * @returns {string} Base64url-encoded SHA-256 hash of the verifier
 */
function generateCodeChallenge(verifier) {
  const hash = crypto.createHash('sha256').update(verifier).digest();
  return base64URLEncode(hash);
}

/**
 * Generates a complete PKCE pair (verifier and challenge)
 * @returns {{ codeVerifier: string, codeChallenge: string }}
 */
function generatePKCE() {
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = generateCodeChallenge(codeVerifier);

  return {
    codeVerifier,
    codeChallenge,
    codeChallengeMethod: 'S256' // Always use SHA-256
  };
}

/**
 * Generates a random state parameter for CSRF protection
 * @returns {string} Random state string
 */
function generateState() {
  return base64URLEncode(crypto.randomBytes(32));
}

module.exports = {
  generatePKCE,
  generateState,
  generateCodeVerifier,
  generateCodeChallenge,
  base64URLEncode
};
