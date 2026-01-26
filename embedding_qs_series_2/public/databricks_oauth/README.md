# Sigma Embedding with Databricks OAuth 2.0 (PKCE)

This application demonstrates secure embedding of Sigma Analytics dashboards using **Databricks connection-level OAuth** with **PKCE** (Proof Key for Code Exchange). Users authenticate with their Databricks credentials, and queries run with their individual permissions.

## Features

- **Connection-Level OAuth**: Each user authenticates with their own Databricks credentials
- **PKCE Security**: Protection against authorization code interception attacks
- **Automatic Token Refresh**: Seamless token renewal before expiration
- **Session Management**: Secure server-side session storage
- **User-Level Permissions**: Queries execute with authenticated user's Databricks permissions
- **CLI Mode**: Standalone token generation for testing
- **Web Application Mode**: Full Express.js server with OAuth flow

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Browser   │ ◄─────► │ Express App  │ ◄─────► │ Databricks  │
└─────────────┘         └──────────────┘         └─────────────┘
                              │
                              │ Encrypted Token
                              ▼
                        ┌──────────────┐
                        │    Sigma     │
                        │  Analytics   │
                        └──────────────┘
```

### OAuth Flow

1. User initiates login → Generates PKCE code challenge
2. Redirect to Databricks → User authenticates
3. Databricks callback → Exchange code + verifier for tokens
4. Store tokens in session → Encrypt access token
5. Embed in Sigma JWT → Dashboard loads with user permissions

## Prerequisites

- Node.js 16+ installed
- Databricks workspace with OAuth configured
- Sigma organization with embedding enabled
- Databricks connection in Sigma configured for OAuth

## Installation

1. **Navigate to the project root directory**
   ```bash
   cd embedding_qs_series_2
   ```

2. **Install dependencies** (if not already installed)
   ```bash
   npm install
   ```

3. **Configure centralized `.env` file**

   This QuickStart uses the centralized `.env` file at `/embedding_qs_series_2/.env`

   Add your Databricks OAuth configuration to the existing `.env` file (see Configuration section below)

## Configuration

This QuickStart uses the **centralized `.env` file** located at `embedding_qs_series_2/.env` (shared with other QuickStarts).

### Databricks OAuth Setup

1. **Navigate to Databricks Admin Console** → Settings → OAuth

2. **Create OAuth Application**
   - Name: `Sigma Embedding`
   - Redirect URI: `http://localhost:3000/auth/databricks/callback`
   - Scopes: `all-apis` and `offline_access`

3. **Copy credentials** to the centralized `.env` file

### Sigma Embedding Setup

1. **Go to Sigma Admin** → Developer Access

2. **Use existing shared embed credentials** (CLIENT_ID and SECRET)
   - These are already configured at the top of the `.env` file

3. **Create Databricks connection** with OAuth enabled
   - Admin → Connections → Your Databricks Connection
   - Enable "Connection-level OAuth"
   - Copy Connection ID from URL

4. **Create a Sigma workbook** using your Databricks connection

### Centralized .env Configuration

Add these variables to the `embedding_qs_series_2/.env` file:

```env
###############################################
# Embedding 16: Databricks OAuth (Connection-Level)
###############################################

# Sigma Embedding Settings (override defaults if needed)
DATABRICKS_OAUTH_BASE_URL=https://app.sigmacomputing.com/your-org/workbook/workbook-id
DATABRICKS_OAUTH_EMAIL=
DATABRICKS_OAUTH_ACCOUNT_TYPE=View
DATABRICKS_OAUTH_TEAMS=

# Databricks OAuth Configuration
DATABRICKS_HOST=https://adb-1234567890123456.2.azuredatabricks.net
DATABRICKS_ACCOUNT_ID=
DATABRICKS_OAUTH_CLIENT_ID=your-oauth-client-id
DATABRICKS_OAUTH_CLIENT_SECRET=your-oauth-client-secret
DATABRICKS_REDIRECT_URI=http://localhost:3000/auth/databricks/callback
DATABRICKS_AUTH_LEVEL=workspace

# Databricks Connection ID in Sigma
DATABRICKS_CONNECTION_ID=your-connection-id

# Session Secret
DATABRICKS_SESSION_SECRET=change-this-to-random-string-in-production

# Optional: Save token to file in CLI mode
DATABRICKS_SAVE_TOKEN_TO_FILE=false
```

**Note:** The shared `CLIENT_ID` and `SECRET` at the top of the `.env` file are used for Sigma JWT signing.

## Usage

### Web Application Mode

Start the Express server from the databricks_oauth directory:

