import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import os from 'os';

// Configuration-specific token caching
function getTokenCacheFile(clientId: string) {
  // Create a safe filename using first 8 chars of clientId
  const configHash = clientId ? clientId.substring(0, 8) : 'default';
  return path.join(os.tmpdir(), `sigma-portal-token-${configHash}.json`);
}

export async function GET() {
  try {
    // Look for the most recent valid token across all configurations
    const tempDir = os.tmpdir();
    const files = fs.readdirSync(tempDir);
    const tokenFiles = files.filter(file => file.startsWith('sigma-portal-token-') && file.endsWith('.json'));
    
    let mostRecentToken = null;
    let mostRecentTime = 0;
    
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
          console.log(`Token ${file}: clientId=${tokenData.clientId?.substring(0,8) || 'default'}, createdAt=${new Date(tokenData.createdAt)}, lastAccessed=${tokenData.lastAccessed ? new Date(tokenData.lastAccessed) : 'none'}, lastAccessTime=${lastAccessTime}`);
          
          const tokenInfo = {
            hasValidToken: true,
            token: tokenData.token,
            expiresAt: tokenData.expiresAt,
            timeRemaining: Math.round((tokenData.expiresAt - now) / 1000 / 60), // minutes
            clientId: tokenData.clientId,
            baseURL: tokenData.baseURL, // Include baseURL to prevent race conditions
            authURL: tokenData.authURL, // Include authURL for completeness
            filePath: filePath,
            lastAccessTime: lastAccessTime
          };
          
          // Separate named configs from default token
          if (tokenData.clientId && tokenData.clientId.length > 8) {
            namedConfigTokens.push(tokenInfo);
            console.log(`  -> This is a named config token (full clientId: ${tokenData.clientId.length} chars)`);
          } else {
            defaultToken = tokenInfo;
            console.log(`  -> This is the default token (clientId: ${tokenData.clientId || 'none'})`);
          }
        } else {
          // Token expired, remove file
          fs.unlinkSync(filePath);
        }
      } catch (err) {
        // Skip invalid token files
        console.warn(`Failed to read token file ${file}:`, err);
      }
    }
    
    // Prioritize named config tokens over default token
    if (namedConfigTokens.length > 0) {
      // Sort named config tokens by most recent access time
      namedConfigTokens.sort((a, b) => b.lastAccessTime - a.lastAccessTime);
      mostRecentToken = namedConfigTokens[0];
      console.log(`  -> Selected most recent named config token: ${mostRecentToken.clientId?.substring(0,8)}`);
    } else if (defaultToken) {
      mostRecentToken = defaultToken;
      console.log(`  -> No named config tokens, using default token`);
    }
    
    if (mostRecentToken) {
      console.log(`Selected token: clientId=${mostRecentToken.clientId?.substring(0,8)}`);
      
      // Update the last accessed time for this token
      try {
        const tokenData = JSON.parse(fs.readFileSync(mostRecentToken.filePath, 'utf8'));
        tokenData.lastAccessed = Date.now();
        fs.writeFileSync(mostRecentToken.filePath, JSON.stringify(tokenData));
      } catch (err) {
        console.warn('Failed to update token access time:', err);
      }
      
      // Remove filePath from response
      const { filePath, ...responseData } = mostRecentToken;
      return NextResponse.json(responseData);
    }
    
    return NextResponse.json({
      hasValidToken: false,
      token: null
    });
  } catch (error) {
    console.error('Error checking token:', error);
    return NextResponse.json({
      hasValidToken: false,
      token: null
    });
  }
}