import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import os from 'os';

export async function POST(request: Request) {
  try {
    const { filePath, envVariables, filename, contentType } = await request.json();
    
    if (!filePath) {
      return NextResponse.json(
        { error: 'File path is required' },
        { status: 400 }
      );
    }

    // Security check: ensure the file is within the recipes directory
    const recipesPath = path.join(process.cwd(), 'recipes');
    const resolvedPath = path.resolve(filePath);
    const resolvedRecipesPath = path.resolve(recipesPath);
    
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
    
    fs.writeFileSync(tempEnvPath, envContent);

    // Execute the script and capture file content  
    const result = await executeDownloadScript(resolvedPath, tempEnvPath);
    
    // Clean up temp file
    try {
      fs.unlinkSync(tempEnvPath);
    } catch (err) {
      console.warn('Failed to cleanup temp env file:', err);
    }

    if (result.success && result.fileContent) {
      // Return the file content for browser download
      return NextResponse.json({
        fileContent: result.fileContent,
        filename: filename || 'download',
        contentType: contentType || 'application/octet-stream',
        success: true,
        output: result.stdout,
        timestamp: new Date().toISOString()
      });
    } else {
      return NextResponse.json({
        output: result.stdout,
        error: result.stderr,
        success: false,
        timestamp: new Date().toISOString(),
        httpStatus: 500,
        httpStatusText: 'Download Failed'
      });
    }
    
  } catch (error) {
    console.error('Error executing download script:', error);
    return NextResponse.json(
      { error: 'Failed to execute download script' },
      { status: 500 }
    );
  }
}

function executeDownloadScript(scriptPath: string, envFilePath: string): Promise<{
  stdout: string;
  stderr: string;
  success: boolean;
  fileContent?: string;
}> {
  return new Promise((resolve) => {
    const scriptDir = path.dirname(scriptPath);
    const recipesRoot = path.join(scriptDir, '..');
    
    // Create a wrapper script that captures file content instead of writing to disk
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
      
      if (tokenData.expiresAt && now < tokenData.expiresAt) {
        return tokenData.token;
      } else {
        fs.unlinkSync(TOKEN_CACHE_FILE);
      }
    }
  } catch (error) {
    // Ignore errors
  }
  return null;
}

function cacheToken(token) {
  try {
    const tokenData = {
      token: token,
      expiresAt: Date.now() + (60 * 60 * 1000),
      createdAt: Date.now()
    };
    fs.writeFileSync(TOKEN_CACHE_FILE, JSON.stringify(tokenData));
  } catch (error) {
    console.error('Failed to cache token:', error.message);
  }
}

// Global variable to capture file content for download
global.DOWNLOAD_CONTENT = null;
global.DOWNLOAD_FILENAME = null;

// Override file writing functions to capture content  
const originalWriteFileSync = fs.writeFileSync;
const originalCreateWriteStream = fs.createWriteStream;
const originalReadFileSync = fs.readFileSync;
const originalUnlinkSync = fs.unlinkSync;

console.log('WRAPPER: Setting up filesystem overrides');

