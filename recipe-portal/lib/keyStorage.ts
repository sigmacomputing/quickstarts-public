import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import os from 'os';

// File path for encrypted key storage - use system config directory
// This ensures keys are stored outside project directory and won't be committed to git
const getKeysDirectory = () => {
  const platform = os.platform();
  let configDir;
  
  if (platform === 'win32') {
    configDir = process.env.APPDATA || os.tmpdir();
  } else if (platform === 'darwin') {
    configDir = path.join(os.homedir(), 'Library', 'Application Support');
  } else {
    configDir = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config');
  }
  
  const sigmaDir = path.join(configDir, '.sigma-portal');
  
  // Ensure directory exists
  if (!fs.existsSync(sigmaDir)) {
    fs.mkdirSync(sigmaDir, { recursive: true });
  }
  
  return sigmaDir;
};

const KEYS_CACHE_FILE = path.join(getKeysDirectory(), 'encrypted-keys.json');

// Algorithm and key derivation
const ALGORITHM = 'aes-256-cbc';
const KEY_LENGTH = 32; // 256 bits

/**
 * Generate a machine-specific encryption key
 * Uses system information to create a consistent key per machine
 */
function getMachineKey(): Buffer {
  const machineInfo = [
    os.hostname(),
    os.platform(),
    os.arch(),
    os.type()
  ].join('|');
  
  // Create a deterministic key from machine info
  return crypto.scryptSync(machineInfo, 'sigma-portal-salt', KEY_LENGTH);
}

/**
 * Encrypt API configuration (credentials + server settings)
 */
