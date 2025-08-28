import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET() {
  try {
    const envFilePath = path.join(process.cwd(), 'recipes', '.env');
    
    if (!fs.existsSync(envFilePath)) {
      return NextResponse.json({
        values: {},
        exists: false,
        message: 'Environment file not found'
      });
    }

    const envContent = fs.readFileSync(envFilePath, 'utf-8');
    const envValues: Record<string, string> = {};
    
    // Parse the .env file
    const lines = envContent.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      // Skip comments and empty lines
      if (trimmed && !trimmed.startsWith('#')) {
        const match = trimmed.match(/^([^=]+)=(.*)$/);
        if (match) {
          const key = match[1].trim();
          const value = match[2].trim();
          // Only include non-empty values
          if (value && value !== '') {
            envValues[key] = value;
          }
        }
      }
    }

    return NextResponse.json({
      values: envValues,
      exists: true,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error reading .env file:', error);
    return NextResponse.json(
      { 
        error: 'Failed to read environment file',
        values: {},
        exists: false
      },
      { status: 500 }
    );
  }
}