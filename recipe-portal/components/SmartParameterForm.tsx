'use client';

import { useState, useEffect } from 'react';
import { SmartParameter } from '../lib/smartParameters';

interface SmartParameterFormProps {
  parameters: SmartParameter[];
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
  authToken?: string | null;
  baseURL?: string; // Add baseURL prop to prevent race conditions
  onRunScript?: () => void;
  executing?: boolean;
  context?: 'recipe' | 'api';
  onShowReadme?: () => void;
}

interface ResourceData {
  id: string;
  name: string;
  description?: string;
  [key: string]: any;
}

export function SmartParameterForm({ 
  parameters, 
  values, 
  onChange, 
  authToken,
  baseURL = 'https://aws-api.sigmacomputing.com/v2', // Default fallback baseURL
  onRunScript,
  executing = false,
  context = 'recipe',
  onShowReadme
}: SmartParameterFormProps) {
  const [resourceData, setResourceData] = useState<Record<string, ResourceData[]>>({});
  const [loadingResources, setLoadingResources] = useState<Record<string, boolean>>({});

  // Fetch resource data for dropdown parameters
  useEffect(() => {
    console.log('SmartParameterForm useEffect triggered - authToken:', authToken?.substring(0,20) + '...', 'baseURL:', baseURL);
    
    if (!authToken) {
      setResourceData({});
      return;
    }
    
    // Create an abort controller for this effect run
    const abortController = new AbortController();
    let isCancelled = false;
    
    const fetchResources = async () => {
      // Clear existing resource data at start
      setResourceData({});
      
      const resourceTypes = new Set<string>();
      parameters.forEach(param => {
        if (param.resourceType) {
          resourceTypes.add(param.resourceType);
        }
      });

      for (const resourceType of Array.from(resourceTypes)) {
        // Check if this effect was cancelled
        if (abortController.signal.aborted || isCancelled) {
          console.log(`Effect cancelled, aborting ${resourceType} request`);
          return;
        }
        
        // Check if this resource type has dependencies
        const param = parameters.find(p => p.resourceType === resourceType);
        const dependentValue = param?.dependsOn ? values[param.dependsOn] : null;
        
        // Create a cache key that includes dependencies
        const cacheKey = param?.dependsOn ? `${resourceType}_${dependentValue}` : resourceType;
        
        // Skip loading if dependency is not met
        if (param?.dependsOn && !dependentValue) {
          continue;
        }
        
        setLoadingResources(prev => ({ ...prev, [resourceType]: true }));
        
        try {
          let url = `/api/resources?type=${resourceType}&token=${encodeURIComponent(authToken)}&baseURL=${encodeURIComponent(baseURL)}`;
          if (param?.dependsOn && dependentValue) {
            // Map parameter names to expected API parameter names
            const paramMapping: Record<string, string> = {
              'WORKBOOK_ID': 'workbookId',
              'MEMBER_ID': 'memberId',
              'TEAM_ID': 'teamId'
            };
            const apiParamName = paramMapping[param.dependsOn] || param.dependsOn.toLowerCase();
            url += `&${apiParamName}=${encodeURIComponent(dependentValue)}`;
          }
          
          console.log(`Fetching ${resourceType} with token ${authToken?.substring(0,20)}...`);
          console.log(`Dependent value for ${param?.dependsOn}:`, dependentValue);
          
          const response = await fetch(url, { signal: abortController.signal });
          
          // Final check before processing response
          if (abortController.signal.aborted || isCancelled) {
            console.log(`Effect cancelled after ${resourceType} response, discarding results`);
            return;
          }
          
          if (response.ok) {
            const data = await response.json();
            console.log(`Received ${resourceType} data (${data.data?.length || 0} items) with token ${authToken?.substring(0,20)}...`);
            
            // Only update state if not cancelled
            if (!abortController.signal.aborted && !isCancelled) {
              setResourceData(prev => ({ ...prev, [cacheKey]: data.data || [] }));
            }
          } else {
            console.warn(`Failed to fetch ${resourceType}:`, response.statusText);
            const errorText = await response.text();
            console.warn(`Error response:`, errorText);
          }
        } catch (error) {
          if (error instanceof Error && error.name === 'AbortError') {
            console.log(`Fetch ${resourceType} aborted`);
          } else {
            console.warn(`Error fetching ${resourceType}:`, error);
          }
        } finally {
          if (!abortController.signal.aborted && !isCancelled) {
            setLoadingResources(prev => ({ ...prev, [resourceType]: false }));
          }
        }
      }
    };

    fetchResources();

    // Cleanup function to cancel ongoing requests when token changes
    return () => {
      console.log('Cleaning up SmartParameterForm effect - cancelling ongoing requests');
      isCancelled = true;
      abortController.abort();
    };
  }, [parameters, authToken, baseURL, values]);

  const handleChange = (paramName: string, value: string) => {
    const newValues = { ...values, [paramName]: value };
    
    
    // Clear dependent parameters when a parent parameter changes
    parameters.forEach(param => {
      if (param.dependsOn === paramName) {
        newValues[param.name] = '';
        // Also clear cached resource data for dependent parameters
        const dependentCacheKey = `${param.resourceType}_${value}`;
        setResourceData(prev => {
          const updated = { ...prev };
          Object.keys(updated).forEach(key => {
            if (key.startsWith(`${param.resourceType}_`) && key !== dependentCacheKey) {
              delete updated[key];
            }
          });
          return updated;
        });
      }
    });
    
    onChange(newValues);
  };

  const renderParameter = (param: SmartParameter) => {
    const currentValue = values[param.name] || '';

    // Handle date inputs
    if (param.type === 'date') {
      // Convert stored value to YYYY-MM-DD format if it's in MM/DD/YYYY format
      const convertToISODate = (dateStr: string): string => {
        if (!dateStr) return '';
        
        // If it's already in YYYY-MM-DD format, return as-is
        if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
          return dateStr;
        }
        
        // If it's in MM/DD/YYYY format, convert it
        if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(dateStr)) {
          const [month, day, year] = dateStr.split('/');
          return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
        }
        
        return dateStr;
      };

      // Convert from YYYY-MM-DD to display format and back
      const displayValue = currentValue;
      
      return (
        <div key={param.name}>
          <label className="block text-sm font-medium mb-1 text-gray-700">
            {param.friendlyName}
            {param.required && <span className="text-red-600 ml-1">*</span>}
          </label>
          <p className="text-xs text-gray-600 mb-2">{param.description} (Format: YYYY-MM-DD)</p>
          <input
            type="date"
            value={convertToISODate(currentValue)}
            onChange={(e) => {
              // HTML date input always provides YYYY-MM-DD format
              handleChange(param.name, e.target.value);
            }}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          {currentValue && (
            <p className="mt-1 text-xs text-green-600">
              API format: {convertToISODate(currentValue)}
            </p>
          )}
        </div>
      );
    }

    // Handle resource-based dropdowns
    if (param.resourceType && authToken) {
      // Check if this parameter depends on another parameter
      const dependentValue = param.dependsOn ? values[param.dependsOn] : null;
      const cacheKey = param.dependsOn ? `${param.resourceType}_${dependentValue}` : param.resourceType;
      
      const resources = resourceData[cacheKey] || [];
      const isLoading = loadingResources[param.resourceType];
      const isDisabled = param.dependsOn && !dependentValue;
      
      // Debug logging
      if (param.resourceType === 'accountTypes') {
        console.log('AccountTypes debug:', {
          resources,
          isLoading,
          resourceDataKeys: Object.keys(resourceData),
          fullResourceData: resourceData
        });
      }

      return (
        <div key={param.name}>
          <label className="block text-sm font-medium mb-1 text-gray-700">
            {param.friendlyName}
            {param.required && <span className="text-red-600 ml-1">*</span>}
          </label>
          <p className="text-xs text-gray-600 mb-2">{param.description}</p>
          
          {isDisabled ? (
            <div className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm bg-gray-50 text-gray-500">
              Please select {param.dependsOn?.replace('_', ' ').toLowerCase()} first
            </div>
          ) : isLoading ? (
            <div className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm bg-gray-50 flex items-center">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
              Loading {param.resourceType}...
            </div>
          ) : resources.length > 0 ? (
            <select
              value={currentValue}
              onChange={(e) => handleChange(param.name, e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            >
              <option value="">Select {param.friendlyName}...</option>
              {resources.map((resource) => (
                <option key={resource.id} value={resource.id}>
                  {resource.name} {param.resourceType !== 'workbookElements' && `(${resource.id})`}
                </option>
              ))}
            </select>
          ) : param.options && param.options.length > 0 ? (
            <select
              value={currentValue}
              onChange={(e) => handleChange(param.name, e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 bg-yellow-50"
            >
              <option value="">Select {param.friendlyName}...</option>
              {param.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          ) : (
            <div className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm bg-yellow-50 text-yellow-800">
              No {param.resourceType} available or authentication required
            </div>
          )}
          
          {currentValue && (
            <p className="mt-1 text-xs text-blue-600">
              Selected: {currentValue}
            </p>
          )}
        </div>
      );
    }

    // Handle predefined options
    if (param.type === 'select' && param.options) {
      return (
        <div key={param.name}>
          <label className="block text-sm font-medium mb-1 text-gray-700">
            {param.friendlyName}
            {param.required && <span className="text-red-600 ml-1">*</span>}
          </label>
          <p className="text-xs text-gray-600 mb-2">{param.description}</p>
          <select
            value={currentValue}
            onChange={(e) => handleChange(param.name, e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          >
            <option value="">{param.placeholder || `Select ${param.friendlyName}...`}</option>
            {param.options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      );
    }

    // Handle boolean parameters
    if (param.type === 'boolean') {
      return (
        <div key={param.name}>
          <label className="block text-sm font-medium mb-1 text-gray-700">
            {param.friendlyName}
            {param.required && <span className="text-red-600 ml-1">*</span>}
          </label>
          <p className="text-xs text-gray-600 mb-2">{param.description}</p>
          <select
            value={currentValue}
            onChange={(e) => handleChange(param.name, e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          >
            <option value="">Select...</option>
            <option value="true">True</option>
            <option value="false">False</option>
          </select>
        </div>
      );
    }

    // Handle JSON parameters
    if (param.type === 'json') {
      return (
        <div key={param.name}>
          <label className="block text-sm font-medium mb-1 text-gray-700">
            {param.friendlyName}
            {param.required && <span className="text-red-600 ml-1">*</span>}
          </label>
          <p className="text-xs text-gray-600 mb-2">{param.description}</p>
          <textarea
            value={currentValue}
            onChange={(e) => handleChange(param.name, e.target.value)}
            placeholder={param.placeholder}
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
        </div>
      );
    }

    // Handle regular input fields
    const inputType = param.type === 'number' ? 'number' : 
                     param.type === 'email' ? 'email' : 'text';

    return (
      <div key={param.name}>
        <label className="block text-sm font-medium mb-1 text-gray-700">
          {param.friendlyName}
          {param.required && <span className="text-red-600 ml-1">*</span>}
        </label>
        <p className="text-xs text-gray-600 mb-2">{param.description}</p>
        <input
          type={inputType}
          value={currentValue}
          onChange={(e) => handleChange(param.name, e.target.value)}
          placeholder={param.placeholder}
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          {...(param.validation && {
            pattern: param.validation.pattern,
            minLength: param.validation.minLength,
            maxLength: param.validation.maxLength
          })}
        />
      </div>
    );
  };

  if (parameters.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div className="mb-4">
        <h4 className="text-md font-semibold text-gray-800 mb-2">
          📋 {context === 'api' ? 'API Parameters' : 'Recipe Parameters'}
        </h4>
        <p className="text-sm text-gray-600">
          Configure the parameters for this {context === 'api' ? 'API call' : 'recipe'}. Parameters with dropdowns will load available options automatically.
        </p>
        
        {/* Show download restrictions link for export recipes */}
        {parameters.some(p => p.name === 'LIMIT') && onShowReadme && (
          <p className="text-sm text-blue-600 mt-1">
            <button 
              onClick={onShowReadme}
              className="underline hover:text-blue-800"
            >
              📋 Click here for download restrictions and best practices
            </button>
          </p>
        )}
      </div>

      {!authToken && parameters.some(p => p.resourceType) && (
        <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <p className="text-sm text-amber-800">
            🔐 Some parameters require authentication to load dropdown options. Please authenticate first to see all available choices.
          </p>
        </div>
      )}

      {parameters.map(renderParameter)}

      {onRunScript && (
        <div className="mt-6 pt-4 border-t border-gray-200">
          <button
            onClick={onRunScript}
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
      )}
    </div>
  );
}