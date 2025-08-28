import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const readmePath = searchParams.get('path');
    
    if (!readmePath) {
      return NextResponse.json(
        { error: 'README path is required' },
        { status: 400 }
      );
    }

    // Security check: ensure the file is within the sigma-api-recipes directory
    const recipesPath = path.join(process.cwd(), '..', 'sigma-api-recipes');
    const resolvedPath = path.resolve(readmePath);
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
        { error: 'README file not found' },
        { status: 404 }
      );
    }

    const content = fs.readFileSync(resolvedPath, 'utf-8');
    
    return NextResponse.json({
      content,
      success: true
    });
    
  } catch (error) {
    console.error('Error reading README file:', error);
    return NextResponse.json(
      { error: 'Failed to read README file' },
      { status: 500 }
    );
  }
}