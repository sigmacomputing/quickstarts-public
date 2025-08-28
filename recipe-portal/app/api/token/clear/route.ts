import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import os from 'os';

// Configuration-specific token caching
function getTokenCacheFile(clientId: string | null) {
  // Create a safe filename using first 8 chars of clientId
  const configHash = clientId ? clientId.substring(0, 8) : 'default';
  return path.join(os.tmpdir(), `sigma-portal-token-${configHash}.json`);
}

export async function POST(request: Request) {
  try {
    const { clientId, clearAll } = await request.json();
    
    console.log('Token clear request:', { clientId, clearAll });
    
    if (clearAll) {
      // Clear all token cache files
      const tempDir = os.tmpdir();
      const files = fs.readdirSync(tempDir);
      const tokenFiles = files.filter(file => file.startsWith('sigma-portal-token-') && file.endsWith('.json'));
      
      console.log('Clearing all tokens:', tokenFiles);
      
      let clearedCount = 0;
      for (const file of tokenFiles) {
        try {
          fs.unlinkSync(path.join(tempDir, file));
          clearedCount++;
          console.log(`Cleared token file: ${file}`);
        } catch (err) {
          console.warn(`Failed to delete token file ${file}:`, err);
        }
      }
      
      return NextResponse.json({
        success: true,
        message: `Cleared ${clearedCount} authentication token(s)`
      });
    } else {
      // Clear specific configuration's token
      const TOKEN_CACHE_FILE = getTokenCacheFile(clientId);
      
      if (fs.existsSync(TOKEN_CACHE_FILE)) {
        fs.unlinkSync(TOKEN_CACHE_FILE);
      }
      
      return NextResponse.json({
        success: true,
        message: 'Authentication token cleared successfully'
      });
    }
  } catch (error) {
    console.error('Error clearing token:', error);
    return NextResponse.json(
      { 
        success: false, 
        error: 'Failed to clear authentication token' 
      },
      { status: 500 }
    );
  }
}