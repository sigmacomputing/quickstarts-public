import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import os from 'os';

export async function POST(request: Request) {
  try {
    // Log request details for debugging
    console.log('Download stream request received from:', request.headers.get('referer'));
    console.log('User agent:', request.headers.get('user-agent'));
    
    // Check if request has a body
    const body = await request.text();
    if (!body || body.trim() === '') {
      console.warn('Empty request body to download-stream endpoint');
      return NextResponse.json(
        { error: 'Request body is empty. This endpoint is only for file download scripts.' },
        { status: 400 }
      );
    }
    
    let parsedBody;
    try {
      parsedBody = JSON.parse(body);
    } catch (parseError) {
      return NextResponse.json(
        { error: 'Invalid JSON in request body. This endpoint is only for file download scripts.' },
        { status: 400 }
      );
    }
    
    const { filePath, envVariables, filename, contentType } = parsedBody;
    
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

    // Create a readable stream for server-sent events
    const stream = new ReadableStream({
      start(controller) {
        executeDownloadWithProgress(resolvedPath, envVariables, controller);
      }
    });

    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
    
  } catch (error) {
    console.error('Error executing download stream:', error);
    return NextResponse.json(
      { error: 'Failed to start download stream' },
      { status: 500 }
    );
  }
}

async function executeDownloadWithProgress(
  scriptPath: string, 
  envVariables: Record<string, string>, 
  controller: ReadableStreamDefaultController
) {
  const scriptDir = path.dirname(scriptPath);
  const recipesRoot = path.join(scriptDir, '..');
  
  // Create temporary .env file
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
  
  envContent += `ENV_FILE_PATH=${tempEnvPath}\n`;
  
  
  fs.writeFileSync(tempEnvPath, envContent);

  const sendProgress = (type: string, message: string, data?: any) => {
    // Handle large content safely for JSON stringification
    let safeData = data;
    if (data && data.content && typeof data.content === 'string' && data.content.length > 10000) {
      // For large content, create a truncated version for the JSON but keep the full content accessible
      safeData = { 
        ...data, 
        content: '[Large content: ' + data.content.length + ' characters]',
        _fullContent: data.content, // Store full content separately
        _isLargeContent: true 
      };
    }
    
    try {
      const event = `data: ${JSON.stringify({ type, message, data: safeData, timestamp: new Date().toISOString() })}\n\n`;
      controller.enqueue(new TextEncoder().encode(event));
    } catch (error) {
      // Fallback for JSON stringification errors
      const fallbackEvent = `data: ${JSON.stringify({ type, message: message + ' (JSON error)', timestamp: new Date().toISOString() })}\n\n`;
      controller.enqueue(new TextEncoder().encode(fallbackEvent));
    }
  };

  try {
    sendProgress('info', 'Using cached authentication token');
    
    // Create wrapper script for streaming progress
    const scriptName = path.basename(scriptPath);
    const wrapperScript = `
process.chdir('${recipesRoot}');

const fs = require('fs');
const path = require('path');
const os = require('os');

// Set up environment variables
const envContent = fs.readFileSync('${tempEnvPath}', 'utf-8');
const envLines = envContent.split('\\n');

envLines.forEach(line => {
  const match = line.match(/^([^=]+)=(.*)$/);
  if (match) {
    process.env[match[1]] = match[2];
  }
});

// Token caching
function getTokenCacheFile(clientId: string) {
  const configHash = clientId ? clientId.substring(0, 8) : "default";
  return path.join(os.tmpdir(), "sigma-portal-token-" + configHash + ".json");
}

function getCachedToken(): { token: string; clientId: string } | null {
  try {
    // Look for the most recent valid token across all configurations
    const tempDir = os.tmpdir();
    const files = fs.readdirSync(tempDir);
    const tokenFiles = files.filter(file => file.startsWith('sigma-portal-token-') && file.endsWith('.json'));
    
    let mostRecentToken = null;
    let mostRecentTime = 0;
    
    for (const file of tokenFiles) {
      try {
        const filePath = path.join(tempDir, file);
        const tokenData = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        const now = Date.now();
        
        // Check if token is still valid (not expired)
        if (tokenData.expiresAt && now < tokenData.expiresAt) {
          const lastAccessTime = tokenData.lastAccessed || tokenData.createdAt;
          
          if (lastAccessTime > mostRecentTime) {
            mostRecentTime = lastAccessTime;
            mostRecentToken = {
              token: tokenData.token,
              clientId: tokenData.clientId
            };
          }
        } else {
          // Token expired, remove file
          fs.unlinkSync(filePath);
        }
      } catch (err) {
        // Skip invalid token files
      }
    }
    
    return mostRecentToken;
  } catch (error) {
    // Ignore errors, just return null
  }
  return null;
      } else {
        fs.unlinkSync(TOKEN_CACHE_FILE);
      }
    }
  } catch (error) {}
  return null;
}

// Global variables for capture
global.DOWNLOAD_CONTENT = null;
global.DOWNLOAD_FILENAME = null;
global.STREAM_FINISHED = false;
global.CAPTURE_IN_PROGRESS = false;

// Override console.log to capture progress
const originalConsoleLog = console.log;
console.log = function(...args) {
  const message = args.map(arg => String(arg)).join(' ');
  
  // For debugging - show ALL messages for now
  process.stdout.write('PROGRESS:debug:' + message + '\\n');
  
  // Also call original for any other logging
  originalConsoleLog.apply(console, args);
};

// File capture system
const originalWriteFileSync = fs.writeFileSync;
const originalCreateWriteStream = fs.createWriteStream;

fs.writeFileSync = function(filePath, data, options) {
  if (filePath.endsWith('.json')) {
    global.DOWNLOAD_CONTENT = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
    global.DOWNLOAD_FILENAME = path.basename(filePath);
    
    // Write download data to temp file instead of stdout to avoid truncation
    const downloadData = {
      content: global.DOWNLOAD_CONTENT,
      filename: global.DOWNLOAD_FILENAME
    };
    
    try {
      const resultFile = require('path').join(require('os').tmpdir(), \`download-result-\${Date.now()}.json\`);
      require('fs').writeFileSync(resultFile, JSON.stringify(downloadData));
      process.stdout.write('DOWNLOAD_FILE:' + resultFile + '\\n');
    } catch (err) {
      process.stdout.write(\`PROGRESS:error:Failed to write download result: \${err.message}\\n\`);
    }
    
    process.exit(0); // Exit immediately after successful capture
    return;
  }
  return originalWriteFileSync.call(this, filePath, data, options);
};

fs.createWriteStream = function(filePath, options) {
  global.DOWNLOAD_FILENAME = path.basename(filePath);
  global.DOWNLOAD_FILEPATH = filePath;
  const tempFilePath = filePath + '.temp';
  
  const realStream = originalCreateWriteStream.call(this, tempFilePath, options);
  let totalBytesWritten = 0;
  let writeCount = 0;
  let lastWriteTime = Date.now();
  let inactivityTimer = null;
  
  const finishDownload = () => {
    if (global.CAPTURE_IN_PROGRESS) return; // Prevent multiple captures
    global.CAPTURE_IN_PROGRESS = true;
    
    process.stdout.write('PROGRESS:info:Finishing download, reading file...\\n');
    try {
      realStream.end();
      setTimeout(() => {
        process.stdout.write(\`PROGRESS:debug:Looking for temp file at: \${tempFilePath}\\n\`);
        if (fs.existsSync(tempFilePath)) {
          const fileData = fs.readFileSync(tempFilePath);
          process.stdout.write(\`PROGRESS:debug:Successfully read \${fileData.length} bytes from temp file\\n\`);
          global.DOWNLOAD_CONTENT = fileData.toString('base64');
          global.STREAM_FINISHED = true;
          
          // Write download data to temp file instead of stdout to avoid truncation
          const downloadData = {
            content: global.DOWNLOAD_CONTENT,
            filename: global.DOWNLOAD_FILENAME || 'export.pdf'
          };
          
          try {
            const os = require('os');
            const path = require('path');
            const fs = require('fs');
            const tempDir = os.tmpdir();
            const resultFile = path.join(tempDir, \`download-result-\${Date.now()}-\${Math.random().toString(36).substring(7)}.json\`);
            
            fs.writeFileSync(resultFile, JSON.stringify(downloadData));
            process.stdout.write('DOWNLOAD_FILE:' + resultFile + '\\n');
          } catch (err) {
            process.stdout.write(\`PROGRESS:error:Failed to write download result: \${err.message}\\n\`);
          }
          
          try { fs.unlinkSync(tempFilePath); } catch (e) {}
          process.exit(0); // Exit immediately after successful capture
        }
      }, 500);
    } catch (err) {
      process.stdout.write(\`PROGRESS:error:Error finishing download: \${err.message}\\n\`);
    }
  };
  
  const mockStream = {
    write: function(chunk) { 
      writeCount++;
      totalBytesWritten += chunk.length;
      lastWriteTime = Date.now();
      
      // Clear any existing inactivity timer
      if (inactivityTimer) {
        clearTimeout(inactivityTimer);
      }
      
      // Set a new inactivity timer - if no writes for 3 seconds, consider download complete
      inactivityTimer = setTimeout(() => {
        process.stdout.write('PROGRESS:info:Download appears complete (3s inactivity)\\n');
        finishDownload();
      }, 3000);
      
      // Show progress for first write and every 1000 writes to avoid spam
      if (writeCount === 1 || writeCount % 1000 === 0) {
        process.stdout.write(\`PROGRESS:info:Downloaded \${Math.round(totalBytesWritten/1024)}KB...\\n\`);
      }
      
      return realStream.write(chunk);
    },
    end: function(chunk) { 
      if (chunk) {
        totalBytesWritten += chunk.length;
      }
      return realStream.end(chunk); 
    },
    on: function(event, callback) {
      if (event === 'finish') {
        realStream.on('finish', () => {
          if (global.CAPTURE_IN_PROGRESS) return; // Prevent multiple captures
          global.CAPTURE_IN_PROGRESS = true;
          
          process.stdout.write('PROGRESS:info:Stream finished, capturing file...\\n');
          try {
            process.stdout.write(\`PROGRESS:debug:Stream finish - looking for temp file at: \${tempFilePath}\\n\`);
            if (fs.existsSync(tempFilePath)) {
              const fileData = fs.readFileSync(tempFilePath);
              process.stdout.write(\`PROGRESS:debug:Stream finish - successfully read \${fileData.length} bytes\\n\`);
              global.DOWNLOAD_CONTENT = fileData.toString('base64');
              
              // Write download data to temp file instead of stdout to avoid truncation
              const downloadData = {
                content: global.DOWNLOAD_CONTENT,
                filename: global.DOWNLOAD_FILENAME || 'export.pdf'
              };
              
              try {
                const os = require('os');
                const path = require('path');
                const fs = require('fs');
                const tempDir = os.tmpdir();
                const resultFile = path.join(tempDir, \`download-result-\${Date.now()}-\${Math.random().toString(36).substring(7)}.json\`);
                
                // Validate content first
                if (!downloadData.content) {
                  throw new Error('Download content is null or undefined');
                }
                
                // Log details in one write to reduce race conditions
                const debugInfo = [
                  'PROGRESS:debug:About to write result file: ' + resultFile,
                  'PROGRESS:debug:Content length: ' + downloadData.content.length + ' chars',
                  'PROGRESS:debug:Filename: ' + downloadData.filename
                ].join('\\n') + '\\n';
                process.stdout.write(debugInfo);
                
                // Create JSON and write file
                const jsonData = JSON.stringify(downloadData);
                process.stdout.write('PROGRESS:debug:JSON data size: ' + jsonData.length + ' chars\\n');
                
                // Write the file synchronously
                fs.writeFileSync(resultFile, jsonData, 'utf8');
                
                // Verify the file was written correctly
                if (!fs.existsSync(resultFile)) {
                  throw new Error('Result file was not created');
                }
                
                const fileSize = fs.statSync(resultFile).size;
                if (fileSize === 0) {
                  throw new Error('Result file is empty');
                }
                
                // Success - output file path and success message
                const successInfo = [
                  'PROGRESS:debug:Result file written successfully (size: ' + fileSize + ' bytes)',
                  'DOWNLOAD_FILE:' + resultFile
                ].join('\\n') + '\\n';
                process.stdout.write(successInfo);
                
              } catch (err) {
                const errorInfo = [
                  'PROGRESS:error:Failed to write download result: ' + err.message,
                  'PROGRESS:error:Stack: ' + err.stack,
                  'PROGRESS:error:Content available: ' + !!downloadData.content,
                  'PROGRESS:error:Content length: ' + (downloadData.content ? downloadData.content.length : 'N/A')
                ].join('\\n') + '\\n';
                process.stdout.write(errorInfo);
              }
              
              try { fs.unlinkSync(tempFilePath); } catch (e) {}
              
              // Ensure stdout is flushed before exit
              process.stdout.write('', () => {
                process.exit(0);
              });
            }
            callback();
          } catch (err) {
            process.stdout.write(\`PROGRESS:error:Error reading temp file: \${err.message}\\n\`);
            callback();
          }
        });
        return this;
      }
      if (event === 'error') {
        realStream.on('error', callback);
        return this;
      }
      return realStream.on(event, callback);
    },
    once: function(event, callback) {
      return realStream.once(event, callback);
    },
    pipe: function(source) {
      return source.pipe(realStream);
    },
    close: function() { 
      return realStream.close(); 
    },
    destroy: function() { 
      return realStream.destroy(); 
    },
    writable: true,
    readable: false
  };
  
  // Ensure the mock stream has all necessary EventEmitter methods
  Object.setPrototypeOf(mockStream, realStream);
  
  return mockStream;
};

// Get cached token and execute
const cachedToken = getCachedToken();
if (cachedToken) {
  
  let scriptContent = fs.readFileSync('${scriptPath}', 'utf-8');
  
  const modifiedScript = scriptContent.replace(
    /const getBearerToken = require\\(['"][^'"]*get-access-token['"]\\);/g,
    'const getBearerToken = async () => { return "' + cachedToken + '"; };'
  ).replace(
    /if \\(require\\.main === module\\) \\{([\\s\\S]*?)\\}/g,
    '{ $1 }'
  ).replace(
    // Change the 10 second delay to 30 seconds for large datasets
    /setTimeout\\(resolve, 10000\\)/g,
    'setTimeout(resolve, 30000)'
  ).replace(
    // Also update any 10000 millisecond delays
    /await new Promise\\(resolve => setTimeout\\(resolve, 10000\\)\\)/g,
    'await new Promise(resolve => setTimeout(resolve, 30000))'
  );
  
  const tempScriptPath = '${scriptPath}' + '.stream.js';
  fs.writeFileSync(tempScriptPath, modifiedScript);
  
  try {
    
    delete require.cache[require.resolve(tempScriptPath)];
    require(tempScriptPath);
    
    // Check for completion
    let checkCount = 0;
    const maxChecks = 30; // 4 minutes max
    
    const checkForCompletion = () => {
      checkCount++;
      
      if (global.DOWNLOAD_CONTENT) {
        process.stdout.write('DOWNLOAD_RESULT:' + JSON.stringify({
          content: global.DOWNLOAD_CONTENT,
          filename: global.DOWNLOAD_FILENAME || 'export.pdf'
        }) + '\\n');
        process.exit(0);
      } else if (checkCount >= maxChecks) {
        process.stdout.write('PROGRESS:timeout:Download timeout - export may have failed\\n');
        process.exit(1);
      } else {
        setTimeout(checkForCompletion, 8000); // Check every 8 seconds
      }
    };
    
    setTimeout(checkForCompletion, 10000); // Wait 10 seconds for stream to finish before first check
    
  } finally {
    try {
      fs.unlinkSync(tempScriptPath);
    } catch (err) {}
  }
} else {
  process.stdout.write('PROGRESS:error:No cached authentication token found\\n');
  process.exit(1);
}
`;

    const tempScriptPath = path.join(os.tmpdir(), `temp-stream-wrapper-${Date.now()}.js`);
    fs.writeFileSync(tempScriptPath, wrapperScript);
    
    const child = spawn('node', [tempScriptPath], {
      cwd: recipesRoot,
      timeout: 600000, // 10 minute timeout for large datasets
    });

    let fileContent: string | null = null;
    let filename: string | null = null;

    let downloadResultCapture = false;
    let capturedFilename = '';
    let capturedContent = '';
    let downloadCompleted = false; // Flag to prevent duplicate success messages

    child.stdout?.on('data', (data) => {
      const output = data.toString();
      const lines = output.split('\n');
      
      for (const line of lines) {
        if (line === 'DOWNLOAD_RESULT_START') {
          downloadResultCapture = true;
          sendProgress('info', 'Capturing download result...');
        } else if (line === 'DOWNLOAD_RESULT_END') {
          downloadResultCapture = false;
          // Process the captured data immediately
          if (capturedFilename && capturedContent) {
            try {
              // Write content to JSON file and use the existing DOWNLOAD_FILE protocol
              const tempResultPath = path.join(os.tmpdir(), `download-result-${Date.now()}.json`);
              const downloadData = {
                content: capturedContent,
                filename: capturedFilename
              };
              fs.writeFileSync(tempResultPath, JSON.stringify(downloadData));
              
              // Don't use sendProgress for DOWNLOAD_FILE - it needs to be processed differently
              // Store the file path for later processing
              fileContent = capturedContent;
              filename = capturedFilename;
              sendProgress('debug', `Stored fileContent length: ${fileContent?.length || 0}, filename: ${filename || 'none'}`);
              
              // Also store as global variables as backup
              (global as any).FINAL_DOWNLOAD_CONTENT = capturedContent;
              (global as any).FINAL_DOWNLOAD_FILENAME = capturedFilename;
              
              sendProgress('success', 'Download completed!', {
                filename: capturedFilename,
                size: Math.round(capturedContent.length * 0.75) // Rough base64 to bytes
              });
              
              downloadCompleted = true; // Mark as completed to prevent duplicate messages
              
            } catch (err) {
              sendProgress('error', 'Failed to process download result: ' + (err instanceof Error ? err.message : String(err)));
            }
          }
        } else if (downloadResultCapture) {
          if (line.startsWith('FILENAME:')) {
            capturedFilename = line.substring(9);
            sendProgress('debug', `Captured filename: ${capturedFilename}`);
          } else if (line.startsWith('CONTENT:')) {
            capturedContent = line.substring(8);
            sendProgress('debug', `Captured content length: ${capturedContent.length} chars`);
          } else if (line.trim() && capturedContent) {
            // Append additional lines that are part of the base64 content
            capturedContent += line;
            sendProgress('debug', `Appended content, total length: ${capturedContent.length} chars`);
          }
        } else if (line.startsWith('PROGRESS:')) {
          const [, type, message] = line.split(':', 3);
          sendProgress(type, message);
        } else if (line.startsWith('DOWNLOAD_FILE:')) {
          try {
            const filePath = line.substring(14);
            sendProgress('debug', `Reading download file: ${filePath}`);
            
            if (!fs.existsSync(filePath)) {
              throw new Error(`Download file does not exist: ${filePath}`);
            }
            
            const fileStats = fs.statSync(filePath);
            sendProgress('debug', `File size: ${fileStats.size} bytes`);
            
            const downloadData = JSON.parse(fs.readFileSync(filePath, 'utf8'));
            fileContent = downloadData.content;
            filename = downloadData.filename;
            
            sendProgress('debug', `File content length: ${fileContent ? fileContent.length : 'null'}`);
            sendProgress('debug', `Filename: ${filename}`);
            
            sendProgress('success', 'Download completed!', {
              filename,
              size: Math.round((fileContent?.length || 0) * 0.75) // Rough base64 to bytes
            });
            
            // Clean up temp file
            try { fs.unlinkSync(filePath); } catch (e) {}
          } catch (e) {
            sendProgress('error', `Failed to read download result file: ${e instanceof Error ? e.message : String(e)}`);
          }
        } else if (line.startsWith('DOWNLOAD_RESULT:')) {
          // Keep old method as fallback for smaller files
          try {
            const jsonString = line.substring(16);
            const downloadData = JSON.parse(jsonString);
            fileContent = downloadData.content;
            filename = downloadData.filename;
            sendProgress('success', 'Download completed!', {
              filename,
              size: Math.round((fileContent?.length || 0) * 0.75) // Rough base64 to bytes
            });
          } catch (e) {
            sendProgress('error', `Failed to parse download result: ${e instanceof Error ? e.message : String(e)}`);
          }
        }
      }
    });

    child.stderr?.on('data', (data) => {
      const output = data.toString();
      // Handle our direct log messages separately from real errors
      if (output.includes('DIRECT_LOG:')) {
        const message = output.replace('DIRECT_LOG:', '').trim();
        sendProgress('info', message);
      } else {
        sendProgress('error', `Error: ${output}`);
      }
    });

    child.on('close', (code) => {
      // Clean up
      try {
        fs.unlinkSync(tempScriptPath);
        fs.unlinkSync(tempEnvPath);
      } catch (err) {}
      
      sendProgress('debug', `Process closed with code: ${code}`);
      sendProgress('debug', `File content available: ${!!fileContent}`);
      sendProgress('debug', `Filename: ${filename || 'none'}`);
      
      // Check backup global variables if local ones are empty
      if (!fileContent && (global as any).FINAL_DOWNLOAD_CONTENT) {
        fileContent = (global as any).FINAL_DOWNLOAD_CONTENT;
        filename = (global as any).FINAL_DOWNLOAD_FILENAME;
        sendProgress('debug', `Using backup global variables - content length: ${fileContent?.length || 0}, filename: ${filename || 'none'}`);
      }
      
      if (downloadCompleted) {
        // Download was already processed successfully via DOWNLOAD_RESULT protocol
        sendProgress('debug', 'Download already completed via DOWNLOAD_RESULT protocol');
      } else if (code === 0 && fileContent) {
        try {
          // Read content from temp file if it's a file path, otherwise treat as direct content
          let actualContent: string;
          if (fileContent.startsWith('/') && fs.existsSync(fileContent)) {
            // Read from temp file
            actualContent = fs.readFileSync(fileContent, 'utf8');
            // Clean up temp file
            fs.unlinkSync(fileContent);
          } else {
            // Direct content (fallback)
            actualContent = fileContent;
          }
          
          // Simple completion message - file is already saved locally by the recipe
          sendProgress('success', `File "${filename}" saved successfully!`, {
            filename: filename,
            localPath: path.resolve('downloaded-files', filename || 'download'),
            size: Math.round(actualContent.length * 0.75) // Rough base64 to bytes
          });
        } catch (err) {
          sendProgress('error', `Failed to process download file: ${err instanceof Error ? err.message : String(err)}`);
        }
      } else if (code !== 0) {
        sendProgress('error', `Process exited with code ${code}`);
      } else if (!fileContent && !downloadCompleted) {
        sendProgress('error', 'No file content captured');
      }
      
      controller.close();
    });

    child.on('error', (error) => {
      sendProgress('error', `Execution error: ${error.message}`);
      controller.close();
    });

  } catch (error) {
    sendProgress('error', `Failed to start download: ${error}`);
    controller.close();
  }
}

function getContentTypeFromFilename(filename: string): string {
  if (filename.endsWith('.pdf')) return 'application/pdf';
  if (filename.endsWith('.csv')) return 'text/csv';
  if (filename.endsWith('.json')) return 'application/json';
  return 'application/octet-stream';
}