// server.js
// Express server for Sigma embedding with Databricks OAuth 2.0 (PKCE)

const express = require('express');
const session = require('express-session');
const dotenv = require('dotenv');
const path = require('path');

const {
  getAuthorizationUrl,
  exchangeCodeForToken,
  refreshAccessToken,
  getCurrentUser,
  generatePKCE,
  generateState
} = require('./helpers/databricks-auth');

const { generateSignedUrl } = require('./helpers/embed-api-oauth');

// Load centralized .env file from parent directory
dotenv.config({ path: path.resolve(__dirname, '../../.env') });

const app = express();
const PORT = process.env.PORT || 3000;

// Session middleware for storing OAuth state and tokens
app.use(session({
  secret: process.env.DATABRICKS_SESSION_SECRET || 'your-secret-key-change-in-production',
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: false, // Set to true in production with HTTPS
    httpOnly: true,
    maxAge: 24 * 60 * 60 * 1000 // 24 hours
  }
}));

// Serve static files (HTML, CSS, JS)
app.use(express.static(path.join(__dirname)));

// Middleware to check if user is authenticated
function requireAuth(req, res, next) {
  if (!req.session.databricksAccessToken) {
    return res.redirect('/login.html');
  }
  next();
}

// Middleware to refresh token if expired or about to expire
async function refreshTokenIfNeeded(req, res, next) {
  if (!req.session.databricksAccessToken) {
    return next();
  }

  const now = Date.now();
  const tokenExpiresAt = req.session.tokenExpiresAt || 0;

  // Refresh if token expires in less than 5 minutes
  if (tokenExpiresAt - now < 5 * 60 * 1000) {
    console.log('[Server] Token expiring soon, refreshing...');

    try {
      const tokenResponse = await refreshAccessToken({
        databricksHost: process.env.DATABRICKS_HOST,
        accountId: process.env.DATABRICKS_ACCOUNT_ID,
        clientId: process.env.DATABRICKS_OAUTH_CLIENT_ID,
        clientSecret: process.env.DATABRICKS_OAUTH_CLIENT_SECRET,
        authLevel: process.env.DATABRICKS_AUTH_LEVEL || 'workspace',
        refreshToken: req.session.databricksRefreshToken
      });

      // Update session with new tokens
      req.session.databricksAccessToken = tokenResponse.access_token;
      req.session.databricksRefreshToken = tokenResponse.refresh_token;
      req.session.tokenExpiresAt = Date.now() + (tokenResponse.expires_in * 1000);

      console.log('[Server] Token refreshed successfully');
    } catch (error) {
      console.error('[Server] Token refresh failed:', error.message);
      // Clear session and redirect to login
      req.session.destroy();
      return res.redirect('/login.html?error=token_refresh_failed');
    }
  }

  next();
}

/**
 * Route: GET /
 * Redirects to login page
 */
app.get('/', (req, res) => {
  res.redirect('/login.html');
});

/**
 * Route: GET /auth/databricks/login
 * Initiates Databricks OAuth flow
 */
app.get('/auth/databricks/login', (req, res) => {
  try {
    // Generate PKCE pair and state
    const { codeVerifier, codeChallenge } = generatePKCE();
    const state = generateState();

    // Store in session for callback verification
    req.session.codeVerifier = codeVerifier;
    req.session.state = state;

    // Build authorization URL
    const authUrl = getAuthorizationUrl({
      databricksHost: process.env.DATABRICKS_HOST,
      accountId: process.env.DATABRICKS_ACCOUNT_ID,
      clientId: process.env.DATABRICKS_OAUTH_CLIENT_ID,
      redirectUri: process.env.DATABRICKS_REDIRECT_URI,
      authLevel: process.env.DATABRICKS_AUTH_LEVEL || 'workspace',
      codeChallenge,
      state
    });

    console.log('[Server] Redirecting to Databricks OAuth:', authUrl);

    // Redirect user to Databricks authorization page
    res.redirect(authUrl);
  } catch (error) {
    console.error('[Server] Login initiation failed:', error.message);
    res.status(500).send('Failed to initiate OAuth login');
  }
});

/**
 * Route: GET /auth/databricks/callback
 * Handles OAuth callback from Databricks
 */