```bash
cd public/databricks_oauth
npm start
```

Visit `http://localhost:3000` and:
1. Click "Login with Databricks"
2. Authenticate with your Databricks credentials
3. View embedded Sigma dashboard with your permissions

### CLI Mode (Standalone Token Generation)

Generate tokens for testing:

```bash
cd public/databricks_oauth
npm run token:cli
```

This will:
1. Open browser for Databricks authentication
2. Generate PKCE challenge and exchange for tokens
3. Display token information
4. Optionally save to `databricks_token.json`

**Note:** The CLI mode uses the same centralized `.env` configuration as the web application.

## File Structure

```
databricks_oauth/
├── server.js                           # Express server with OAuth routes
├── databricks-token-cli.js             # Standalone CLI token generator
├── package.json                        # Dependencies and scripts
├── .env.example                        # Environment template
├── helpers/
│   ├── pkce.js                        # PKCE utilities (RFC 7636)
│   ├── databricks-auth.js             # Databricks OAuth functions
│   └── embed-api-oauth.js             # Sigma JWT signing with encrypted tokens
├── index.html                         # Dashboard page (authenticated)
└── login.html                         # Login page
```

## Key Components

### PKCE Implementation (`helpers/pkce.js`)

Generates cryptographically secure code verifiers and SHA-256 challenges per RFC 7636.

### Databricks Auth (`helpers/databricks-auth.js`)

- `getAuthorizationUrl()`: Builds OAuth authorization URL
- `exchangeCodeForToken()`: Exchanges auth code for access/refresh tokens
- `refreshAccessToken()`: Refreshes expired tokens
- `getCurrentUser()`: Fetches user info from Databricks SCIM API

### Sigma Embedding (`helpers/embed-api-oauth.js`)

- `encryptToken()`: AES-256 encryption of Databricks access token
- `generateSignedUrl()`: Creates signed Sigma embed URL with encrypted OAuth token in JWT

### Server Routes (`server.js`)

| Route | Description |
|-------|-------------|
| `GET /` | Redirects to login |
| `GET /auth/databricks/login` | Initiates OAuth flow |
| `GET /auth/databricks/callback` | Handles OAuth callback |
| `GET /dashboard` | Dashboard page (requires auth) |
| `GET /api/embed-url` | Returns signed Sigma embed URL |
| `GET /logout` | Destroys session |
| `GET /health` | Health check |

## Security Features

- **PKCE**: Protects against code interception
- **State Parameter**: CSRF protection
- **Session Storage**: Server-side token storage (not exposed to client)
- **Token Encryption**: AES-256-CBC encryption for Databricks tokens
- **HTTPS Ready**: Configurable for production with HTTPS
- **Auto-Refresh**: Tokens refreshed 5 minutes before expiry

## Troubleshooting

### "Missing required environment variables"

Ensure `.env` file exists and contains all required variables from `.env.example`.

### "State mismatch - possible CSRF attack"

Clear browser cookies and restart the server. This usually happens during development when sessions are lost.

### "Token exchange failed"

Verify:
- Databricks OAuth client ID and secret are correct
- Redirect URI matches Databricks OAuth app configuration exactly
- `DATABRICKS_HOST` is correct

### "Failed to generate embed URL"

Check:
- `SIGMA_BASE_URL` points to a valid workbook
- `SIGMA_CONNECTION_ID` is correct (from connection URL in Sigma Admin)
- Sigma connection has OAuth enabled

### Embed shows "No data" or permission errors

Verify:
- Authenticated Databricks user has permissions to query the data
- Sigma workbook uses the correct Databricks connection
- Connection-level OAuth is enabled in Sigma connection settings

## Production Deployment

For production use:

1. **Enable HTTPS**: Set `cookie.secure = true` in `server.js`
2. **Change SESSION_SECRET**: Use a strong random string
3. **Update Redirect URI**: Add production URL to Databricks OAuth app
4. **Environment Variables**: Use secure secret management (not `.env` files)
5. **Rate Limiting**: Add rate limiting middleware
6. **Logging**: Implement production logging (e.g., Winston)
7. **Error Handling**: Add comprehensive error handling and monitoring

## Additional Resources

- [Sigma Embedding Documentation](https://help.sigmacomputing.com/docs/embedding)
- [Databricks OAuth Documentation](https://docs.databricks.com/dev-tools/auth.html#oauth-2-0)
- [OAuth 2.0 with PKCE (RFC 7636)](https://datatracker.ietf.org/doc/html/rfc7636)
- [Sigma QuickStarts](https://quickstarts.sigmacomputing.com/)

## License

MIT
