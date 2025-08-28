import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const filePath = searchParams.get('path');
    
    console.log('=== CODE API DEBUG ===');
    console.log('Received filePath:', filePath);
    console.log('Process CWD:', process.cwd());
    
    if (!filePath) {
      return NextResponse.json(
        { error: 'File path is required' },
        { status: 400 }
      );
    }

    // Force the file path to be relative to our current working directory  
    const relativePath = filePath.replace(/^.*recipes\//, 'recipes/');
    const correctedPath = path.join(process.cwd(), relativePath);
    
    console.log('Corrected path:', correctedPath);

    // Security check: ensure the file is within the recipes directory
    const recipesPath = path.join(process.cwd(), 'recipes');
    const resolvedPath = path.resolve(correctedPath);
    const resolvedRecipesPath = path.resolve(recipesPath);
    
    if (!resolvedPath.startsWith(resolvedRecipesPath)) {
      return NextResponse.json(
        { error: 'Access denied: File must be within recipes directory' },
        { status: 403 }
      );
    }

    // Check if file exists and is a JavaScript file
    if (!fs.existsSync(resolvedPath)) {
      return NextResponse.json(
        { error: 'File not found' },
        { status: 404 }
      );
    }

    if (!resolvedPath.endsWith('.js')) {
      return NextResponse.json(
        { error: 'Only JavaScript files are allowed' },
        { status: 400 }
      );
    }

    // Read the file content
    const content = fs.readFileSync(resolvedPath, 'utf-8');
    
    return NextResponse.json({
      content,
      filePath: resolvedPath,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error reading file:', error);
    return NextResponse.json(
      { error: 'Failed to read file' },
      { status: 500 }
    );
  }
}