app.get('/auth/databricks/callback', async (req, res) => {
  try {
    const { code, state, error } = req.query;

    // Check for OAuth errors
    if (error) {
      console.error('[Server] OAuth error:', error);
      return res.redirect('/login.html?error=' + encodeURIComponent(error));
    }

    // Validate state to prevent CSRF
    if (state !== req.session.state) {
      console.error('[Server] State mismatch - possible CSRF attack');
      return res.status(400).send('Invalid state parameter');
    }

    // Exchange authorization code for tokens
    const tokenResponse = await exchangeCodeForToken({
      databricksHost: process.env.DATABRICKS_HOST,
      accountId: process.env.DATABRICKS_ACCOUNT_ID,
      clientId: process.env.DATABRICKS_OAUTH_CLIENT_ID,
      clientSecret: process.env.DATABRICKS_OAUTH_CLIENT_SECRET,
      redirectUri: process.env.DATABRICKS_REDIRECT_URI,
      authLevel: process.env.DATABRICKS_AUTH_LEVEL || 'workspace',
      code,
      codeVerifier: req.session.codeVerifier
    });

    // Get user information from Databricks
    const userInfo = await getCurrentUser(
      tokenResponse.access_token,
      process.env.DATABRICKS_HOST
    );

    // Store tokens and user info in session
    req.session.databricksAccessToken = tokenResponse.access_token;
    req.session.databricksRefreshToken = tokenResponse.refresh_token;
    req.session.tokenExpiresAt = Date.now() + (tokenResponse.expires_in * 1000);
    req.session.userEmail = userInfo.email;
    req.session.userDisplayName = userInfo.displayName;

    // Clear PKCE data
    delete req.session.codeVerifier;
    delete req.session.state;

    console.log('[Server] OAuth callback successful, user:', userInfo.email);

    // Redirect to dashboard
    res.redirect('/dashboard');
  } catch (error) {
    console.error('[Server] OAuth callback failed:', error.message);
    res.redirect('/login.html?error=authentication_failed');
  }
});

/**
 * Route: GET /dashboard
 * Displays embedded Sigma dashboard (requires authentication)
 */
app.get('/dashboard', requireAuth, refreshTokenIfNeeded, (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

/**
 * Route: GET /api/embed-url
 * Generates signed Sigma embed URL with Databricks OAuth token
 */
app.get('/api/embed-url', requireAuth, refreshTokenIfNeeded, async (req, res) => {
  try {
    const { signedUrl, jwt } = await generateSignedUrl(
      req.session.databricksAccessToken,
      req.session.userEmail
    );

    res.json({
      embedUrl: signedUrl,
      jwt: jwt,
      user: {
        email: req.session.userEmail,
        displayName: req.session.userDisplayName
      }
    });
  } catch (error) {
    console.error('[Server] Failed to generate embed URL:', error.message);
    res.status(500).json({ error: 'Failed to generate embed URL' });
  }
});

/**
 * Route: GET /logout
 * Clears session and logs user out
 */
app.get('/logout', (req, res) => {
  req.session.destroy((err) => {
    if (err) {
      console.error('[Server] Logout error:', err);
    }
    res.redirect('/login.html?logged_out=true');
  });
});

/**
 * Route: GET /health
 * Health check endpoint
 */
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    authenticated: !!req.session.databricksAccessToken
  });
});

// Start server
app.listen(PORT, () => {
  console.log('='.repeat(60));
  console.log('Sigma Embedding with Databricks OAuth Server');
  console.log('='.repeat(60));
  console.log(`Server running at: http://localhost:${PORT}`);
  console.log(`Login page: http://localhost:${PORT}/login.html`);
  console.log(`Health check: http://localhost:${PORT}/health`);
  console.log('='.repeat(60));
  console.log(`Databricks Host: ${process.env.DATABRICKS_HOST || 'NOT CONFIGURED'}`);
  console.log(`Auth Level: ${process.env.DATABRICKS_AUTH_LEVEL || 'workspace'}`);
  console.log(`Sigma Base URL: ${process.env.DATABRICKS_OAUTH_BASE_URL || 'NOT CONFIGURED'}`);
  console.log('='.repeat(60));
});
