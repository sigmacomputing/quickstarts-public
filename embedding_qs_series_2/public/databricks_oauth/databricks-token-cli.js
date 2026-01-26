#!/usr/bin/env node

// databricks-token-cli.js
// Standalone CLI tool for generating Databricks OAuth tokens with PKCE
// Useful for testing and manual token generation

const http = require('http');
const { URL } = require('url');
const dotenv = require('dotenv');
const path = require('path');
const fs = require('fs').promises;
const readline = require('readline');

const {
  getAuthorizationUrl,
  exchangeCodeForToken,
  getCurrentUser,
  generatePKCE,
  generateState
} = require('./helpers/databricks-auth');

// Load centralized .env file from parent directory
dotenv.config({ path: path.resolve(__dirname, '../../.env') });

// ANSI color codes for terminal output
const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  red: '\x1b[31m'
};

function log(message, color = colors.reset) {
  console.log(`${color}${message}${colors.reset}`);
}

/**
 * Starts a local HTTP server to handle OAuth callback
 * @param {number} port - Port to listen on
 * @returns {Promise<string>} Authorization code from callback
 */
function startRedirectServer(port, expectedState) {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const url = new URL(req.url, `http://localhost:${port}`);

      if (url.pathname === '/callback') {
        const code = url.searchParams.get('code');
        const state = url.searchParams.get('state');
        const error = url.searchParams.get('error');

        if (error) {
          res.writeHead(200, { 'Content-Type': 'text/html' });
          res.end(`
            <html>
              <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                <h1 style="color: #d32f2f;">❌ Authentication Failed</h1>
                <p>Error: ${error}</p>
                <p>You can close this window.</p>
              </body>
            </html>
          `);
          server.close();
          reject(new Error(`OAuth error: ${error}`));
          return;
        }

        if (state !== expectedState) {
          res.writeHead(400, { 'Content-Type': 'text/html' });
          res.end(`
            <html>
              <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                <h1 style="color: #d32f2f;">❌ Invalid State</h1>
                <p>State parameter mismatch - possible CSRF attack</p>
                <p>You can close this window.</p>
              </body>
            </html>
          `);
          server.close();
          reject(new Error('State mismatch'));
          return;
        }

        if (code) {
          res.writeHead(200, { 'Content-Type': 'text/html' });
          res.end(`
            <html>
              <body style="font-family: sans-serif; padding: 40px; text-align: center;">
                <h1 style="color: #4caf50;">✅ Authentication Successful!</h1>
                <p>Authorization code received. You can close this window.</p>
                <p style="margin-top: 30px; color: #666;">Returning to CLI...</p>
              </body>
            </html>
          `);
          server.close();
          resolve(code);
        } else {
          res.writeHead(400, { 'Content-Type': 'text/plain' });
          res.end('Missing authorization code');
          server.close();
          reject(new Error('Missing authorization code'));
        }
      }
    });

    server.listen(port, () => {
      log(`\n🌐 Redirect server listening on http://localhost:${port}/callback`, colors.blue);
    });

    server.on('error', (err) => {
      reject(err);
    });
  });
}

/**
 * Opens the authorization URL in the default browser
 */
async function openBrowser(url) {
  const { spawn } = require('child_process');
  const platform = process.platform;

  let command;
  if (platform === 'darwin') {
    command = 'open';
  } else if (platform === 'win32') {
    command = 'start';
  } else {
    command = 'xdg-open';
  }

  log(`\n🔐 Opening browser for Databricks authentication...`, colors.yellow);
  log(`📋 If browser doesn't open, visit this URL manually:`, colors.yellow);
  log(`   ${url}\n`, colors.blue);

  spawn(command, [url], { detached: true, stdio: 'ignore' }).unref();
}

/**
 * Main token generation function
 */
