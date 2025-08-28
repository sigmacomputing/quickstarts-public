'use client';

import { useState, useEffect } from 'react';

interface CodeViewerProps {
  isOpen: boolean;
  onClose: () => void;
  filePath: string;
  fileName: string;
  envVariables?: string[];
  useEnvFile?: boolean;
  onTokenObtained?: () => void;
  defaultTab?: 'params' | 'run' | 'code' | 'readme';
}

interface ExecutionResult {
  output: string;
  error: string;
  success: boolean;
  timestamp: string;
  httpStatus?: number;
  httpStatusText?: string;
}

export function CodeViewer({ isOpen, onClose, filePath, fileName, envVariables = [], useEnvFile = false, onTokenObtained, defaultTab = 'params' }: CodeViewerProps) {
  const [code, setCode] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'params' | 'run' | 'code' | 'readme'>(defaultTab);
  const [envValues, setEnvValues] = useState<Record<string, string>>({});
  const [envFileValues, setEnvFileValues] = useState<Record<string, string>>({});
  const [executing, setExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null);
  const [detectedParameters, setDetectedParameters] = useState<string[]>([]);

  useEffect(() => {
    if (isOpen && filePath) {
      // Smart default tab selection based on whether script has parameters
      let smartDefaultTab: 'params' | 'run' | 'code' | 'readme';
      if (fileName === 'get-access-token.js') {
        // Auth script: README first
        smartDefaultTab = 'readme';
      } else if (detectedParameters.length > 0) {
        // Has parameters: Parameters first
        smartDefaultTab = 'params';
      } else {
        // No parameters: Run Script (Response) first
        smartDefaultTab = 'run';
      }
      setActiveTab(smartDefaultTab);
      fetchCode();
      if (useEnvFile) {
        fetchEnvFile();
      }
    }
  }, [isOpen, filePath, useEnvFile, fileName, detectedParameters.length]);

  // Set default auth values for authentication script
  useEffect(() => {
    if (fileName === 'get-access-token.js' && !envValues['baseURL']) {
      // Set defaults for auth script
      handleEnvChange('baseURL', 'https://aws-api.sigmacomputing.com/v2');
      handleEnvChange('authURL', 'https://aws-api.sigmacomputing.com/v2/auth/token');
    }
  }, [fileName, envValues]);

  // Detect parameters when code changes
  useEffect(() => {
    if (code) {
      const envVarPattern = /process\.env\.([A-Z_]+)/g;
      const matches = code.match(envVarPattern) || [];
      
      const parameters = new Set<string>();
      matches.forEach(match => {
        const paramName = match.replace('process.env.', '');
        // Filter out auth parameters since they're handled centrally
        if (!['CLIENT_ID', 'SECRET', 'authURL', 'baseURL'].includes(paramName)) {
          parameters.add(paramName);
        }
      });
      
      setDetectedParameters(Array.from(parameters));
    }
  }, [code]);


  const fetchCode = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`/api/code?path=${encodeURIComponent(filePath)}`);
      if (!response.ok) {
        throw new Error('Failed to fetch code');
      }
      const data = await response.json();
      setCode(data.content);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(code);
    alert('Code copied to clipboard!');
  };

  const copyFilePath = () => {
    navigator.clipboard.writeText(filePath);
    alert('File path copied to clipboard!');
  };

  const fetchEnvFile = async () => {
    try {
      const response = await fetch('/api/env');
      if (response.ok) {
        const data = await response.json();
        setEnvFileValues(data.values);
        // Pre-fill envValues with file values when useEnvFile is true
        if (data.values) {
          setEnvValues(data.values);
        }
      }
    } catch (err) {
      console.error('Failed to fetch env file values:', err);
    }
  };

  const executeScript = async () => {
    setExecuting(true);
    setExecutionResult(null);
    
    try {
      let currentEnvValues = envValues;
      
      // If using env file, refresh the values before execution
      if (useEnvFile) {
        const response = await fetch('/api/env');
        if (response.ok) {
          const data = await response.json();
          setEnvFileValues(data.values);
          // Use the fresh values directly instead of waiting for state update
          currentEnvValues = data.values;
          setEnvValues(data.values);
        }
      }
      
      // Add core auth variables (will be filled from centralized auth, direct input, or env file)
      const coreAuthVars = {
        'CLIENT_ID': useEnvFile ? (currentEnvValues['CLIENT_ID'] || envFileValues['CLIENT_ID'] || '') : (currentEnvValues['CLIENT_ID'] || ''),
        'SECRET': useEnvFile ? (currentEnvValues['SECRET'] || envFileValues['SECRET'] || '') : (currentEnvValues['SECRET'] || ''),
        'authURL': useEnvFile ? (envFileValues['authURL'] || 'https://aws-api.sigmacomputing.com/v2/auth/token') : 'https://aws-api.sigmacomputing.com/v2/auth/token',
        'baseURL': useEnvFile ? (envFileValues['baseURL'] || 'https://aws-api.sigmacomputing.com/v2') : 'https://aws-api.sigmacomputing.com/v2'
      };
      
      // Validate that required auth credentials are provided (for auth script only)
      if (fileName === 'get-access-token.js' && (!coreAuthVars.CLIENT_ID || !coreAuthVars.SECRET)) {
        setExecutionResult({
          output: '',
          error: 'Authentication required: Please provide CLIENT_ID and SECRET credentials in the Parameters tab.',
          success: false,
          timestamp: new Date().toISOString(),
          httpStatus: 401,
          httpStatusText: 'Unauthorized'
        });
        setExecuting(false);
        return;
      }
      
      const allEnvVariables = { ...coreAuthVars, ...currentEnvValues };

      const response = await fetch('/api/execute', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          filePath,
          envVariables: allEnvVariables
        })
      });
      
      const result = await response.json();
      setExecutionResult(result);
      
      // If this is an auth script and execution was successful, notify parent
      if (result.success && fileName === 'get-access-token.js' && onTokenObtained) {
        onTokenObtained();
      }
      
      if (!response.ok) {
        throw new Error(result.error || 'Execution failed');
      }
    } catch (err) {
      setExecutionResult({
        output: '',
        error: err instanceof Error ? err.message : 'Unknown error',
        success: false,
        timestamp: new Date().toISOString()
      });
    } finally {
      setExecuting(false);
    }
  };

  const handleEnvChange = (key: string, value: string) => {
    setEnvValues(prev => ({
      ...prev,
      [key]: value
    }));
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">{fileName}</h3>
            <p className="text-sm text-gray-500 font-mono">{filePath}</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl font-bold"
          >
            ×
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200">
          {fileName === 'get-access-token.js' ? (
            // Auth script tab order: README → Parameters
            <>
              <button
                onClick={() => setActiveTab('readme')}
                className={`px-4 py-2 text-sm font-medium ${
                  activeTab === 'readme'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                📖 README
              </button>
              <button
                onClick={() => setActiveTab('params')}
                className={`px-4 py-2 text-sm font-medium ${
                  activeTab === 'params'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                ⚙️ Parameters
              </button>
              <button
                onClick={() => setActiveTab('run')}
                className={`px-4 py-2 text-sm font-medium ${
                  activeTab === 'run'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                ▶️ Run Script
              </button>
              <button
                onClick={() => setActiveTab('code')}
                className={`px-4 py-2 text-sm font-medium ${
                  activeTab === 'code'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                📄 View Recipe
              </button>
            </>
          ) : (
            // Regular recipe tab order: Parameters → Response → README → View Recipe (if params exist)
            // Or: Response → README → View Recipe (if no params)
            <>
              {detectedParameters.length > 0 && (
                <button
                  onClick={() => setActiveTab('params')}
                  className={`px-4 py-2 text-sm font-medium ${
                    activeTab === 'params'
                      ? 'text-blue-600 border-b-2 border-blue-600'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  ⚙️ Parameters
                </button>
              )}
              <button
                onClick={() => setActiveTab('run')}
                className={`px-4 py-2 text-sm font-medium ${
                  activeTab === 'run'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                📊 Response
              </button>
              <button
                onClick={() => setActiveTab('readme')}
                className={`px-4 py-2 text-sm font-medium ${
                  activeTab === 'readme'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                📖 README
              </button>
              <button
                onClick={() => setActiveTab('code')}
                className={`px-4 py-2 text-sm font-medium ${
                  activeTab === 'code'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                📄 View Recipe
              </button>
            </>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto min-h-0">
          {activeTab === 'readme' ? (
            <div className="p-6">
              {fileName === 'get-access-token.js' ? (
                <div className="space-y-6">
                  <div className="bg-gradient-to-r from-amber-50 to-orange-50 border-l-4 border-amber-500 rounded-lg p-6">
                    <div className="flex items-center mb-4">
                      <span className="text-2xl mr-3">🔐</span>
                      <h3 className="text-xl font-semibold text-gray-800">Authentication Setup</h3>
                      <span className="ml-3 bg-amber-100 text-amber-800 text-xs font-medium px-2.5 py-0.5 rounded-full">
                        Required First
                      </span>
                    </div>
                    
                    <p className="text-gray-700 mb-4">
                      Configure your API credentials and generate a bearer token for accessing Sigma&rsquo;s REST API. 
                      Tokens are cached for reuse across recipes during your session.
                    </p>
                    
                    <div className="mb-4">
                      <p className="text-sm font-medium text-gray-700 mb-2">Required Environment Variables:</p>
                      <div className="flex flex-wrap gap-2">
                        <span className="bg-amber-100 text-amber-800 text-xs font-mono px-2 py-1 rounded">CLIENT_ID</span>
                        <span className="bg-amber-100 text-amber-800 text-xs font-mono px-2 py-1 rounded">SECRET</span>
                        <span className="bg-amber-100 text-amber-800 text-xs font-mono px-2 py-1 rounded">authURL</span>
                        <span className="bg-amber-100 text-amber-800 text-xs font-mono px-2 py-1 rounded">baseURL</span>
                      </div>
                    </div>
                    
                    <div className="flex items-center space-x-4 text-sm text-gray-600">
                      <span className="flex items-center">
                        <svg className="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Start Here
                      </span>
                      <a 
                        href="https://quickstarts.sigmacomputing.com/guide/developers_api_code_samples/index.html#0"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:text-blue-800 underline"
                      >
                        Instructions →
                      </a>
                    </div>
                    
                    <div className="mt-4 pt-4 border-t border-amber-200 text-xs text-gray-600">
                      <span className="font-medium">Token Duration:</span> 1 hour (cached for session)
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold text-gray-800">Recipe Information</h3>
                  <p className="text-gray-600">
                    This recipe demonstrates how to use the Sigma API for specific use cases.
                    Refer to the code and run the script to see the results.
                  </p>
                </div>
              )}
            </div>
          ) : activeTab === 'params' ? (
            <div className="p-4">
              {fileName === 'get-access-token.js' ? (
                <div className="space-y-4">
                  <div className="mb-4">
                    <h4 className="text-md font-semibold text-gray-800 mb-2">🔐 Authentication Credentials</h4>
                    <p className="text-sm text-gray-600">
                      Enter your Sigma API credentials to authenticate
                    </p>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium mb-1 text-gray-700">
                      Server Endpoint
                      <span className="text-red-600 ml-1">*</span>
                    </label>
                    <select
                      value={envValues['baseURL'] || 'https://aws-api.sigmacomputing.com/v2'}
                      onChange={(e) => {
                        const baseURL = e.target.value;
                        // Handle different URL patterns for auth endpoints
                        let authURL;
                        if (baseURL === 'https://api.sigmacomputing.com') {
                          authURL = baseURL + '/v2/auth/token';
                        } else {
                          authURL = baseURL + '/auth/token';
                        }
                        handleEnvChange('baseURL', baseURL);
                        handleEnvChange('authURL', authURL);
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    >
                      <option value="https://api.sigmacomputing.com">
                        https://api.sigmacomputing.com - GCP hosted organizations
                      </option>
                      <option value="https://aws-api.sigmacomputing.com/v2">
                        https://aws-api.sigmacomputing.com/v2 - AWS US (West) hosted organizations
                      </option>
                      <option value="https://api.us-a.aws.sigmacomputing.com">
                        https://api.us-a.aws.sigmacomputing.com - AWS US (East) hosted organizations  
                      </option>
                      <option value="https://api.ca.aws.sigmacomputing.com">
                        https://api.ca.aws.sigmacomputing.com - AWS Canada hosted organizations
                      </option>
                      <option value="https://api.eu.aws.sigmacomputing.com">
                        https://api.eu.aws.sigmacomputing.com - AWS Europe hosted organizations
                      </option>
                      <option value="https://api.au.aws.sigmacomputing.com">
                        https://api.au.aws.sigmacomputing.com - AWS Australia and APAC hosted organizations
                      </option>
                      <option value="https://api.uk.aws.sigmacomputing.com">
                        https://api.uk.aws.sigmacomputing.com - AWS UK hosted organizations
                      </option>
                      <option value="https://api.us.azure.sigmacomputing.com">
                        https://api.us.azure.sigmacomputing.com - Azure US hosted organizations
                      </option>
                      <option value="https://api.eu.azure.sigmacomputing.com">
                        https://api.eu.azure.sigmacomputing.com - Azure Europe hosted organizations
                      </option>
                      <option value="https://api.ca.azure.sigmacomputing.com">
                        https://api.ca.azure.sigmacomputing.com - Azure Canada hosted organizations
                      </option>
                      <option value="https://api.uk.azure.sigmacomputing.com">
                        https://api.uk.azure.sigmacomputing.com - Azure United Kingdom hosted organizations
                      </option>
                    </select>
                    <p className="mt-1 text-xs text-gray-600">
                      Auth URL: {envValues['authURL'] || 'https://aws-api.sigmacomputing.com/v2/auth/token'}
                    </p>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium mb-1 text-gray-700">
                      Client ID
                      <span className="text-red-600 ml-1">*</span>
                    </label>
                    <input
                      type="text"
                      value={envValues['CLIENT_ID'] || ''}
                      onChange={(e) => handleEnvChange('CLIENT_ID', e.target.value)}
                      placeholder="Enter your Sigma Client ID"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium mb-1 text-gray-700">
                      Client Secret
                      <span className="text-red-600 ml-1">*</span>
                    </label>
                    <input
                      type="password"
                      value={envValues['SECRET'] || ''}
                      onChange={(e) => handleEnvChange('SECRET', e.target.value)}
                      placeholder="Enter your Sigma Client Secret"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  
                  <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                    <div className="flex">
                      <div className="flex-shrink-0">
                        <svg className="h-5 w-5 text-blue-400" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                        </svg>
                      </div>
                      <div className="ml-3">
                        <p className="text-sm text-blue-800">
                          <strong>Don&rsquo;t have credentials?</strong>{' '}
                          <a 
                            href="https://quickstarts.sigmacomputing.com/guide/developers_api_code_samples/index.html#0"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline hover:text-blue-900"
                          >
                            Follow the setup instructions →
                          </a>
                        </p>
                      </div>
                    </div>
                  </div>
                  
                  <div className="mt-6 pt-4 border-t border-gray-200">
                    <button
                      onClick={() => {
                        setActiveTab('run');
                        // Auto-execute after switching tabs
                        setTimeout(() => {
                          if (!executing) {
                            executeScript();
                          }
                        }, 100);
                      }}
                      className="w-full bg-green-600 text-white px-6 py-3 rounded-lg text-sm font-medium hover:bg-green-700 transition-colors flex items-center justify-center"
                      disabled={!envValues['CLIENT_ID'] || !envValues['SECRET']}
                    >
                      <span className="mr-2">🔐</span>
                      Authenticate Now
                    </button>
                    <p className="mt-2 text-xs text-gray-600 text-center">
                      This will switch to Run Script tab and execute authentication
                    </p>
                  </div>

                  {useEnvFile && (
                    <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                      <p className="text-sm text-amber-800">
                        📁 Environment file mode is enabled. Values above will be ignored in favor of the .env file.
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="mb-4">
                    <h4 className="text-md font-semibold text-gray-800 mb-2">📋 Recipe Parameters</h4>
                    <p className="text-sm text-gray-600">
                      Configure the environment variables for this recipe
                    </p>
                  </div>
                  
                  {detectedParameters.map((paramName) => (
                    <div key={paramName}>
                      <label className="block text-sm font-medium mb-1 text-gray-700">
                        {paramName.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase())}
                        <span className="text-red-600 ml-1">*</span>
                      </label>
                      <input
                        type="text"
                        value={envValues[paramName] || ''}
                        onChange={(e) => handleEnvChange(paramName, e.target.value)}
                        placeholder={`Enter ${paramName.toLowerCase()}...`}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                  ))}
                  
                  <div className="mt-6 pt-4 border-t border-gray-200">
                    <button
                      onClick={() => {
                        setActiveTab('run');
                        setTimeout(() => {
                          if (!executing) {
                            executeScript();
                          }
                        }, 100);
                      }}
                      disabled={executing}
                      className={`w-full px-6 py-3 rounded-lg text-sm font-medium transition-colors flex items-center justify-center ${
                        executing
                          ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                          : 'bg-green-600 text-white hover:bg-green-700'
                      }`}
                    >
                      {executing ? (
                        <>
                          <span className="animate-spin rounded-full h-4 w-4 border-b border-white inline-block mr-2"></span>
                          Executing...
                        </>
                      ) : (
                        <>
                          <span className="mr-2">▶️</span>
                          Run Script
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : activeTab === 'run' ? (
            <div className="p-4">
              {/* Copy Code and Run Script Buttons */}
              <div className="flex justify-between items-center mb-6">
                <button
                  onClick={executeScript}
                  disabled={executing}
                  className={`px-6 py-2 rounded-lg text-sm font-medium ${
                    executing
                      ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      : 'bg-green-600 text-white hover:bg-green-700'
                  }`}
                >
                  {executing ? (
                    <>
                      <span className="animate-spin rounded-full h-4 w-4 border-b border-white inline-block mr-2"></span>
                      Executing...
                    </>
                  ) : (
                    '▶️ Run Script'
                  )}
                </button>
                <button
                  onClick={copyToClipboard}
                  className="bg-gray-100 text-gray-700 px-3 py-2 rounded text-sm hover:bg-gray-200 transition-colors"
                  disabled={!code}
                >
                  📋 Copy Code
                </button>
              </div>

              {/* Execution Results */}
              {executionResult && (
                <div className="border rounded-lg bg-gray-50">
                  {/* Header with Status and Response Code */}
                  <div className={`px-4 py-3 border-b ${
                    executionResult.success ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
                  }`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center">
                        <span className={`text-lg mr-2 ${executionResult.success ? 'text-green-600' : 'text-red-600'}`}>
                          {executionResult.success ? '✅' : '❌'}
                        </span>
                        <span className={`font-semibold ${executionResult.success ? 'text-green-800' : 'text-red-800'}`}>
                          {executionResult.success 
                            ? `Success${executionResult.httpStatus ? ` (${executionResult.httpStatus})` : ''}`
                            : `Error${executionResult.httpStatus ? ` (${executionResult.httpStatus})` : ''}`
                          }
                        </span>
                      </div>
                      <span className="text-xs text-gray-500">
                        {new Date(executionResult.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                  </div>
                  
                  {/* Response Body */}
                  <div className="p-4">
                    {executionResult.output && (
                      <div className="mb-4">
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-sm font-semibold text-gray-700">Console Output:</p>
                          <button
                            onClick={() => navigator.clipboard.writeText(executionResult.output)}
                            className="text-xs text-blue-600 hover:text-blue-800 underline"
                          >
                            Copy Output
                          </button>
                        </div>
                        <pre className="bg-white border p-3 rounded text-xs font-mono whitespace-pre-wrap overflow-auto max-h-64 border-gray-300">
                          {executionResult.output}
                        </pre>
                      </div>
                    )}
                    {executionResult.error && (
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-sm font-semibold text-red-700">Error Details:</p>
                          <button
                            onClick={() => navigator.clipboard.writeText(executionResult.error)}
                            className="text-xs text-blue-600 hover:text-blue-800 underline"
                          >
                            Copy Error
                          </button>
                        </div>
                        <pre className="bg-red-50 border border-red-200 p-3 rounded text-xs font-mono whitespace-pre-wrap overflow-auto max-h-64">
                          {executionResult.error}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            // Code tab
            loading ? (
              <div className="flex items-center justify-center p-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                <span className="ml-3 text-gray-600">Loading code...</span>
              </div>
            ) : error ? (
              <div className="p-8 text-center">
                <p className="text-red-600 mb-4">Error loading code: {error}</p>
                <button 
                  onClick={fetchCode}
                  className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
                >
                  Retry
                </button>
              </div>
            ) : (
              <div className="p-4">
                <div className="flex justify-end mb-4">
                  <button
                    onClick={copyToClipboard}
                    className="bg-blue-600 text-white px-3 py-2 rounded text-sm hover:bg-blue-700 transition-colors"
                    disabled={!code}
                  >
                    📋 Copy Code
                  </button>
                </div>
                <pre className="text-sm font-mono bg-gray-50 border rounded p-4 overflow-auto whitespace-pre-wrap">
                  <code className="language-javascript">{code}</code>
                </pre>
              </div>
            )
          )}
        </div>

      </div>
    </div>
  );
}