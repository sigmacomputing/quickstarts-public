// This script responds with a bearer token using the encrypted authentication system
// It integrates with the portal's encrypted credential storage instead of using .env files

const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const axios = require('axios');

// Constants for encrypted credential storage (matching keyStorage.ts)
const ALGORITHM = 'aes-256-cbc';
const KEY_LENGTH = 32;

/**
 * Generate machine-specific encryption key (matches keyStorage.ts)
 */
function getMachineKey() {
  const machineInfo = [
    os.hostname(),
    os.platform(),
    os.arch(),
    os.type()
  ].join('|');
  
  return crypto.scryptSync(machineInfo, 'sigma-portal-salt', KEY_LENGTH);
}

/**
 * Get the sigma portal config directory (matches keyStorage.ts)
 */
function getKeysDirectory() {
  const platform = os.platform();
  let configDir;
  
  if (platform === 'win32') {
    configDir = process.env.APPDATA || os.tmpdir();
  } else if (platform === 'darwin') {
    configDir = path.join(os.homedir(), 'Library', 'Application Support');
  } else {
    configDir = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config');
  }
  
  return path.join(configDir, '.sigma-portal');
}

/**
 * Decrypt stored credentials (matches keyStorage.ts)
 */
function decryptCredentials(encryptedData) {
  try {
    const key = getMachineKey();
    const { iv, encrypted } = JSON.parse(encryptedData);
    
    const decipher = crypto.createDecipheriv(ALGORITHM, key, Buffer.from(iv, 'hex'));
    
    let decrypted = decipher.update(encrypted, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    
    const parsed = JSON.parse(decrypted);
    
    return {
      clientId: parsed.clientId,
      clientSecret: parsed.clientSecret,
      baseURL: parsed.baseURL || 'https://aws-api.sigmacomputing.com/v2',
      authURL: parsed.authURL || 'https://aws-api.sigmacomputing.com/v2/auth/token'
    };
  } catch (error) {
    console.error('Failed to decrypt credentials:', error);
    return null;
  }
}

/**
 * Get stored credentials from encrypted storage
 */
function getStoredCredentials(configName) {
  try {
    const keysFile = path.join(getKeysDirectory(), 'encrypted-keys.json');
    
    console.log('=== AUTH SCRIPT CONFIG SELECTION DEBUG ===');
    console.log('Requested config name:', configName);
    console.log('Keys file path:', keysFile);
    
    if (!fs.existsSync(keysFile)) {
      console.log('Keys file does not exist');
      return null;
    }
    
    const allCredentials = JSON.parse(fs.readFileSync(keysFile, 'utf-8'));
    console.log('Available configs:', Object.keys(allCredentials).filter(k => k !== '_metadata'));
    console.log('Default set in metadata:', allCredentials._metadata?.defaultSet);
    
    // Use provided name, or default, or first available
    let targetName = configName;
    if (!targetName) {
      targetName = allCredentials._metadata?.defaultSet || Object.keys(allCredentials).find(k => k !== '_metadata');
      console.log('No config name provided, using:', targetName);
    } else {
      console.log('Using provided config name:', targetName);
    }
    
    if (!targetName || !allCredentials[targetName]) {
      console.log('Target config not found:', targetName);
      return null;
    }
    
    const decrypted = decryptCredentials(allCredentials[targetName].encrypted);
    if (decrypted) {
      console.log('Successfully decrypted config for:', targetName);
      console.log('ClientId starts with:', decrypted.clientId?.substring(0, 8));
      console.log('BaseURL:', decrypted.baseURL);
    }
    
    return decrypted;
  } catch (error) {
    console.error('Failed to retrieve stored credentials:', error);
    return null;
  }
}

/**
 * Check for cached valid token
 */
function getCachedToken(clientId) {
  try {
    const tempDir = os.tmpdir();
    const configHash = clientId ? clientId.substring(0, 8) : 'default';
    const tokenFile = path.join(tempDir, `sigma-portal-token-${configHash}.json`);
    
    if (!fs.existsSync(tokenFile)) {
      return null;
    }
    
    const tokenData = JSON.parse(fs.readFileSync(tokenFile, 'utf8'));
    const now = Date.now();
    
    // Check if token is still valid
    if (tokenData.expiresAt && now < tokenData.expiresAt) {
      // Update last accessed time
      tokenData.lastAccessed = Date.now();
      fs.writeFileSync(tokenFile, JSON.stringify(tokenData));
      
      return tokenData.token;
    } else {
      // Remove expired token
      fs.unlinkSync(tokenFile);
      return null;
    }
  } catch (error) {
    return null;
  }
}

/**
 * Cache a new token
 */
function cacheToken(token, clientId, expiresIn = 3600, baseURL = null, authURL = null) {
  try {
    const tempDir = os.tmpdir();
    const configHash = clientId ? clientId.substring(0, 8) : 'default';
    const tokenFile = path.join(tempDir, `sigma-portal-token-${configHash}.json`);
    
    const tokenData = {
      token: token,
      clientId: clientId,
      baseURL: baseURL, // Store baseURL with token for race condition prevention
      authURL: authURL, // Store authURL with token for completeness
      createdAt: Date.now(),
      lastAccessed: Date.now(),
      expiresAt: Date.now() + (expiresIn * 1000) // Convert to milliseconds
    };
    
    fs.writeFileSync(tokenFile, JSON.stringify(tokenData));
  } catch (error) {
    console.warn('Failed to cache token:', error);
  }
}

/**
 * Get bearer token using new authentication system
 */
async function getBearerToken(configName) {
  // Allow configName to be passed via environment variable for portal integration
  const envConfigName = process.env.CONFIG_NAME;
  if (!configName && envConfigName) {
    configName = envConfigName;
    console.log('Using config name from environment:', configName);
  }
  try {
    // Get stored credentials
    const credentials = getStoredCredentials(configName);
    
    if (!credentials) {
      throw new Error('No authentication configuration found. Please use the portal to set up authentication first.');
    }
    
    // Check for cached valid token first
    const cachedToken = getCachedToken(credentials.clientId);
    if (cachedToken) {
      console.log('Using cached authentication token.');
      return cachedToken;
    }
    
    console.log('No cached token found. Script will authenticate normally.');
    
    // Request new token
    const requestData = new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: credentials.clientId,
      client_secret: credentials.clientSecret,
    });

    console.log(`URL sent to Sigma: ${credentials.authURL}`);

    const response = await axios.post(credentials.authURL, requestData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });

    const token = response.data.access_token;
    const expiresIn = response.data.expires_in || 3600;
    
    console.log('Bearer token obtained successfully:', response.data.access_token);
    
    // Cache the new token with baseURL and authURL to prevent race conditions
    cacheToken(token, credentials.clientId, expiresIn, credentials.baseURL, credentials.authURL);
    
    return token;
  } catch (error) {
    console.error('Error obtaining Bearer token:', error.response ? error.response.data : error.message);
    return null;
  }
}

// Check if this script is being run directly
if (require.main === module) {
  getBearerToken().then(token => {
    console.log('Token acquired:', token);
  }).catch(error => {
    console.error('Failed to acquire token:', error);
  });
}

// Export the getBearerToken function
module.exports = getBearerToken;