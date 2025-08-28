import { NextResponse } from 'next/server';
import { exec } from 'child_process';
import path from 'path';

export async function POST(request: Request) {
  try {
    const { folder } = await request.json();
    
    if (!folder || folder !== 'downloaded-files') {
      return NextResponse.json(
        { error: 'Invalid folder specified' },
        { status: 400 }
      );
    }
    
    const folderPath = path.resolve(folder);
    
    // Open folder using system command based on OS
    let command: string;
    if (process.platform === 'win32') {
      command = `explorer "${folderPath}"`;
    } else if (process.platform === 'darwin') {
      command = `open "${folderPath}"`;
    } else {
      command = `xdg-open "${folderPath}"`;
    }
    
    exec(command, (error) => {
      if (error) {
        console.error('Error opening folder:', error);
      }
    });
    
    return NextResponse.json({ success: true });
    
  } catch (error) {
    console.error('Error opening folder:', error);
    return NextResponse.json(
      { error: 'Failed to open folder' },
      { status: 500 }
    );
  }
}