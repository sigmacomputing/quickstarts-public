import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import os from 'os';

// Get current token info using same logic as /api/token
function getCurrentTokenInfo() {
  try {
    const tempDir = os.tmpdir();
    const files = fs.readdirSync(tempDir);
    const tokenFiles = files.filter(file => file.startsWith('sigma-portal-token-') && file.endsWith('.json'));
    
    console.log('=== EXECUTE ROUTE TOKEN DEBUGGING ===');
    console.log('Found token files:', tokenFiles);
    
    let namedConfigTokens = [];
    let defaultToken = null;
    
    for (const file of tokenFiles) {
      try {
        const filePath = path.join(tempDir, file);
        const tokenData = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        const now = Date.now();
        
        // Check if token is still valid (not expired)
        if (tokenData.expiresAt && now < tokenData.expiresAt) {
          const lastAccessTime = tokenData.lastAccessed || tokenData.createdAt;
          console.log(`Token ${file}: clientId=${tokenData.clientId?.substring(0,8) || 'default'}, fullLength=${tokenData.clientId?.length || 0}, createdAt=${new Date(tokenData.createdAt)}, lastAccessed=${tokenData.lastAccessed ? new Date(tokenData.lastAccessed) : 'none'}, lastAccessTime=${lastAccessTime}`);
          
          const tokenInfo = {
            hasValidToken: true,
            token: tokenData.token,
            clientId: tokenData.clientId, // Use full clientId for environment variables
            baseURL: tokenData.baseURL,
            authURL: tokenData.authURL,
            filePath: filePath,
            lastAccessTime: lastAccessTime
          };
          
          // Use same classification logic as /api/token
          if (tokenData.clientId && tokenData.clientId.length > 8) {
            namedConfigTokens.push(tokenInfo);
            console.log(`  -> This is a named config token (full clientId: ${tokenData.clientId.length} chars)`);
          } else {
            defaultToken = tokenInfo;
            console.log(`  -> This is the default token (clientId: ${tokenData.clientId || 'none'})`);
          }
        } else {
          console.log(`Token ${file} is expired, removing...`);
          // Token expired, remove file
          fs.unlinkSync(filePath);
        }
      } catch (err) {
        console.warn(`Failed to read token file ${file}:`, err);
        // Skip invalid token files
      }
    }
    
    console.log(`Found ${namedConfigTokens.length} named config tokens and ${defaultToken ? 1 : 0} default tokens`);
    
    // Prioritize named config tokens over default token (same as /api/token)
    if (namedConfigTokens.length > 0) {
      // Sort named config tokens by most recent access time
      namedConfigTokens.sort((a, b) => b.lastAccessTime - a.lastAccessTime);
      console.log('Named config tokens sorted by lastAccessTime:');
      namedConfigTokens.forEach((token, index) => {
        console.log(`  ${index + 1}. ${token.clientId?.substring(0,8)}... - ${new Date(token.lastAccessTime)}`);
      });
      console.log(`  -> Selected most recent named config token: ${namedConfigTokens[0].clientId?.substring(0,8)}`);
      return namedConfigTokens[0];
    } else if (defaultToken) {
      console.log(`  -> No named config tokens, using default token`);
      return defaultToken;
    }
    
    console.log('  -> No valid tokens found');
    return null;
  } catch (error) {
    console.error('Error in getCurrentTokenInfo:', error);
    return null;
  }
}

