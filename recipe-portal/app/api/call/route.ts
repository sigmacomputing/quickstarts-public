import { NextResponse } from 'next/server';
import axios from 'axios';
import fs from 'fs';
import path from 'path';
import os from 'os';

// Configuration-specific token caching (matches other working routes)
function getTokenCacheFile(clientId: string) {
  const configHash = clientId ? clientId.substring(0, 8) : 'default';
  return path.join(os.tmpdir(), `sigma-portal-token-${configHash}.json`);
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
}

export async function POST(request: Request) {
  try {
    const { endpoint, method, parameters = {}, requestBody, baseURL: providedBaseURL } = await request.json();
    
    if (!endpoint) {
      return NextResponse.json(
        { error: 'Endpoint is required' },
        { status: 400 }
      );
    }

    // Get cached token
    const tokenData = getCachedToken();
    if (!tokenData) {
      return NextResponse.json(
        { 
          error: 'Authentication required', 
          message: 'No valid authentication token found. Please authenticate first.' 
        },
        { status: 401 }
      );
    }

    // Build the full URL - use provided baseURL to prevent race conditions, fallback to environment/default
    const baseURL = providedBaseURL || process.env.SIGMA_BASE_URL || 'https://aws-api.sigmacomputing.com/v2';
    let url = `${baseURL}${endpoint}`;
    
    console.log(`API Call: ${method} ${url} (baseURL from auth config: ${baseURL})`);

    // Add query parameters
    if (parameters.query && Object.keys(parameters.query).length > 0) {
      const queryParams = new URLSearchParams();
      Object.entries(parameters.query).forEach(([key, value]) => {
        if (value !== undefined && value !== '') {
          queryParams.append(key, String(value));
        }
      });
      if (queryParams.toString()) {
        url += `?${queryParams.toString()}`;
      }
    }

    // Prepare headers
    const headers: Record<string, string> = {
      'Authorization': `Bearer ${tokenData.token}`,
      'Accept': 'application/json',
      'Content-Type': 'application/json'
    };

    // Add header parameters
    if (parameters.header) {
      Object.entries(parameters.header).forEach(([key, value]) => {
        if (value !== undefined && value !== '') {
          headers[key] = String(value);
        }
      });
    }

    // Make the API call
    const response = await axios({
      method: method.toLowerCase(),
      url,
      headers,
      data: requestBody,
      timeout: 30000 // 30 second timeout
    });

    // Return successful response
    return NextResponse.json({
      output: JSON.stringify(response.data, null, 2),
      error: '',
      success: true,
      timestamp: new Date().toISOString(),
      httpStatus: response.status,
      httpStatusText: response.statusText,
      requestUrl: url,
      requestMethod: method
    });

  } catch (error: any) {
    console.error('API call error:', error);
    
    let errorMessage = 'Unknown error occurred';
    let httpStatus = 500;
    let httpStatusText = 'Internal Server Error';

    if (axios.isAxiosError(error)) {
      if (error.response) {
        // Server responded with error status
        httpStatus = error.response.status;
        httpStatusText = error.response.statusText;
        errorMessage = error.response.data?.message || error.response.data?.error || `HTTP ${httpStatus}: ${httpStatusText}`;
      } else if (error.request) {
        // Request made but no response
        errorMessage = 'No response received from server';
        httpStatus = 0;
        httpStatusText = 'Network Error';
      } else {
        // Error setting up request
        errorMessage = error.message;
      }
    } else {
      errorMessage = error.message || 'Unknown error';
    }

    return NextResponse.json({
      output: '',
      error: errorMessage,
      success: false,
      timestamp: new Date().toISOString(),
      httpStatus,
      httpStatusText
    });
  }
}