function encryptCredentials(clientId: string, clientSecret: string, baseURL?: string, authURL?: string): string {
  const key = getMachineKey();
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  
  const data = JSON.stringify({ 
    clientId, 
    clientSecret,
    baseURL: baseURL || 'https://aws-api.sigmacomputing.com/v2',
    authURL: authURL || 'https://aws-api.sigmacomputing.com/v2/auth/token'
  });
  let encrypted = cipher.update(data, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  
  return JSON.stringify({
    iv: iv.toString('hex'),
    encrypted
  });
}

/**
 * Decrypt API configuration (credentials + server settings)
 */
function decryptCredentials(encryptedData: string): { clientId: string; clientSecret: string; baseURL: string; authURL: string } | null {
  try {
    const key = getMachineKey();
    const { iv, encrypted } = JSON.parse(encryptedData);
    
    const decipher = crypto.createDecipheriv(ALGORITHM, key, Buffer.from(iv, 'hex'));
    
    let decrypted = decipher.update(encrypted, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    
    const parsed = JSON.parse(decrypted);
    
    // Ensure backward compatibility with old format
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
 * Store API configuration (credentials + server settings) encrypted on disk
 */
export async function storeCredentials(clientId: string, clientSecret: string, name: string = 'default', baseURL?: string, authURL?: string): Promise<boolean> {
  try {
    // Read existing credential sets
    let allCredentials: Record<string, any> = {};
    if (fs.existsSync(KEYS_CACHE_FILE)) {
      const existingData = fs.readFileSync(KEYS_CACHE_FILE, 'utf-8');
      allCredentials = JSON.parse(existingData);
    }
    
    const encryptedData = encryptCredentials(clientId, clientSecret, baseURL, authURL);
    
    // Store this set with its name
    allCredentials[name] = {
      encrypted: encryptedData,
      storedAt: Date.now(),
      version: '2.0' // Updated version to include server settings
    };
    
    // Mark as default if it's the first one
    if (!allCredentials._metadata) {
      allCredentials._metadata = { defaultSet: name };
    }
    
    fs.writeFileSync(KEYS_CACHE_FILE, JSON.stringify(allCredentials, null, 2));
    return true;
  } catch (error) {
    console.error('Failed to store credentials:', error);
    return false;
  }
}

/**
 * Retrieve and decrypt stored API configuration (credentials + server settings)
 */
export async function getStoredCredentials(name?: string): Promise<{ clientId: string; clientSecret: string; baseURL: string; authURL: string } | null> {
  try {
    if (!fs.existsSync(KEYS_CACHE_FILE)) {
      return null;
    }
    
    const allCredentials = JSON.parse(fs.readFileSync(KEYS_CACHE_FILE, 'utf-8'));
    
    // Use provided name, or default, or first available
    let targetName = name;
    if (!targetName) {
      targetName = allCredentials._metadata?.defaultSet || Object.keys(allCredentials).find(k => k !== '_metadata');
    }
    
    if (!targetName || !allCredentials[targetName]) {
      return null;
    }
    
    const decrypted = decryptCredentials(allCredentials[targetName].encrypted);
    return decrypted;
  } catch (error) {
    console.error('Failed to retrieve stored credentials:', error);
    return null;
  }
}

/**
 * Check if credentials are stored locally
 */
export async function hasStoredCredentials(): Promise<boolean> {
  try {
    return fs.existsSync(KEYS_CACHE_FILE);
  } catch (error) {
    return false;
  }
}

/**
 * Get list of stored credential set names
 */
export async function getStoredCredentialNames(): Promise<string[]> {
  try {
    if (!fs.existsSync(KEYS_CACHE_FILE)) {
      return [];
    }
    
    const allCredentials = JSON.parse(fs.readFileSync(KEYS_CACHE_FILE, 'utf-8'));
    return Object.keys(allCredentials).filter(k => k !== '_metadata');
  } catch (error) {
    console.error('Failed to get credential names:', error);
    return [];
  }
}

/**
 * Get the default credential set name
 */
export async function getDefaultCredentialSetName(): Promise<string | null> {
  try {
    if (!fs.existsSync(KEYS_CACHE_FILE)) {
      return null;
    }
    
    const allCredentials = JSON.parse(fs.readFileSync(KEYS_CACHE_FILE, 'utf-8'));
    return allCredentials._metadata?.defaultSet || null;
  } catch (error) {
    return null;
  }
}

/**
 * Set the default credential set
 */
export async function setDefaultCredentialSet(name: string): Promise<boolean> {
  try {
    if (!fs.existsSync(KEYS_CACHE_FILE)) {
      return false;
    }
    
    const allCredentials = JSON.parse(fs.readFileSync(KEYS_CACHE_FILE, 'utf-8'));
    if (!allCredentials[name]) {
      return false; // Set doesn't exist
    }
    
    if (!allCredentials._metadata) {
      allCredentials._metadata = {};
    }
    allCredentials._metadata.defaultSet = name;
    
    fs.writeFileSync(KEYS_CACHE_FILE, JSON.stringify(allCredentials, null, 2));
    return true;
  } catch (error) {
    console.error('Failed to set default credential set:', error);
    return false;
  }
}

/**
 * Clear stored credentials (optionally specific set)
 */
export async function clearStoredCredentials(name?: string): Promise<boolean> {
  try {
    if (!fs.existsSync(KEYS_CACHE_FILE)) {
      return true;
    }
    
    if (!name) {
      // Clear all
      fs.unlinkSync(KEYS_CACHE_FILE);
      return true;
    }
    
    // Clear specific set
    const allCredentials = JSON.parse(fs.readFileSync(KEYS_CACHE_FILE, 'utf-8'));
    if (allCredentials[name]) {
      delete allCredentials[name];
      
      // Update default if we deleted it
      if (allCredentials._metadata?.defaultSet === name) {
        const remainingNames = Object.keys(allCredentials).filter(k => k !== '_metadata');
        allCredentials._metadata.defaultSet = remainingNames[0] || null;
      }
      
      fs.writeFileSync(KEYS_CACHE_FILE, JSON.stringify(allCredentials, null, 2));
    }
    
    return true;
  } catch (error) {
    console.error('Failed to clear stored credentials:', error);
    return false;
  }
}