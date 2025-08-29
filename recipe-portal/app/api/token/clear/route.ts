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
      console.log('=== CLEAR ALL TOKENS DEBUG ===');
      console.log('Temp directory:', tempDir);
      
      const files = fs.readdirSync(tempDir);
      const tokenFiles = files.filter(file => file.startsWith('sigma-portal-token-') && file.endsWith('.json'));
      
      console.log('All files in temp dir that match pattern:', tokenFiles);
      console.log('Clearing all tokens:', tokenFiles);
      
      let clearedCount = 0;
      let failedToDelete = [];
      
      for (const file of tokenFiles) {
        try {
          const fullPath = path.join(tempDir, file);
          console.log(`Attempting to delete: ${fullPath}`);
          fs.unlinkSync(fullPath);
          clearedCount++;
          console.log(`✓ Successfully cleared token file: ${file}`);
        } catch (err) {
          console.error(`✗ Failed to delete token file ${file}:`, err);
          failedToDelete.push({ file, error: err.message });
        }
      }
      
      // Verify deletion by checking again
      const filesAfterDelete = fs.readdirSync(tempDir);
      const tokenFilesAfterDelete = filesAfterDelete.filter(file => file.startsWith('sigma-portal-token-') && file.endsWith('.json'));
      console.log('Token files remaining after deletion attempt:', tokenFilesAfterDelete);
      
      return NextResponse.json({
        success: failedToDelete.length === 0,
        message: `Cleared ${clearedCount} authentication token(s)`,
        details: {
          cleared: clearedCount,
          failed: failedToDelete,
          remainingFiles: tokenFilesAfterDelete
        }
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