export async function POST(request: Request) {
  try {
    const { filePath, envVariables } = await request.json();
    
    console.log('=== EXECUTE API DEBUG ===');
    console.log('Received filePath:', filePath);
    console.log('Process CWD:', process.cwd());
    console.log('Environment variables CLIENT_ID:', envVariables?.CLIENT_ID);
    console.log('Environment variables keys:', Object.keys(envVariables || {}));
    
    if (!filePath) {
      return NextResponse.json(
        { error: 'File path is required' },
        { status: 400 }
      );
    }

    // Security check: ensure the file is within the recipes directory
    const recipesPath = path.join(process.cwd(), 'recipes');
    
    // Force the file path to be relative to our current working directory
    const fileName = path.basename(filePath);
    const relativePath = filePath.replace(/^.*recipes\//, 'recipes/');
    const resolvedPath = path.join(process.cwd(), relativePath);
    const resolvedRecipesPath = path.resolve(recipesPath);
    
    console.log('Recipes path:', recipesPath);
    console.log('Relative path:', relativePath);
    console.log('Resolved path:', resolvedPath);
    console.log('Resolved recipes path:', resolvedRecipesPath);
    
    if (!resolvedPath.startsWith(resolvedRecipesPath)) {
      return NextResponse.json(
        { error: 'Access denied: File must be within recipes directory' },
        { status: 403 }
      );
    }

    // Check if file exists
    if (!fs.existsSync(resolvedPath)) {
      return NextResponse.json(
        { error: 'File not found' },
        { status: 404 }
      );
    }

    // Create temporary .env file with provided variables
    const tempEnvPath = path.join(os.tmpdir(), `.env-${Date.now()}`);
    let envContent = '';
    
    if (envVariables && typeof envVariables === 'object') {
      for (const [key, value] of Object.entries(envVariables)) {
        if (typeof value === 'string') {
          envContent += `${key}=${value}\n`;
        }
      }
    }
    
    // Add common variables if not provided
    if (envVariables && !envVariables.authURL && (envVariables.CLIENT_ID || envVariables.SECRET)) {
      envContent += `authURL=https://aws-api.sigmacomputing.com/v2/auth/token\n`;
    }
    if (envVariables && !envVariables.baseURL && (envVariables.CLIENT_ID || envVariables.SECRET)) {
      envContent += `baseURL=https://aws-api.sigmacomputing.com/v2\n`;
    }
    
    // Add the path to the env file in the content
    envContent += `ENV_FILE_PATH=${tempEnvPath}\n`;
    
    // Use the same token selection logic as /api/token to get the current config  
    const currentTokenInfo = getCurrentTokenInfo();
    console.log('Current token info:', currentTokenInfo);
    
    // Auto-populate authentication variables from current token if not explicitly provided or empty
    if (currentTokenInfo && (!envVariables || !envVariables.CLIENT_ID || envVariables.CLIENT_ID.trim() === '')) {
      // Replace empty CLIENT_ID with the populated one
      envContent = envContent.replace(/^CLIENT_ID=\s*$/m, `CLIENT_ID=${currentTokenInfo.clientId}`);
      console.log('Auto-populated CLIENT_ID from token:', currentTokenInfo.clientId?.substring(0,8) + '...');
    }
    if (currentTokenInfo && (!envVariables || !envVariables.baseURL || envVariables.baseURL.trim() === '')) {
      // Replace empty baseURL with the populated one  
      envContent = envContent.replace(/^baseURL=\s*$/m, `baseURL=${currentTokenInfo.baseURL}`);
      console.log('Auto-populated baseURL from token:', currentTokenInfo.baseURL);
    }
    if (currentTokenInfo && (!envVariables || !envVariables.authURL || envVariables.authURL.trim() === '')) {
      // Replace empty authURL with the populated one
      envContent = envContent.replace(/^authURL=\s*$/m, `authURL=${currentTokenInfo.authURL}`);
      console.log('Auto-populated authURL from token:', currentTokenInfo.authURL);
    }

    fs.writeFileSync(tempEnvPath, envContent);
    
    // Debug: Log the final environment file content
    console.log('=== ENVIRONMENT FILE CONTENT ===');
    console.log(envContent);
    console.log('=== END ENVIRONMENT FILE ===');
    
    // Execute the script with timeout  
    const output = await executeScript(resolvedPath, tempEnvPath, currentTokenInfo?.clientId);
    
    // Clean up temp file
    try {
      fs.unlinkSync(tempEnvPath);
    } catch (err) {
      console.warn('Failed to cleanup temp env file:', err);
    }


    return NextResponse.json({
      output: output.stdout,
      error: output.stderr,
      success: output.success,
      timestamp: new Date().toISOString(),
      httpStatus: output.success ? 200 : 500,
      httpStatusText: output.success ? 'OK' : 'Internal Server Error'
    });
    
  } catch (error) {
    console.error('Error executing script:', error);
    return NextResponse.json(
      { error: 'Failed to execute script' },
      { status: 500 }
    );
  }
}

function executeScript(scriptPath: string, envFilePath: string, clientId: string | null = null): Promise<{
  stdout: string;
  stderr: string;
  success: boolean;
}> {
  return new Promise((resolve) => {
    // Always use the current working directory as the base for recipes
    const recipesRoot = path.join(process.cwd(), 'recipes');
    console.log('Process CWD:', process.cwd());
    console.log('Recipes Root:', recipesRoot);
    console.log('Script Path:', scriptPath);
    
    // Create a wrapper script that handles module resolution and environment setup
    const scriptName = path.basename(scriptPath);
    const isMasterScript = scriptPath.includes('master-script.js');
    const wrapperScript = `
// Change to the recipes directory for proper module resolution
process.chdir('${recipesRoot}');
console.log('Executing from directory:', process.cwd());
console.log('Client ID for token caching: ${clientId || "null"}');

// Import required modules
const fs = require('fs');
const path = require('path');
const os = require('os');

// Set up environment variables from our temp file
const envContent = fs.readFileSync('${envFilePath}', 'utf-8');
const envLines = envContent.split('\\n');

envLines.forEach(line => {
  const match = line.match(/^([^=]+)=(.*)$/);
  if (match) {
    process.env[match[1]] = match[2];
  }
});

// Configuration-specific token caching
function getTokenCacheFile(clientId) {
  // Create a safe filename using first 8 chars of clientId
  const configHash = clientId ? clientId.substring(0, 8) : 'default';
  return path.join(os.tmpdir(), 'sigma-portal-token-' + configHash + '.json');
}

function getCachedToken(preferredClientId = null) {
  try {
    // Look for tokens, prioritizing current config over pure recency
    const tempDir = os.tmpdir();
    const files = fs.readdirSync(tempDir);
    const tokenFiles = files.filter(file => file.startsWith('sigma-portal-token-') && file.endsWith('.json'));
    
    console.log('Found token files:', tokenFiles);
    console.log('Preferred client ID:', preferredClientId);
    
    let preferredToken = null;
    let mostRecentToken = null;
    let mostRecentTime = 0;
    
    for (const file of tokenFiles) {
      try {
        const filePath = path.join(tempDir, file);
        const tokenData = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        const now = Date.now();
        
        console.log('Token ' + file + ':', 'clientId=' + tokenData.clientId + ', createdAt=' + new Date(tokenData.createdAt) + ', lastAccessed=' + new Date(tokenData.lastAccessed || tokenData.createdAt) + ', lastAccessTime=' + (tokenData.lastAccessed || tokenData.createdAt));
        
        // Check if token is still valid (not expired)
        if (tokenData.expiresAt && now < tokenData.expiresAt) {
          const lastAccessTime = tokenData.lastAccessed || tokenData.createdAt;
          
          // Check if this matches the preferred client ID
          if (preferredClientId && tokenData.clientId && tokenData.clientId.startsWith(preferredClientId)) {
            preferredToken = tokenData.token;
            console.log('  -> Found preferred client ID token');
          }
          
          // Track most recent regardless
          if (lastAccessTime > mostRecentTime) {
            mostRecentTime = lastAccessTime;
            mostRecentToken = tokenData.token;
            console.log('  -> This is the most recent token so far');
          }
        } else {
          // Token expired, remove file
          fs.unlinkSync(filePath);
          console.log('  -> Token expired, removed file');
        }
      } catch (err) {
        // Skip invalid token files
        console.log('  -> Invalid token file, skipping');
      }
    }
    
    // Prioritize preferred client token, fallback to most recent
    const selectedToken = preferredToken || mostRecentToken;
    if (selectedToken) {
      if (preferredToken) {
        console.log('Selected preferred client token');
      } else {
        console.log('Selected most recent valid token (no preferred match)');
      }
    }
    
    return selectedToken;
  } catch (error) {
    // Ignore errors, just return null
  }
  return null;
}

function cacheToken(token, clientId = null, baseURL = null, authURL = null) {
  try {
    const TOKEN_CACHE_FILE = getTokenCacheFile(clientId);
    const tokenData = {
      token: token,
      clientId: clientId,
      baseURL: baseURL, // Store baseURL with token for race condition prevention
      authURL: authURL, // Store authURL with token for completeness
      expiresAt: Date.now() + (60 * 60 * 1000), // 1 hour from now
      createdAt: Date.now()
    };
    fs.writeFileSync(TOKEN_CACHE_FILE, JSON.stringify(tokenData));
  } catch (error) {
    console.error('Failed to cache token:', error.message);
  }
}

// Override getBearerToken function for recipes that use cached tokens
async function getBearerToken(clientId = null) {
  // First check for cached token
  const cached = getCachedToken(clientId);
  if (cached) {
    // Don't log anything about tokens in regular recipes
    return cached;
  }
  
  // If no cached token, get a new one silently
  // Temporarily suppress console output when getting token for recipes
  const originalConsoleLog = console.log;
  const originalConsoleError = console.error;
  console.log = () => {}; // Suppress logs
  console.error = () => {}; // Suppress errors
  
  const originalGetBearerToken = require('${recipesRoot}/get-access-token');
  const newToken = await originalGetBearerToken();
  
  // Restore console output
  console.log = originalConsoleLog;
  console.error = originalConsoleError;
  
  if (newToken) {
    cacheToken(newToken, null, process.env.baseURL || 'https://aws-api.sigmacomputing.com/v2', process.env.authURL || 'https://aws-api.sigmacomputing.com/v2/auth/token');
  }
  
  return newToken;
}

// Import and run the original script
try {
  ${scriptName === 'get-access-token.js' ? `
  // Special handling for auth script to show token and cache it
  const originalGetBearerToken = require('${scriptPath}');
  originalGetBearerToken().then((token) => {
    if (token) {
      console.log('✅ Bearer token obtained successfully!');
      console.log('Token:', token);
      console.log('Token will expire in 1 hour');
      console.log('HTTP Status: 200 OK - Authentication successful');
      
      // Cache the token for future use with baseURL and authURL from env
      cacheToken(token, '${clientId || ""}', process.env.baseURL || 'https://aws-api.sigmacomputing.com/v2', process.env.authURL || 'https://aws-api.sigmacomputing.com/v2/auth/token');
    } else {
      console.log('❌ Failed to obtain bearer token');
      process.exit(1);
    }
  }).catch(error => {
    console.error('Authentication failed:', error.message);
    process.exit(1);
  });
  ` : `
  // For regular scripts, check for cached token first
  const cachedToken = getCachedToken('${clientId || ""}');
  
  if (cachedToken) {
    console.log('Using cached authentication token');
    console.log('Cached token: ' + cachedToken.substring(0, 20) + '...');
    
    // Read and modify the script content to use cached token
    const fs = require('fs');
    let scriptContent = fs.readFileSync('${scriptPath}', 'utf-8');
    
    // Replace the getBearerToken import with a function that returns cached token
    const modifiedScript = scriptContent.replace(
      /const getBearerToken = require\\(['"][^'"]*get-access-token['"]\\);/g,
      'const getBearerToken = async () => { console.log("Using cached token from file cache"); return "' + cachedToken + '"; };'
    ).replace(
      /if \\(require\\.main === module\\) \\{([\\s\\S]*?)\\}/g,
      '{ $1 }' // Remove the require.main check so the script always executes
    );
    
    // For master-script.js, we need to override the get-access-token module globally
    // so that when sub-scripts import it, they get the cached token
    const isMasterScript = '${scriptPath}'.includes('master-script.js');
    const finalScript = isMasterScript ? 
      '// Override get-access-token module globally for sub-scripts\\n' +
      'const Module = require(\\'module\\');\\n' +
      'const originalRequire = Module.prototype.require;\\n' +
      '\\n' +
      'Module.prototype.require = function(id) {\\n' +
      '  if (id === \\'../get-access-token\\' || id.endsWith(\\'get-access-token\\')) {\\n' +
      '    return async () => {\\n' +
      '      console.log("Using master script cached token for sub-operation");\\n' +
      '      return "' + cachedToken + '";\\n' +
      '    };\\n' +
      '  }\\n' +
      '  return originalRequire.apply(this, arguments);\\n' +
      '};\\n' +
      '\\n' +
      modifiedScript : modifiedScript;
    
    // Write to a temporary file and require it
    const tempScriptPath = '${scriptPath}' + '.cached.js';
    fs.writeFileSync(tempScriptPath, finalScript);
    
    try {
      // Clear require cache to ensure fresh execution
      delete require.cache[require.resolve(tempScriptPath)];
      require(tempScriptPath);
    } finally {
      // Clean up temp file
      try {
        fs.unlinkSync(tempScriptPath);
      } catch (err) {
        console.warn('Failed to cleanup temp script file:', err);
      }
    }
  } else {
    console.log('No cached token found. Script will authenticate normally.');
    
    // Execute original script
    const script = require('${scriptPath}');
    if (typeof script === 'function') {
      script();
    }
  }
  `}
} catch (error) {
  console.error('Script execution error:', error.message);
  process.exit(1);
}
`;
    
    const tempScriptPath = path.join(os.tmpdir(), `temp-wrapper-${Date.now()}.js`);
    fs.writeFileSync(tempScriptPath, wrapperScript);
    
    // Set timeout based on script type - materialization takes longer
    const isMaterializationScript = scriptPath.includes('initiate-materialization.js');
    const timeout = isMaterializationScript ? 300000 : 30000; // 5 minutes for materialization, 30 seconds for others
    
    const child = spawn('node', [tempScriptPath], {
      cwd: recipesRoot,
      timeout: timeout,
    });

    let stdout = '';
    let stderr = '';

    child.stdout?.on('data', (data) => {
      stdout += data.toString();
    });

    child.stderr?.on('data', (data) => {
      stderr += data.toString();
    });

    child.on('close', (code) => {
      // Clean up temp script file
      try {
        fs.unlinkSync(tempScriptPath);
      } catch (err) {
        console.warn('Failed to cleanup temp script file:', err);
      }
      
      resolve({
        stdout: stdout || 'Script executed successfully (no output)',
        stderr: stderr || '',
        success: code === 0
      });
    });

    child.on('error', (error) => {
      // Clean up temp script file
      try {
        fs.unlinkSync(tempScriptPath);
      } catch (err) {
        console.warn('Failed to cleanup temp script file:', err);
      }
      
      resolve({
        stdout: '',
        stderr: `Execution error: ${error.message}`,
        success: false
      });
    });
  });
}