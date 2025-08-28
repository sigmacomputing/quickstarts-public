'use client';

import { useState } from 'react';
import { SmartParameterForm } from './SmartParameterForm';
import { SmartParameter } from '../lib/smartParameters';

interface QuickApiEndpoint {
  id: string;
  name: string;
  method: 'GET';
  path: string;
  description: string;
  category: 'List All' | 'Get Details';
  parameters: SmartParameter[];
  example?: string;
}

interface QuickApiModalProps {
  isOpen: boolean;
  onClose: () => void;
  endpoint: QuickApiEndpoint;
  hasValidToken: boolean;
  authToken?: string | null;
}

interface ExecutionResult {
  output: string;
  error: string;
  success: boolean;
  timestamp: string;
  httpStatus?: number;
  requestUrl?: string;
  requestMethod?: string;
}

export function QuickApiModal({ isOpen, onClose, endpoint, hasValidToken, authToken }: QuickApiModalProps) {
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [executing, setExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null);

  const executeEndpoint = async () => {
    setExecuting(true);
    setExecutionResult(null);
    
    try {
      // Build URL with path parameters
      let url = endpoint.path;
      endpoint.parameters.forEach(param => {
        const value = paramValues[param.name];
        if (value) {
          url = url.replace(`{${param.name}}`, value);
        }
      });

      const response = await fetch('/api/call', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          endpoint: url,
          method: endpoint.method,
          parameters: {
            path: {},
            query: {},
            header: {}
          }
        })
      });

      const result = await response.json();
      setExecutionResult({
        ...result,
        requestUrl: url,
        requestMethod: endpoint.method
      });
      
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

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div>
            <div className="flex items-center mb-2">
              <span className="text-xs font-medium px-2 py-1 rounded bg-green-100 text-green-800 mr-2">
                {endpoint.method}
              </span>
              <h3 className="text-lg font-semibold text-gray-900">{endpoint.name}</h3>
            </div>
            <code className="text-sm font-mono text-gray-700 bg-gray-100 px-2 py-1 rounded">
              {endpoint.path}
            </code>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl font-bold"
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto min-h-0 p-6">
          <p className="text-gray-600 mb-4">{endpoint.description}</p>
          {endpoint.example && (
            <p className="text-sm text-blue-600 mb-4 italic">{endpoint.example}</p>
          )}

          {!hasValidToken && (
            <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
              <div className="flex items-center">
                <span className="text-amber-600 mr-2">🔐</span>
                <div>
                  <p className="text-amber-800 font-medium">Authentication Required</p>
                  <p className="text-amber-700 text-sm">Please authenticate first to test this API endpoint.</p>
                </div>
              </div>
            </div>
          )}

          {/* Parameters */}
          {endpoint.parameters.length > 0 && (
            <div className="mb-6">
              <SmartParameterForm
                parameters={endpoint.parameters}
                values={paramValues}
                onChange={setParamValues}
                authToken={authToken}
                context="api"
              />
            </div>
          )}

          {/* Execute Button */}
          <div className="mb-6">
            <button
              onClick={executeEndpoint}
              disabled={executing || !hasValidToken}
              className={`w-full px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                executing
                  ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  : hasValidToken
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-gray-300 text-gray-500 cursor-not-allowed'
              }`}
            >
              {executing ? (
                <>
                  <span className="animate-spin rounded-full h-4 w-4 border-b border-white inline-block mr-2"></span>
                  Calling API...
                </>
              ) : (
                `▶️ Call ${endpoint.method} ${endpoint.path}`
              )}
            </button>
            {!hasValidToken && (
              <p className="mt-2 text-xs text-gray-600 text-center">
                Authentication required to call API
              </p>
            )}
          </div>

          {/* Parameter Summary */}
          {Object.keys(paramValues).length > 0 && Object.values(paramValues).some(v => v && v.trim()) && (
            <div className="mb-6 p-3 bg-blue-50 border border-blue-200 rounded-lg">
              <h4 className="text-sm font-semibold text-blue-800 mb-2">Request Parameters</h4>
              <div className="space-y-1">
                {endpoint.parameters.map(param => {
                  const value = paramValues[param.name];
                  if (!value || !value.trim()) return null;
                  
                  return (
                    <div key={param.name} className="text-xs text-blue-700">
                      <span className="font-medium">{param.friendlyName}:</span> <span className="font-mono">{value}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Results */}
          {executionResult && (
            <div className="border rounded-lg bg-gray-50">
              <div className={`px-4 py-3 border-b ${
                executionResult.success ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
              }`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <span className={`text-lg mr-2 ${executionResult.success ? 'text-green-600' : 'text-red-600'}`}>
                      {executionResult.success ? '✅' : '❌'}
                    </span>
                    <div>
                      <span className={`font-semibold ${executionResult.success ? 'text-green-800' : 'text-red-800'}`}>
                        {executionResult.success 
                          ? `Success${executionResult.httpStatus ? ` (${executionResult.httpStatus})` : ''}`
                          : `Error${executionResult.httpStatus ? ` (${executionResult.httpStatus})` : ''}`
                        }
                      </span>
                      {executionResult.requestUrl && (
                        <div className="text-xs text-gray-600 mt-1">
                          <span className="font-medium">{executionResult.requestMethod}</span> {executionResult.requestUrl}
                        </div>
                      )}
                    </div>
                  </div>
                  <span className="text-xs text-gray-500">
                    {new Date(executionResult.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              </div>
              
              <div className="p-4">
                {executionResult.output && (
                  <div className="mb-4">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm font-semibold text-gray-700">Response:</p>
                      <button
                        onClick={() => navigator.clipboard.writeText(executionResult.output)}
                        className="text-xs text-blue-600 hover:text-blue-800 underline"
                      >
                        Copy Response
                      </button>
                    </div>
                    <pre className="bg-white border p-3 rounded text-xs font-mono whitespace-pre-wrap overflow-auto max-h-64 border-gray-300">
                      {executionResult.output}
                    </pre>
                  </div>
                )}
                {executionResult.error && (
                  <div>
                    <p className="text-sm font-semibold text-red-700 mb-2">Error:</p>
                    <pre className="bg-red-50 border border-red-200 p-3 rounded text-xs font-mono whitespace-pre-wrap overflow-auto max-h-64">
                      {executionResult.error}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}