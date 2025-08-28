import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

function convertMarkdownToHtml(markdown: string): string {
  // First, normalize line endings and remove excessive whitespace
  let html = markdown
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    // Remove excessive blank lines
    .replace(/\n{3,}/g, '\n\n')
    // Trim each line
    .split('\n')
    .map(line => line.trim())
    .join('\n');

  return html
    // Code blocks (do this first to preserve their content)
    .replace(/```[\s\S]*?```/g, (match) => {
      const code = match.replace(/```\w*\n?/, '').replace(/\n?```$/, '');
      return `<pre class="bg-gray-100 p-3 rounded text-sm overflow-x-auto mb-3"><code>${code.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code></pre>`;
    })
    // Headers
    .replace(/^### (.+)$/gm, '<h3 class="text-lg font-medium text-gray-600 mt-4 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-xl font-semibold text-gray-700 mt-5 mb-2">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold text-gray-800 mb-3 pb-2 border-b border-gray-200">$1</h1>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono">$1</code>')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="text-blue-600 hover:text-blue-800 underline">$1</a>')
    // Bold text
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold">$1</strong>')
    // Lists
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^\* (.+)$/gm, '<li>$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
    // Wrap consecutive list items in proper containers
    .replace(/(<li>.*?<\/li>(?:\s*<li>.*?<\/li>)*)/g, (match) => {
      const items = match.trim();
      return `<ul class="list-disc list-inside mb-3 ml-4">${items}</ul>`;
    })
    // Convert double line breaks to paragraph breaks
    .replace(/\n\s*\n/g, '</p><p class="mb-2">')
    // Wrap remaining content in paragraphs
    .replace(/^(?![<])/gm, '<p class="mb-2">')
    // Clean up paragraph wrapping around headers and other elements
    .replace(/<p class="mb-2">(<[h123]|<pre|<ul)/g, '$1')
    .replace(/(<\/h[123]>|<\/pre>|<\/ul>)<p class="mb-2">/g, '$1')
    // Remove trailing paragraph tags
    .replace(/<\/p>$/g, '')
    // Remove empty paragraphs
    .replace(/<p class="mb-2"><\/p>/g, '');
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const readmePath = searchParams.get('path');
    const format = searchParams.get('format'); // Check if HTML format is requested
    
    if (!readmePath) {
      return NextResponse.json(
        { error: 'README path is required' },
        { status: 400 }
      );
    }

    // Security check: ensure the file is within the recipes directory or is the main README
    const recipesPath = path.join(process.cwd(), 'recipes');
    const mainReadmePath = path.join(process.cwd(), 'README.md');
    const resolvedPath = path.resolve(readmePath);
    const resolvedRecipesPath = path.resolve(recipesPath);
    const resolvedMainReadmePath = path.resolve(mainReadmePath);
    
    if (!resolvedPath.startsWith(resolvedRecipesPath) && resolvedPath !== resolvedMainReadmePath) {
      return NextResponse.json(
        { error: 'Access denied: File must be within recipes directory or be the main README' },
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
    
    // If accessed directly in browser (no explicit JSON format requested), return HTML
    if (format !== 'json') {
      const htmlContent = `<!DOCTYPE html>
<html>
<head>
    <title>Recipe Instructions</title>
    <meta charset="utf-8">
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif; 
            max-width: 800px; 
            margin: 0 auto; 
            padding: 2rem; 
            line-height: 1.6; 
            color: #333;
        }
        h1 { color: #2563eb; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.5rem; }
        h2 { color: #1f2937; margin-top: 2rem; }
        h3 { color: #374151; }
        code { 
            background: #f3f4f6; 
            padding: 0.2rem 0.4rem; 
            border-radius: 0.25rem; 
            font-family: 'Monaco', 'Menlo', monospace;
        }
        pre { 
            background: #f9fafb; 
            border: 1px solid #e5e7eb; 
            padding: 1rem; 
            border-radius: 0.5rem; 
            overflow-x: auto;
        }
        ul { padding-left: 1.5rem; }
        li { margin: 0.5rem 0; }
        a { color: #2563eb; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .close-btn { 
            position: fixed; 
            top: 1rem; 
            right: 1rem; 
            background: #3b82f6; 
            color: white; 
            padding: 0.5rem 1rem; 
            border-radius: 0.5rem; 
            text-decoration: none;
            font-weight: 500;
        }
        .close-btn:hover { background: #2563eb; }
    </style>
</head>
<body>
    <a href="javascript:window.close()" class="close-btn">✕ Close</a>
    <div>${convertMarkdownToHtml(content)}</div>
</body>
</html>`;

      return new NextResponse(htmlContent, {
        headers: {
          'Content-Type': 'text/html; charset=utf-8',
        },
      });
    }
    
    // Return JSON for API calls
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