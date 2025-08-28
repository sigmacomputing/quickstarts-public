import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import os from 'os';

export async function POST(request: Request) {
  try {
    const { filePath, envVariables } = await request.json();
    
    if (!filePath) {
      return NextResponse.json(
        { error: 'File path is required' },
        { status: 400 }
      );
    }

    // Security check: ensure the file is within the sigma-api-recipes directory
    const recipesPath = path.join(process.cwd(), '..', 'sigma-api-recipes');
    const resolvedPath = path.resolve(filePath);
    const resolvedRecipesPath = path.resolve(recipesPath);
    
    if (!resolvedPath.startsWith(resolvedRecipesPath)) {
      return NextResponse.json(
        { error: 'Access denied: File must be within sigma-api-recipes directory' },
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
    
    fs.writeFileSync(tempEnvPath, envContent);

    // Execute the script with timeout  
    const output = await executeScript(resolvedPath, tempEnvPath);
    
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

function executeScript(scriptPath: string, envFilePath: string): Promise<{
  stdout: string;
  stderr: string;
  success: boolean;
}> {
  return new Promise((resolve) => {
    const scriptDir = path.dirname(scriptPath);
    const recipesRoot = path.join(scriptDir, '..');
    
    // Create a wrapper script that handles module resolution and environment setup
    const scriptName = path.basename(scriptPath);
    const wrapperScript = `
// Change to the recipes directory for proper module resolution
process.chdir('${recipesRoot}');

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

// File-based token caching
const TOKEN_CACHE_FILE = path.join(os.tmpdir(), 'sigma-portal-token.json');

function getCachedToken() {
  try {
    if (fs.existsSync(TOKEN_CACHE_FILE)) {
      const tokenData = JSON.parse(fs.readFileSync(TOKEN_CACHE_FILE, 'utf8'));
      const now = Date.now();
      
      // Check if token is still valid (not expired)
      if (tokenData.expiresAt && now < tokenData.expiresAt) {
        return tokenData.token;
      } else {
        // Token expired, remove file
        fs.unlinkSync(TOKEN_CACHE_FILE);
      }
    }
  } catch (error) {
    // Ignore errors, just return null
  }
  return null;
}

function cacheToken(token) {
  try {
    const tokenData = {
      token: token,
      expiresAt: Date.now() + (60 * 60 * 1000), // 1 hour from now
      createdAt: Date.now()
    };
    fs.writeFileSync(TOKEN_CACHE_FILE, JSON.stringify(tokenData));
  } catch (error) {
    console.error('Failed to cache token:', error.message);
  }
}

// Override getBearerToken function for recipes that use cached tokens
async function getBearerToken() {
  // First check for cached token
  const cached = getCachedToken();
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
    cacheToken(newToken);
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
      
      // Cache the token for future use
      cacheToken(token);
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
  const cachedToken = getCachedToken();
  
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
    
    // Write to a temporary file and require it
    const tempScriptPath = '${scriptPath}' + '.cached.js';
    fs.writeFileSync(tempScriptPath, modifiedScript);
    
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
    
    const child = spawn('node', [tempScriptPath], {
      cwd: recipesRoot,
      timeout: 30000, // 30 second timeout
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