async function generateToken() {
  try {
    log('\n' + '='.repeat(60), colors.bright);
    log('  Databricks OAuth Token Generator (PKCE)', colors.bright);
    log('='.repeat(60) + '\n', colors.bright);

    // Load configuration from .env
    const databricksHost = process.env.DATABRICKS_HOST;
    const accountId = process.env.DATABRICKS_ACCOUNT_ID;
    const clientId = process.env.DATABRICKS_OAUTH_CLIENT_ID;
    const clientSecret = process.env.DATABRICKS_OAUTH_CLIENT_SECRET;
    const authLevel = process.env.DATABRICKS_AUTH_LEVEL || 'workspace';

    if (!databricksHost || !clientId) {
      throw new Error('Missing required environment variables. Please check your .env file.');
    }

    if (authLevel === 'account' && !accountId) {
      throw new Error('DATABRICKS_ACCOUNT_ID required for account-level authentication');
    }

    log(`📊 Configuration:`, colors.green);
    log(`   Auth Level: ${authLevel}`);
    log(`   Databricks Host: ${databricksHost}`);
    if (authLevel === 'account') {
      log(`   Account ID: ${accountId}`);
    }
    log(`   Client ID: ${clientId}\n`);

    // Generate PKCE pair and state
    const { codeVerifier, codeChallenge } = generatePKCE();
    const state = generateState();

    log(`🔑 PKCE Challenge generated`, colors.green);

    // Extract port from redirect URI or use default
    const redirectUri = 'http://localhost:8020/callback';
    const redirectPort = 8020;

    // Start local redirect server
    const serverPromise = startRedirectServer(redirectPort, state);

    // Build authorization URL
    const authUrl = getAuthorizationUrl({
      databricksHost,
      accountId,
      clientId,
      redirectUri,
      authLevel,
      codeChallenge,
      state
    });

    // Open browser
    await openBrowser(authUrl);

    log(`⏳ Waiting for authentication...`, colors.yellow);

    // Wait for authorization code
    const authCode = await serverPromise;

    log(`\n✅ Authorization code received!`, colors.green);
    log(`🔄 Exchanging code for access token...\n`, colors.yellow);

    // Exchange code for tokens
    const tokenResponse = await exchangeCodeForToken({
      databricksHost,
      accountId,
      clientId,
      clientSecret,
      redirectUri,
      authLevel,
      code: authCode,
      codeVerifier
    });

    log(`✅ Token exchange successful!\n`, colors.green);

    // Get user information
    const userInfo = await getCurrentUser(tokenResponse.access_token, databricksHost);

    log(`👤 Authenticated User:`, colors.green);
    log(`   Email: ${userInfo.email}`);
    log(`   Display Name: ${userInfo.displayName}`);
    log(`   User ID: ${userInfo.id}\n`);

    log(`🎫 Token Details:`, colors.green);
    log(`   Token Type: ${tokenResponse.token_type}`);
    log(`   Expires In: ${tokenResponse.expires_in} seconds (${Math.floor(tokenResponse.expires_in / 60)} minutes)`);
    log(`   Scope: ${tokenResponse.scope}\n`);

    log(`📝 Access Token (first 50 chars):`, colors.blue);
    log(`   ${tokenResponse.access_token.substring(0, 50)}...\n`, colors.blue);

    // Save to file if configured
    if (process.env.DATABRICKS_SAVE_TOKEN_TO_FILE === 'true') {
      const tokenData = {
        access_token: tokenResponse.access_token,
        refresh_token: tokenResponse.refresh_token,
        expires_in: tokenResponse.expires_in,
        token_type: tokenResponse.token_type,
        scope: tokenResponse.scope,
        generated_at: new Date().toISOString(),
        user: userInfo
      };

      await fs.writeFile(
        'databricks_token.json',
        JSON.stringify(tokenData, null, 2)
      );

      log(`💾 Token saved to: databricks_token.json`, colors.green);
    }

    log('\n' + '='.repeat(60), colors.bright);
    log('  ✅ Token Generation Complete!', colors.green);
    log('='.repeat(60) + '\n', colors.bright);

    return tokenResponse;
  } catch (error) {
    log(`\n❌ Error: ${error.message}`, colors.red);
    log(`\nPlease check your .env configuration and try again.\n`, colors.yellow);
    process.exit(1);
  }
}

// Run if executed directly
if (require.main === module) {
  generateToken();
}

module.exports = { generateToken };