fs.writeFileSync = function(filePath, data, options) {
  // For JSON files, capture the content
  if (filePath.endsWith('.json')) {
    global.DOWNLOAD_CONTENT = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
    global.DOWNLOAD_FILENAME = path.basename(filePath);
    console.log(\`Download ready: \${global.DOWNLOAD_FILENAME}\`);
    return;
  }
  // For other files, use original behavior as fallback
  return originalWriteFileSync.call(this, filePath, data, options);
};

// Override stream writing for binary files
fs.createWriteStream = function(filePath, options) {
  console.log(\`WRAPPER: Intercepted createWriteStream for: \${path.basename(filePath)}\`);
  global.DOWNLOAD_FILENAME = path.basename(filePath);
  global.DOWNLOAD_FILEPATH = filePath;
  
  // Use a temporary file to capture the actual data
  const tempFilePath = filePath + '.temp';
  const realStream = originalCreateWriteStream.call(this, tempFilePath, options);
  
  // Create a proper writable stream proxy that captures completion
  const mockStream = {
    write: function(chunk) { 
      return realStream.write(chunk); 
    },
    end: function(chunk) { 
      if (chunk) realStream.write(chunk);
      return realStream.end(); 
    },
    destroy: function() { 
      return realStream.destroy(); 
    },
    on: function(event, callback) {
      if (event === 'finish') {
        // When the real stream finishes, read the file and store content
        realStream.on('finish', () => {
          console.log(\`WRAPPER: Reading completed file...\`);
          try {
            // Give the filesystem a moment to flush
            setTimeout(() => {
              if (fs.existsSync(tempFilePath)) {
                const fileData = originalReadFileSync(tempFilePath);
                global.DOWNLOAD_CONTENT = fileData.toString('base64');
                console.log(\`WRAPPER: Successfully captured \${fileData.length} bytes\`);
                console.log(\`Download ready: \${global.DOWNLOAD_FILENAME}\`);
                // Clean up temp file
                try { originalUnlinkSync(tempFilePath); } catch (e) {}
              } else {
                console.error(\`WRAPPER: Temp file missing: \${tempFilePath}\`);
              }
              // Always call the callback to let the recipe know we're done
              if (callback) callback();
            }, 200);
          } catch (err) {
            console.error('WRAPPER: Error reading file:', err);
            if (callback) callback();
          }
        });
        return this;
      }
      return realStream.on(event, callback);
    },
    // Implement writable stream interface properly
    writable: true,
    readable: false,
    close: function() { 
      return realStream.close(); 
    }
  };
  
  return mockStream;
};

// Override getBearerToken function for cached tokens
async function getBearerToken() {
  const cached = getCachedToken();
  if (cached) {
    return cached;
  }
  
  const originalConsoleLog = console.log;
  const originalConsoleError = console.error;
  console.log = () => {};
  console.error = () => {};
  
  const originalGetBearerToken = require('${recipesRoot}/get-access-token');
  const newToken = await originalGetBearerToken();
  
  console.log = originalConsoleLog;
  console.error = originalConsoleError;
  
  if (newToken) {
    cacheToken(newToken);
  }
  
  return newToken;
}

// Execute the script
try {
  const cachedToken = getCachedToken();
  
  if (cachedToken) {
    console.log('Using cached authentication token for download');
    
    let scriptContent = fs.readFileSync('${scriptPath}', 'utf-8');
    
    // Replace the getBearerToken import with cached token
    const modifiedScript = scriptContent.replace(
      /const getBearerToken = require\\(['"][^'"]*get-access-token['"]\\);/g,
      'const getBearerToken = async () => { return "' + cachedToken + '"; };'
    ).replace(
      /if \\(require\\.main === module\\) \\{([\\s\\S]*?)\\}/g,
      '{ $1 }'
    );
    
    const tempScriptPath = '${scriptPath}' + '.download.js';
    fs.writeFileSync(tempScriptPath, modifiedScript);
    
    try {
      delete require.cache[require.resolve(tempScriptPath)];
      require(tempScriptPath);
      
      // Wait longer for async operations to complete (PDF exports can take time)
      let checkCount = 0;
      const maxChecks = 30; // 30 checks * 2 seconds = 60 seconds max
      
      const checkForCompletion = () => {
        checkCount++;
        if (global.DOWNLOAD_CONTENT) {
          console.log('DOWNLOAD_RESULT:' + JSON.stringify({
            content: global.DOWNLOAD_CONTENT,
            filename: global.DOWNLOAD_FILENAME
          }));
          process.exit(0);
        } else if (checkCount >= maxChecks) {
          console.log('Download timeout - export may have failed or taken too long');
          process.exit(1);
        } else {
          // Check again in 2 seconds
          setTimeout(checkForCompletion, 2000);
        }
      };
      
      // Start checking after initial delay
      setTimeout(checkForCompletion, 3000);
      
    } finally {
      try {
        fs.unlinkSync(tempScriptPath);
      } catch (err) {}
    }
  } else {
    console.log('No cached token found for download script.');
    process.exit(1);
  }
} catch (error) {
  console.error('Script execution error:', error.message);
  process.exit(1);
}
`;
    
    const tempScriptPath = path.join(os.tmpdir(), `temp-download-wrapper-${Date.now()}.js`);
    fs.writeFileSync(tempScriptPath, wrapperScript);
    
    const child = spawn('node', [tempScriptPath], {
      cwd: recipesRoot,
      timeout: 120000, // 120 second timeout for downloads (PDF exports can take time)
    });

    let stdout = '';
    let stderr = '';
    let fileContent: string | null = null;

    child.stdout?.on('data', (data) => {
      const output = data.toString();
      stdout += output;
      
      // Look for download result in output
      const downloadMatch = output.match(/DOWNLOAD_RESULT:(.+)/);
      if (downloadMatch) {
        try {
          const downloadData = JSON.parse(downloadMatch[1]);
          fileContent = downloadData.content;
        } catch (e) {
          console.error('Failed to parse download result:', e);
        }
      }
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
        stdout: stdout || 'Download script executed',
        stderr: stderr || '',
        success: code === 0 && fileContent !== null,
        fileContent: fileContent || undefined
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