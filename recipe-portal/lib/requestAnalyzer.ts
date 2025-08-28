interface ApiRequest {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  url: string;
  headers: Record<string, string>;
  body?: any;
}

interface RequestPreview {
  description: string;
  request: ApiRequest;
  curlCommand: string;
}

export function analyzeRecipeRequest(
  code: string, 
  envVariables: Record<string, string>,
  baseURL = 'https://aws-api.sigmacomputing.com/v2'
): RequestPreview | null {
  try {
    // Extract method and endpoint patterns
    const methodMatch = code.match(/axios\.(get|post|put|delete)\s*\(/i);
    const urlMatch = code.match(/['"`]([^'"`]*\/[^'"`]*)['"`]/);
    
    if (!methodMatch || !urlMatch) {
      return null;
    }

    const method = methodMatch[1].toUpperCase() as 'GET' | 'POST' | 'PUT' | 'DELETE';
    let endpoint = urlMatch[1];

    // Replace variables in the endpoint
    Object.entries(envVariables).forEach(([key, value]) => {
      if (value) {
        endpoint = endpoint.replace(`\${${key}}`, value);
        endpoint = endpoint.replace(`\${process.env.${key}}`, value);
        endpoint = endpoint.replace(new RegExp(`\\$\\{baseURL\\}`, 'g'), baseURL);
      }
    });

    // Construct full URL
    const fullUrl = endpoint.startsWith('http') ? endpoint : `${baseURL}${endpoint}`;

    // Extract headers
    const headers: Record<string, string> = {
      'Authorization': `Bearer ${envVariables.CLIENT_ID ? '[YOUR_ACCESS_TOKEN]' : '[CACHED_TOKEN]'}`,
      'Accept': 'application/json'
    };

    // Check for Content-Type
    if (method !== 'GET' && code.includes('Content-Type')) {
      headers['Content-Type'] = 'application/json';
    }

    let body: any = undefined;
    let description = '';

    // Analyze request body for POST/PUT requests
    if (method === 'POST' || method === 'PUT') {
      // Look for request body patterns
      const bodyPatterns = [
        /exportOptions\s*=\s*\{([\s\S]*?)\}/,
        /\{[\s\S]*?runAsynchronously:\s*true[\s\S]*?\}/,
        /const\s+\w+\s*=\s*\{([\s\S]*?)\}/
      ];

      for (const pattern of bodyPatterns) {
        const bodyMatch = code.match(pattern);
        if (bodyMatch) {
          try {
            // Build request body based on recipe type and parameters
            body = buildRequestBody(code, envVariables);
            break;
          } catch (e) {
            // If parsing fails, show a basic structure
            body = { 
              "// Note": "Request body structure varies by recipe",
              "// See": "Recipe code for exact structure"
            };
          }
        }
      }
    }

    // Generate description
    if (code.includes('export')) {
      description = method === 'POST' ? 
        'Initiates an asynchronous export job' : 
        'Downloads the export once ready';
    } else if (code.includes('workbooks')) {
      description = 'Workbook-related API operation';
    } else if (code.includes('members')) {
      description = 'Member management API operation';
    } else if (code.includes('teams')) {
      description = 'Team management API operation';
    } else if (code.includes('connections')) {
      description = 'Lists or manages API connections';
    } else {
      description = `${method} request to Sigma API`;
    }

    // Generate curl command
    const curlCommand = generateCurlCommand({ method, url: fullUrl, headers, body });

    return {
      description,
      request: {
        method,
        url: fullUrl,
        headers,
        body
      },
      curlCommand
    };

  } catch (error) {
    console.error('Error analyzing request:', error);
    return null;
  }
}

function buildRequestBody(code: string, envVariables: Record<string, string>): any {
  // Export workbook element (CSV/PDF)
  if (code.includes('export') && code.includes('elementId')) {
    const body: any = {
      elementId: envVariables.ELEMENT_ID || 'ELEMENT_ID_HERE',
      format: { type: 'csv' },
      runAsynchronously: true
    };

    if (code.includes('type: \'pdf\'')) {
      body.format = { type: 'pdf', layout: 'portrait' };
    }

    // Add date range if present
    if (envVariables.START_DATE && envVariables.END_DATE) {
      body.parameters = {
        DateFilter: `min:${envVariables.START_DATE},max:${envVariables.END_DATE}`
      };
    }

    return body;
  }

  // Export workbook (full workbook)
  if (code.includes('export') && code.includes('workbookId')) {
    return {
      workbookId: envVariables.WORKBOOK_ID || 'WORKBOOK_ID_HERE',
      format: { type: 'pdf', layout: 'portrait' }
    };
  }

  // Create member
  if (code.includes('members') && code.includes('POST')) {
    return {
      email: envVariables.EMAIL || 'user@example.com',
      firstName: envVariables.NEW_MEMBER_FIRST_NAME || 'John',
      lastName: envVariables.NEW_MEMBER_LAST_NAME || 'Doe',
      accountType: envVariables.NEW_MEMBER_TYPE || 'viewer'
    };
  }

  // Permission assignments
  if (code.includes('permission')) {
    const permission = envVariables.PERMISSION || envVariables.WORKSPACE_PERMISSION || 'view';
    return {
      memberId: envVariables.MEMBERID || 'MEMBER_ID_HERE',
      permission: permission
    };
  }

  // Create workspace
  if (code.includes('workspace') && code.includes('POST')) {
    return {
      name: envVariables.WORKSPACE_NAME || 'My Workspace',
      noDuplicates: envVariables.NO_DUPLICATES === 'true'
    };
  }

  // Generic fallback
  return {
    "// Note": "Request body varies by recipe",
    "// Parameters": "Populated from user inputs"
  };
}

function generateCurlCommand(request: ApiRequest): string {
  let curl = `curl -X ${request.method} "${request.url}"`;
  
  // Add headers
  Object.entries(request.headers).forEach(([key, value]) => {
    curl += ` \\\n  -H "${key}: ${value}"`;
  });

  // Add body for POST/PUT
  if (request.body && (request.method === 'POST' || request.method === 'PUT')) {
    const bodyJson = JSON.stringify(request.body, null, 2);
    curl += ` \\\n  -d '${bodyJson}'`;
  }

  return curl;
}

export function getApiDocumentationUrl(endpoint: string): string | null {
  const baseDocsUrl = 'https://help.sigmacomputing.com/reference/';
  
  // Map common endpoints to documentation
  const endpointMap: Record<string, string> = {
    '/connections': 'listconnections',
    '/members': 'listmembers', 
    '/teams': 'listteams',
    '/workbooks': 'listworkbooks',
    '/workspaces': 'listworkspaces',
    '/export': 'exportworkbook',
    '/embed': 'createembedurl'
  };

  for (const [pattern, docPath] of Object.entries(endpointMap)) {
    if (endpoint.includes(pattern)) {
      return baseDocsUrl + docPath;
    }
  }

  return 'https://help.sigmacomputing.com/reference/';
}