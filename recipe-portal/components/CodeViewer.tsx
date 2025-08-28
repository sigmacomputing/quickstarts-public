'use client';

import { useState, useEffect } from 'react';
import { detectSmartParameters, SmartParameter, analyzeRecipeCode } from '../lib/smartParameters';
import { SmartParameterForm } from './SmartParameterForm';

interface CodeViewerProps {
  isOpen: boolean;
  onClose: () => void;
  filePath: string;
  fileName: string;
  envVariables?: string[];
  useEnvFile?: boolean;
  onTokenObtained?: () => void;
  onTokenCleared?: () => void;
  defaultTab?: 'params' | 'run' | 'code' | 'readme';
  hasValidToken?: boolean;
  readmePath?: string;
}

interface ExecutionResult {
  output: string;
  error: string;
  success: boolean | null;
  timestamp: string;
  httpStatus?: number;
  httpStatusText?: string;
  downloadInfo?: {
    filename: string;
    localPath: string;
    size: number;
  };
}

// Function to open the downloads folder via API
const openDownloadsFolder = async () => {
  try {
    await fetch('/api/open-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: 'downloaded-files' })
    });
  } catch (error) {
    console.log('Could not open folder automatically. Please navigate to the downloaded-files folder manually.');
  }
};

export function CodeViewer({ isOpen, onClose, filePath, fileName, envVariables = [], useEnvFile = false, onTokenObtained, onTokenCleared, defaultTab = 'params', hasValidToken = false, readmePath }: CodeViewerProps) {
  const [code, setCode] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'params' | 'run' | 'code' | 'readme'>(defaultTab);
  const [envValues, setEnvValues] = useState<Record<string, string>>({});
  const [envFileValues, setEnvFileValues] = useState<Record<string, string>>({});
  const [executing, setExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(null);
  const [smartParameters, setSmartParameters] = useState<SmartParameter[]>([]);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [authBaseURL, setAuthBaseURL] = useState<string>('https://aws-api.sigmacomputing.com/v2'); // Store baseURL from auth config
  const [clearingToken, setClearingToken] = useState(false);
  const [storeKeysLocally, setStoreKeysLocally] = useState(false);
  const [hasStoredKeys, setHasStoredKeys] = useState(false);
  const [currentFormIsStored, setCurrentFormIsStored] = useState(false);

  // Reset form when modal is closed
  useEffect(() => {
    if (!isOpen) {
      setEnvValues({});
      setExecutionResult(null);
      setActiveTab(defaultTab);
      setError(null);
      setSetAsDefault(false);
      setCopyButtonText('Copy Output');
    }
  }, [isOpen, defaultTab]);
  const [saveNotification, setSaveNotification] = useState<string | null>(null);
  const [credentialSetName, setCredentialSetName] = useState('');
  const [availableCredentialSets, setAvailableCredentialSets] = useState<string[]>([]);
  const [selectedCredentialSet, setSelectedCredentialSet] = useState('');
  const [setAsDefault, setSetAsDefault] = useState(false);
  const [defaultCredentialSet, setDefaultCredentialSet] = useState<string | null>(null);
  const [copyButtonText, setCopyButtonText] = useState('Copy Output');
  const [customReadme, setCustomReadme] = useState<string | null>(null);
  const [readmeLoading, setReadmeLoading] = useState(false);

  useEffect(() => {
    if (isOpen && filePath) {
      // Smart default tab selection based on whether script has parameters
      let smartDefaultTab: 'params' | 'run' | 'code' | 'readme';
      if (fileName === 'get-access-token.js') {
        // Auth script: README first
        smartDefaultTab = 'readme';
      } else if (smartParameters.length > 0) {
        // Has parameters: Request first
        smartDefaultTab = 'params';
      } else {
        // No parameters: Run Script (Response) first
        smartDefaultTab = 'run';
      }
      
      // Only set the tab if it's not already set to avoid switching during execution
      // Don't switch tabs if we're currently executing or if we have results to show
      if (!executing && !executionResult && (activeTab === defaultTab || (activeTab === 'run' && smartParameters.length > 0))) {
        setActiveTab(smartDefaultTab);
      }
      fetchCode();
      checkAuthToken();
      if (useEnvFile) {
        fetchEnvFile();
      }
    } else if (!isOpen) {
      // Reset form when modal is closed
      if (fileName === 'get-access-token.js') {
        setEnvValues({
          'baseURL': 'https://aws-api.sigmacomputing.com/v2',
          'authURL': 'https://aws-api.sigmacomputing.com/v2/auth/token',
          'CLIENT_ID': '',
          'SECRET': ''
        });
      }
      setExecutionResult(null);
    }
  }, [isOpen, filePath, useEnvFile, fileName, executing, smartParameters.length, executionResult]);

  // Set default auth values for authentication script
  useEffect(() => {
    if (fileName === 'get-access-token.js' && !envValues['baseURL']) {
      // Set defaults for auth script
      handleEnvChange('baseURL', 'https://aws-api.sigmacomputing.com/v2');
      handleEnvChange('authURL', 'https://aws-api.sigmacomputing.com/v2/auth/token');
    }
  }, [fileName, envValues]);

  // Sync internal auth state with parent
  useEffect(() => {
    if (!hasValidToken) {
      setAuthToken(null);
      
      // Clear form fields when session is ended from main page
      if (fileName === 'get-access-token.js') {
        setEnvValues({
          'baseURL': 'https://aws-api.sigmacomputing.com/v2',
          'authURL': 'https://aws-api.sigmacomputing.com/v2/auth/token',
          'CLIENT_ID': '',
          'SECRET': ''
        });
      }
    }
  }, [hasValidToken, fileName]);

  // Load custom README if available
  useEffect(() => {
    if (readmePath && isOpen) {
      setReadmeLoading(true);
      fetch(`/api/readme?path=${encodeURIComponent(readmePath)}&format=json`)
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            setCustomReadme(data.content);
          }
        })
        .catch(error => {
          console.error('Failed to load custom README:', error);
        })
        .finally(() => {
          setReadmeLoading(false);
        });
    } else {
      setCustomReadme(null);
    }
  }, [readmePath, isOpen]);

  // Detect smart parameters when code changes
  useEffect(() => {
    if (code) {
      // Analyze code to find parameters
      const analysis = analyzeRecipeCode(code, { filePath });
      const detected = detectSmartParameters(analysis.suggestedParameters, { filePath });
      setSmartParameters(detected);
    }
  }, [code, filePath]);

  // Check for stored credentials when auth modal opens
  // Only auto-populate if form is empty (app startup scenario)
  useEffect(() => {
    const checkStoredCredentials = async () => {
      if (isOpen && fileName === 'get-access-token.js') {
        try {
          const response = await fetch('/api/keys?retrieve=true');
          if (response.ok) {
            const data = await response.json();
            setHasStoredKeys(data.hasStoredKeys);
            setAvailableCredentialSets(data.credentialSets || []);
            setDefaultCredentialSet(data.defaultSet || null);
            
            // Only auto-populate if fields are empty AND we have a valid token
            // This prevents re-population after "End Session" is clicked
            const hasEmptyFields = !envValues['CLIENT_ID'] && !envValues['SECRET'];
            
            if (data.hasStoredKeys && data.credentials && hasEmptyFields && hasValidToken) {
              // Auto-populate form with complete config on startup
              handleEnvChange('CLIENT_ID', data.credentials.clientId);
              handleEnvChange('SECRET', data.credentials.clientSecret);
              handleEnvChange('baseURL', data.credentials.baseURL);
              handleEnvChange('authURL', data.credentials.authURL);
              setStoreKeysLocally(true); // Check the checkbox since keys are stored
              setSelectedCredentialSet(data.defaultSet || '');
              setCurrentFormIsStored(true); // Mark current form as representing stored data
            }
          }
        } catch (error) {
          console.log('Error checking stored credentials:', error);
        }
      }
    };
    
    checkStoredCredentials();
  }, [isOpen, fileName]);

  const checkAuthToken = async () => {
    try {
      console.log('checkAuthToken: Fetching current token from /api/token');
      const response = await fetch('/api/token');
      if (response.ok) {
        const data = await response.json();
        console.log('checkAuthToken: Response from /api/token:', { hasValidToken: data.hasValidToken, clientId: data.clientId?.substring(0,8), baseURL: data.baseURL });
        if (data.hasValidToken && data.token) {
          console.log('checkAuthToken: Updating authToken and baseURL state');
          setAuthToken(data.token);
          if (data.baseURL) {
            setAuthBaseURL(data.baseURL); // Store baseURL to prevent race conditions
          }
        }
      }
    } catch (error) {
      console.log('No cached token available');
    }
  };

  const clearToken = async () => {
    setClearingToken(true);
    try {
      // Clear the session token
      const response = await fetch('/api/token/clear', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ clearAll: true })
      });
      
      if (response.ok) {
        setAuthToken(null);
        
        // Handle stored keys logic for auth script
        if (fileName === 'get-access-token.js') {
          if (!storeKeysLocally && hasStoredKeys) {
            // User unchecked the box - clear stored keys
            await fetch('/api/keys', { method: 'DELETE' });
            setHasStoredKeys(false);
          }
          
          // Always clear form fields on End Session
          // This implements the new UX flow:
          // - Session-only: fields cleared
          // - Storage enabled: fields cleared (will be restored on next startup)
          setEnvValues({
            'baseURL': 'https://aws-api.sigmacomputing.com/v2',
            'authURL': 'https://aws-api.sigmacomputing.com/v2/auth/token',
            'CLIENT_ID': '',
            'SECRET': ''
          });
        }
        
        if (onTokenCleared) {
          onTokenCleared();
        }
      } else {
        console.error('Failed to clear token');
      }
    } catch (error) {
      console.error('Error clearing token:', error);
    } finally {
      setClearingToken(false);
    }
  };


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

  const getDownloadFilename = (fileName: string, envValues: Record<string, string>) => {
    switch (fileName) {
      case 'export-workbook-element-csv.js':
        return envValues['EXPORT_FILENAME'] || 'export.csv';
      case 'export-workbook-pdf.js':
        return 'workbook-export.pdf';
      default:
        return 'download';
    }
  };

  const getDownloadContentType = (fileName: string) => {
    switch (fileName) {
      case 'export-workbook-element-csv.js':
        return 'text/csv';
      case 'export-workbook-pdf.js':
        return 'application/pdf';
      default:
        return 'application/octet-stream';
    }
  };

  const createBlobFromContent = (content: string, contentType: string) => {
    // All content from DOWNLOAD_RESULT protocol is base64 encoded
    try {
      const byteCharacters = atob(content);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      return new Blob([byteArray], { type: contentType });
    } catch (error) {
      // Fallback for non-base64 content (shouldn't happen with new protocol)
      console.warn('Failed to decode base64 content, treating as text:', error);
      return new Blob([content], { type: contentType });
    }
  };

  const handleStreamingDownload = async (filePath: string, envVariables: Record<string, string>, filename: string, contentType: string) => {
    try {
      const response = await fetch('/api/download-stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          filePath,
          envVariables,
          filename,
          contentType
        })
      });

      if (!response.ok) {
        throw new Error('Failed to start download stream');
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      let outputMessages: string[] = [];
      let jsonBuffer = ''; // Persistent buffer for handling split JSON messages
      
      // Initialize with starting message
      const startingMessage = `${new Date().toLocaleTimeString()} - Starting export process...`;
      outputMessages.push(startingMessage);
      
      setExecutionResult({
        output: startingMessage + '\n',
        error: '',
        success: null, // null indicates "in progress"
        timestamp: new Date().toISOString()
      });

      const decoder = new TextDecoder();
      
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;
        
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ') && line.trim() !== 'data: ') {
            const jsonPart = line.substring(6);
            jsonBuffer += jsonPart;
            
            // Try to parse the accumulated JSON
            try {
              const data = JSON.parse(jsonBuffer);
              // Success! Reset buffer and process the data
              jsonBuffer = '';
              const timestamp = new Date(data.timestamp).toLocaleTimeString();
              
              // Add message to beginning of array (newest first)
              // Show debug messages during development
              const prefix = '';
              const newMessage = `${timestamp} - ${prefix}${data.message}`;
              outputMessages.unshift(newMessage);
              
              // Keep only last 100 messages to see debug info
              if (outputMessages.length > 100) {
                outputMessages = outputMessages.slice(0, 100);
              }
              
              // Update the execution result with progressive output (newest first)
              setExecutionResult({
                output: outputMessages.join('\n') + '\n',
                error: '',
                success: null, // Keep as "in progress" until completion
                timestamp: data.timestamp
              });
              
              // Handle download completion with folder link
              if (data.type === 'success' && data.data && data.data.filename) {
                // Create clickable message to open downloads folder
                const folderMessage = `${timestamp} - 📁 File saved! Click here to open downloads folder`;
                const fileInfo = `${timestamp} - ✅ ${data.data.filename} (${Math.round(data.data.size / 1024)}KB) saved to downloaded-files/`;
                outputMessages.unshift(folderMessage);
                outputMessages.unshift(fileInfo);
                
                setExecutionResult({
                  output: outputMessages.join('\n') + '\n',
                  error: '',
                  success: true,
                  timestamp: data.timestamp,
                  downloadInfo: {
                    filename: data.data.filename,
                    localPath: data.data.localPath,
                    size: data.data.size
                  }
                });
                
                // Switch to Response tab to show the completion message
                setActiveTab('run');
              }
              
              // Handle errors
              if (data.type === 'error') {
                setExecutionResult({
                  output: outputMessages.join('\n') + '\n',
                  error: data.message,
                  success: false,
                  timestamp: data.timestamp
                });
                break;
              }
              
            } catch (e) {
              // JSON parsing failed - this might be a partial message
              // Keep the buffer and wait for more data, but limit buffer size to prevent memory issues
              if (jsonBuffer.length > 500000) { // 500KB limit
                console.error('JSON buffer too large, discarding:', jsonBuffer.substring(0, 100) + '...');
                jsonBuffer = '';
              }
              // Don't log every parse error as they're expected for partial messages
            }
          } else if (line.trim() === '' && jsonBuffer) {
            // Empty line might indicate end of an SSE message - try to parse what we have
            try {
              const data = JSON.parse(jsonBuffer);
              jsonBuffer = ''; // Reset on successful parse
              
              const timestamp = new Date(data.timestamp).toLocaleTimeString();
              const newMessage = `${timestamp} - ${data.message}`;
              outputMessages.unshift(newMessage);
              
              if (outputMessages.length > 100) {
                outputMessages = outputMessages.slice(0, 100);
              }
              
              setExecutionResult({
                output: outputMessages.join('\n') + '\n',
                error: '',
                success: null,
                timestamp: data.timestamp
              });
              
              // Handle download completion (same logic as above)
              if (data.type === 'success' && data.data && data.data.filename) {
                const folderMessage = `${timestamp} - 📁 File saved! Click here to open downloads folder`;
                const fileInfo = `${timestamp} - ✅ ${data.data.filename} (${Math.round(data.data.size / 1024)}KB) saved to downloaded-files/`;
                outputMessages.unshift(folderMessage);
                outputMessages.unshift(fileInfo);
                
                setExecutionResult({
                  output: outputMessages.join('\n') + '\n',
                  error: '',
                  success: true,
                  timestamp: data.timestamp,
                  downloadInfo: {
                    filename: data.data.filename,
                    localPath: data.data.localPath,
                    size: data.data.size
                  }
                });
                
                setActiveTab('run');
              }
              
              if (data.type === 'error') {
                setExecutionResult({
                  output: outputMessages.join('\n') + '\n',
                  error: data.message,
                  success: false,
                  timestamp: data.timestamp
                });
                return; // Exit the stream processing
              }
              
            } catch (e) {
              // Still couldn't parse - keep waiting for more data
            }
          }
        }
      }
      
    } catch (error) {
      setExecutionResult({
        output: '',
        error: error instanceof Error ? error.message : 'Unknown streaming error',
        success: false,
        timestamp: new Date().toISOString()
      });
    }
  };

  const executeScript = async () => {
    console.log('executeScript called');
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
      console.log('Validating auth credentials:', { fileName, coreAuthVars });
      if (fileName === 'get-access-token.js' && (!coreAuthVars.CLIENT_ID || !coreAuthVars.SECRET)) {
        console.log('Validation failed - missing credentials');
        setExecutionResult({
          output: '',
          error: 'Authentication required: Please provide CLIENT_ID and SECRET credentials in the Config tab.',
          success: false,
          timestamp: new Date().toISOString(),
          httpStatus: 401,
          httpStatusText: 'Unauthorized'
        });
        setExecuting(false);
        return;
      }
      
      console.log('Validation passed, continuing execution...');
      
      const allEnvVariables = { ...coreAuthVars, ...currentEnvValues };
      console.log('About to make API request with variables:', Object.keys(allEnvVariables));
      
      

      // Check if this is a download recipe
      const isDownloadRecipe = ['export-workbook-element-csv.js', 'export-workbook-pdf.js'].includes(fileName);
      
      let result;
      let response;
      
      if (isDownloadRecipe) {
        // Handle download recipes with streaming progress
        await handleStreamingDownload(filePath, allEnvVariables, getDownloadFilename(fileName, currentEnvValues), getDownloadContentType(fileName));
        return; // Exit early since streaming handles everything
      } else {
        // Handle regular recipes
        response = await fetch('/api/execute', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            filePath,
            envVariables: allEnvVariables
          })
        });
        
        console.log('API response received:', response.status, response.statusText);
        
        result = await response.json();
        console.log('API result:', result);
        setExecutionResult(result);
        console.log('ExecutionResult set, switching to run tab');
        setActiveTab('run');
      }
      
      // If this is an auth script and execution was successful, notify parent and refresh token
      if (result.success && fileName === 'get-access-token.js' && onTokenObtained) {
        onTokenObtained();
        
        // Switch to Response tab to show authentication result
        setActiveTab('run');
        
        // Store complete config (credentials + server settings) if user checked the box
        if (storeKeysLocally && allEnvVariables['CLIENT_ID'] && allEnvVariables['SECRET']) {
          try {
            const setName = credentialSetName.trim();
            if (!setName) {
              console.warn('Cannot save credentials without a name during authentication');
              // Continue with authentication but don't save
              setTimeout(() => checkAuthToken(), 1000);
              return;
            }
            await fetch('/api/keys', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                clientId: allEnvVariables['CLIENT_ID'],
                clientSecret: allEnvVariables['SECRET'],
                baseURL: allEnvVariables['baseURL'],
                authURL: allEnvVariables['authURL'],
                name: setName,
                setAsDefault: setAsDefault
              })
            });
            setHasStoredKeys(true);
            setCurrentFormIsStored(true); // Mark current form as stored
            
            // Show success notification for auto-save during authentication
            showSaveNotification(`Config "${setName}" saved during authentication!`);
            
            // Update available sets
            const updatedResponse = await fetch('/api/keys?list=true');
            if (updatedResponse.ok) {
              const updatedData = await updatedResponse.json();
              setAvailableCredentialSets(updatedData.credentialSets || []);
              setDefaultCredentialSet(updatedData.defaultSet || null);
            }
          } catch (error) {
            console.error('Failed to store credentials:', error);
          }
        }
        
        // Refresh the auth token for smart parameter dropdowns
        setTimeout(() => checkAuthToken(), 1000);
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

  const loadCredentialSet = async (setName: string) => {
    try {
      const response = await fetch(`/api/keys?retrieve=true&set=${encodeURIComponent(setName)}`);
      if (response.ok) {
        const data = await response.json();
        if (data.credentials) {
          // Load complete config: credentials + server settings
          handleEnvChange('CLIENT_ID', data.credentials.clientId);
          handleEnvChange('SECRET', data.credentials.clientSecret);
          handleEnvChange('baseURL', data.credentials.baseURL);
          handleEnvChange('authURL', data.credentials.authURL);
          setCredentialSetName(setName);
          setCurrentFormIsStored(true); // Mark current form as representing stored data
        }
      }
    } catch (error) {
      console.error('Failed to load credential set:', error);
    }
  };

  const handleEnvChange = (key: string, value: string) => {
    setEnvValues(prev => ({
      ...prev,
      [key]: value
    }));
    
    // Mark form as unsaved when credentials or server settings change
    if (['CLIENT_ID', 'SECRET', 'baseURL', 'authURL'].includes(key)) {
      setCurrentFormIsStored(false);
    }
  };

  const showSaveNotification = (message: string) => {
    setSaveNotification(message);
    setTimeout(() => setSaveNotification(null), 3000); // Auto-hide after 3 seconds
  };

  const deleteConfig = async (configName: string) => {
    try {
      await fetch(`/api/keys?config=${encodeURIComponent(configName)}`, {
        method: 'DELETE'
      });
      
      // Clear form if we deleted the currently selected config
      if (selectedCredentialSet === configName) {
        setSelectedCredentialSet('');
        setCredentialSetName('');
        handleEnvChange('CLIENT_ID', '');
        handleEnvChange('SECRET', '');
        handleEnvChange('baseURL', 'https://aws-api.sigmacomputing.com/v2');
        handleEnvChange('authURL', 'https://aws-api.sigmacomputing.com/v2/auth/token');
        setCurrentFormIsStored(false);
      }
      
      // Update available sets
      const updatedResponse = await fetch('/api/keys?list=true');
      if (updatedResponse.ok) {
        const updatedData = await updatedResponse.json();
        setAvailableCredentialSets(updatedData.credentialSets || []);
        setDefaultCredentialSet(updatedData.defaultSet || null);
        setHasStoredKeys(updatedData.credentialSets?.length > 0);
      }
      
      showSaveNotification(`Config "${configName}" deleted successfully!`);
    } catch (error) {
      console.error('Failed to delete config:', error);
      showSaveNotification('Failed to delete config. Please try again.');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">{fileName}</h3>
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
            // Auth script tab order: README → Config
            <>
              <button
                onClick={() => setActiveTab('readme')}
                className={`px-4 py-2 text-sm font-medium ${
                  activeTab === 'readme'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                README
              </button>
              <button
                onClick={() => setActiveTab('params')}
                className={`px-4 py-2 text-sm font-medium ${
                  activeTab === 'params'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                Request
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
                View Recipe
              </button>
            </>
          ) : (
            // Regular recipe tab order: Config → Response → README → View Recipe (if params exist)
            // Or: Response → README → View Recipe (if no params)
            <>
              {smartParameters.length > 0 && (
                <button
                  onClick={() => setActiveTab('params')}
                  className={`px-4 py-2 text-sm font-medium ${
                    activeTab === 'params'
                      ? 'text-blue-600 border-b-2 border-blue-600'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Request
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
                Response
              </button>
              <button
                onClick={() => setActiveTab('readme')}
                className={`px-4 py-2 text-sm font-medium ${
                  activeTab === 'readme'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                README
              </button>
              <button
                onClick={() => setActiveTab('code')}
                className={`px-4 py-2 text-sm font-medium ${
                  activeTab === 'code'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                View Recipe
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
                  {readmeLoading ? (
                    <div className="text-center py-8">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
                      <p className="text-gray-600">Loading README...</p>
                    </div>
                  ) : customReadme ? (
                    <div className="prose max-w-none">
                      <div 
                        className="markdown-content"
                        dangerouslySetInnerHTML={{ 
                          __html: (() => {
                            let html = customReadme;
                            
                            // Handle headers
                            html = html.replace(/^# (.+)$/gm, '<h1 class="text-2xl font-bold text-gray-800 mb-4 pb-2 border-b border-gray-200">$1</h1>');
                            html = html.replace(/^## (.+)$/gm, '<h2 class="text-xl font-semibold text-gray-700 mt-6 mb-3">$1</h2>');
                            html = html.replace(/^### (.+)$/gm, '<h3 class="text-lg font-medium text-gray-600 mt-4 mb-2">$1</h3>');
                            
                            // Handle inline code
                            html = html.replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono">$1</code>');
                            
                            // Handle bold text
                            html = html.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold">$1</strong>');
                            
                            // Handle links
                            html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="text-blue-600 hover:text-blue-800 underline">$1</a>');
                            
                            // Process lists line by line
                            const lines = html.split('\n');
                            const processed = [];
                            let inBulletList = false;
                            let inNumberList = false;
                            
                            for (let i = 0; i < lines.length; i++) {
                              const line = lines[i];
                              const trimmed = line.trim();
                              
                              if (trimmed.startsWith('- ')) {
                                if (!inBulletList) {
                                  processed.push('<ul class="list-disc list-inside mb-3 space-y-0">');
                                  inBulletList = true;
                                }
                                if (inNumberList) {
                                  processed.push('</ol>');
                                  inNumberList = false;
                                }
                                processed.push(`<li>${trimmed.substring(2)}</li>`);
                              } else if (/^\d+\. /.test(trimmed)) {
                                if (!inNumberList) {
                                  processed.push('<ol class="list-decimal list-inside mb-3 space-y-0">');
                                  inNumberList = true;
                                }
                                if (inBulletList) {
                                  processed.push('</ul>');
                                  inBulletList = false;
                                }
                                processed.push(`<li>${trimmed.replace(/^\d+\. /, '')}</li>`);
                              } else {
                                if (inBulletList) {
                                  processed.push('</ul>');
                                  inBulletList = false;
                                }
                                if (inNumberList) {
                                  processed.push('</ol>');
                                  inNumberList = false;
                                }
                                if (trimmed === '') {
                                  // Only add break if we're not between sections
                                  const nextLine = lines[i + 1]?.trim();
                                  if (nextLine && !nextLine.startsWith('#')) {
                                    processed.push('<div class="mb-3"></div>');
                                  }
                                } else if (trimmed.startsWith('#')) {
                                  // Headers are already processed, just add the line
                                  processed.push(line);
                                } else {
                                  // Regular text - just add it with minimal spacing
                                  processed.push(`<div class="mb-1">${line}</div>`);
                                }
                              }
                            }
                            
                            // Close any open lists
                            if (inBulletList) processed.push('</ul>');
                            if (inNumberList) processed.push('</ol>');
                            
                            return processed.join('\n');
                          })()
                        }}
                      />
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
              )}
            </div>
          ) : activeTab === 'params' ? (
            <div className="p-4">
              {fileName === 'get-access-token.js' ? (
                <div className="space-y-3">
                  {/* Header with Setup Guide in top-right corner */}
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="text-lg font-semibold text-gray-800 mb-1">🔐 Authentication Request</h4>
                      <p className="text-sm text-gray-600 mb-1">
                        Configure your Sigma API credentials to access the platform
                      </p>
                      <p className="text-xs italic text-red-600">
                        Once authenticated, use the &quot;End Session&quot; button in the header to clear your authentication
                      </p>
                    </div>
                    <a 
                      href="https://quickstarts.sigmacomputing.com/guide/developers_api_code_samples/index.html#0"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-3 py-1.5 border border-blue-300 text-blue-700 rounded-lg text-xs font-medium hover:bg-blue-50 transition-colors flex items-center"
                    >
                      📚 Setup Guide
                    </a>
                  </div>

                  {/* Load Existing Config - FIRST thing user does */}
                  {availableCredentialSets.length > 0 && (
                    <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                      <h5 className="text-sm font-medium text-green-900 mb-2">⚡ Quick Start - Load Saved Config</h5>
                      <div className="flex gap-2 items-end">
                        <div className="flex-1 max-w-sm">
                          <label className="block text-xs font-medium text-green-800 mb-1">
                            Select Config:
                          </label>
                          <select
                            value={selectedCredentialSet}
                            onChange={(e) => {
                              const setName = e.target.value;
                              setSelectedCredentialSet(setName);
                              if (setName) {
                                loadCredentialSet(setName);
                              }
                            }}
                            className="w-full px-3 py-2 border border-green-300 rounded-md text-sm focus:border-green-500 focus:ring-1 focus:ring-green-500 bg-white"
                          >
                            <option value="">Choose a saved config...</option>
                            {availableCredentialSets.map(name => (
                              <option key={name} value={name}>
                                {name}{defaultCredentialSet === name ? ' (Default)' : ''}
                              </option>
                            ))}
                          </select>
                        </div>
                        {selectedCredentialSet && (
                          <button
                            onClick={() => deleteConfig(selectedCredentialSet)}
                            className="px-2 py-2 text-xs bg-red-50 border border-red-300 text-red-700 rounded-md hover:bg-red-100 transition-colors"
                            title={`Delete "${selectedCredentialSet}" config`}
                          >
                            🗑️
                          </button>
                        )}
                        <button
                          onClick={() => {
                            // Clear form for new config
                            setSelectedCredentialSet('');
                            setCredentialSetName('');
                            handleEnvChange('CLIENT_ID', '');
                            handleEnvChange('SECRET', '');
                            handleEnvChange('baseURL', 'https://aws-api.sigmacomputing.com/v2');
                            handleEnvChange('authURL', 'https://aws-api.sigmacomputing.com/v2/auth/token');
                            setStoreKeysLocally(false);
                            setCurrentFormIsStored(false); // Reset stored indicator
                          }}
                          className="px-3 py-2 text-xs bg-white border border-green-300 text-green-700 rounded-md hover:bg-green-50 transition-colors"
                        >
                          ✨ New Config
                        </button>
                        <button
                          onClick={() => {
                            console.log('Authenticate Now clicked', { executing, envValues: { CLIENT_ID: envValues['CLIENT_ID'], SECRET: envValues['SECRET'] } });
                            if (!executing) {
                              executeScript();
                            }
                          }}
                          className="px-3 py-2 text-xs bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors ml-2"
                          disabled={!envValues['CLIENT_ID'] || !envValues['SECRET']}
                        >
                          🔐 Authenticate Now
                        </button>
                      </div>
                      <p className="text-xs text-green-700 mt-1">
                        {availableCredentialSets.length} saved config{availableCredentialSets.length !== 1 ? 's' : ''} available
                      </p>
                    </div>
                  )}

                  {/* Server Endpoint - Manual Configuration */}
                  <div className="max-w-lg">
                    <label className="block text-sm font-medium mb-2 text-gray-700">
                      Server Endpoint <span className="text-red-600">*</span>
                    </label>
                    <select
                      value={envValues['baseURL'] || 'https://aws-api.sigmacomputing.com/v2'}
                      onChange={(e) => {
                        const baseURL = e.target.value;
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
                      <option value="https://api.sigmacomputing.com">GCP hosted organizations</option>
                      <option value="https://aws-api.sigmacomputing.com/v2">AWS US (West) hosted organizations</option>
                      <option value="https://api.us-a.aws.sigmacomputing.com">AWS US (East) hosted organizations</option>
                      <option value="https://api.ca.aws.sigmacomputing.com">AWS Canada hosted organizations</option>
                      <option value="https://api.eu.aws.sigmacomputing.com">AWS Europe hosted organizations</option>
                      <option value="https://api.au.aws.sigmacomputing.com">AWS Australia hosted organizations</option>
                      <option value="https://api.uk.aws.sigmacomputing.com">AWS UK hosted organizations</option>
                      <option value="https://api.us.azure.sigmacomputing.com">Azure US hosted organizations</option>
                      <option value="https://api.eu.azure.sigmacomputing.com">Azure Europe hosted organizations</option>
                      <option value="https://api.ca.azure.sigmacomputing.com">Azure Canada hosted organizations</option>
                      <option value="https://api.uk.azure.sigmacomputing.com">Azure UK hosted organizations</option>
                    </select>
                  </div>

                  {/* API Credentials and Storage - Combined intelligently */}
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <h5 className="text-sm font-medium text-blue-900 mb-2">🔐 API Credentials</h5>
                    
                    <div className="grid grid-cols-2 gap-4 mb-3">
                      <div>
                        <label className="block text-xs font-medium text-blue-800 mb-1">
                          Client ID <span className="text-red-600">*</span>
                        </label>
                        <input
                          type="text"
                          value={envValues['CLIENT_ID'] || ''}
                          onChange={(e) => handleEnvChange('CLIENT_ID', e.target.value)}
                          placeholder="Enter Client ID"
                          className="w-full px-2 py-1 border border-blue-300 rounded text-sm font-mono focus:border-blue-500 focus:ring-1 focus:ring-blue-500 bg-white"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-blue-800 mb-1">
                          Client Secret <span className="text-red-600">*</span>
                        </label>
                        <input
                          type="password"
                          value={envValues['SECRET'] || ''}
                          onChange={(e) => handleEnvChange('SECRET', e.target.value)}
                          placeholder="Enter Client Secret"
                          className="w-full px-2 py-1 border border-blue-300 rounded text-sm font-mono focus:border-blue-500 focus:ring-1 focus:ring-blue-500 bg-white"
                        />
                      </div>
                    </div>

                    {/* Storage Options - Integrated into credentials section */}
                    <div className="border-t border-blue-200 pt-3">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center">
                          <input
                            type="checkbox"
                            id="storeKeysLocally"
                            checked={storeKeysLocally}
                            onChange={(e) => setStoreKeysLocally(e.target.checked)}
                            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                          />
                          <label htmlFor="storeKeysLocally" className="ml-2 text-sm font-medium text-blue-800">
                            Store locally (encrypted)
                          </label>
                        </div>
                        {currentFormIsStored && (
                          <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded-full">
                            ✓ Stored
                          </span>
                        )}
                      </div>

                      {storeKeysLocally && (
                        <div className="space-y-2">
                          {/* Save notification */}
                          {saveNotification && (
                            <div className="bg-green-100 border border-green-400 text-green-700 px-3 py-2 rounded text-xs animate-pulse">
                              {saveNotification}
                            </div>
                          )}
                          
                          <div className="grid grid-cols-3 gap-3 items-end max-w-lg">
                            <div className="col-span-2">
                              <label className="block text-xs font-medium text-blue-800 mb-1">
                                Config Name (optional):
                              </label>
                              <input
                                type="text"
                                value={credentialSetName}
                                onChange={(e) => {
                                  setCredentialSetName(e.target.value);
                                  setCurrentFormIsStored(false); // Mark as unsaved when name changes
                                  // Reset default checkbox when changing config name
                                  setSetAsDefault(false);
                                }}
                                placeholder="e.g., Production, Staging"
                                className="w-full px-2 py-1 border border-blue-300 rounded text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 bg-white"
                              />
                            </div>
                            
                            <div className="flex items-center space-x-2">
                              <input
                                type="checkbox"
                                id="setAsDefault"
                                checked={setAsDefault}
                                onChange={(e) => setSetAsDefault(e.target.checked)}
                                className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-blue-300 rounded"
                              />
                              <label htmlFor="setAsDefault" className="text-xs text-blue-700 select-none cursor-pointer">
                                Set as default config
                              </label>
                              {setAsDefault && (
                                <span className="text-xs text-blue-600">⭐</span>
                              )}
                            </div>
                            
                            <button
                              onClick={async () => {
                                // Save config immediately
                                if (envValues['CLIENT_ID'] && envValues['SECRET']) {
                                  try {
                                    const setName = credentialSetName.trim();
                                    if (!setName) {
                                      showSaveNotification('Please enter a config name before saving.');
                                      return;
                                    }
                                    await fetch('/api/keys', {
                                      method: 'POST',
                                      headers: { 'Content-Type': 'application/json' },
                                      body: JSON.stringify({
                                        clientId: envValues['CLIENT_ID'],
                                        clientSecret: envValues['SECRET'],
                                        baseURL: envValues['baseURL'],
                                        authURL: envValues['authURL'],
                                        name: setName,
                                        setAsDefault: setAsDefault
                                      })
                                    });
                                    setCurrentFormIsStored(true);
                                    setHasStoredKeys(true);
                                    
                                    // Update available sets
                                    const updatedResponse = await fetch('/api/keys?list=true');
                                    if (updatedResponse.ok) {
                                      const updatedData = await updatedResponse.json();
                                      setAvailableCredentialSets(updatedData.credentialSets || []);
                                      setDefaultCredentialSet(updatedData.defaultSet || null);
                                    }
                                    
                                    // Show success notification
                                    showSaveNotification(`Config "${setName}" saved successfully!`);
                                  } catch (error) {
                                    console.error('Failed to save config:', error);
                                    showSaveNotification('Failed to save config. Please try again.');
                                  }
                                }
                              }}
                              disabled={!envValues['CLIENT_ID'] || !envValues['SECRET']}
                              className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-500 transition-colors"
                            >
                              💾 Save
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Authentication Status */}
                  {(authToken || hasValidToken) && (
                    <div className="pt-3 border-t border-gray-200">
                      <div className="flex items-center">
                        <span className="text-green-600 text-lg mr-2">✅</span>
                        <span className="text-sm font-medium text-green-800">Currently Authenticated</span>
                      </div>
                    </div>
                  )}

                  {useEnvFile && (
                    <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                      <p className="text-sm text-amber-800">
                        📁 Environment file mode is enabled. Values above will be ignored in favor of the .env file.
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <SmartParameterForm
                  parameters={smartParameters}
                  values={envValues}
                  onChange={setEnvValues}
                  authToken={authToken}
                  baseURL={authBaseURL} // Pass baseURL to prevent race conditions
                  onRunScript={() => {
                    console.log('SmartParameterForm authToken:', authToken, 'baseURL:', authBaseURL);
                    // Switch to Response tab immediately so user can see progress
                    setActiveTab('run');
                    if (!executing) {
                      executeScript();
                    }
                  }}
                  executing={executing}
                  onShowReadme={() => setActiveTab('readme')}
                />
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

              {/* Parameter Summary */}
              {Object.keys(envValues).length > 0 && Object.values(envValues).some(v => v && v.trim()) && (
                <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <h4 className="text-sm font-semibold text-blue-800 mb-2">Request Parameters</h4>
                  <div className="space-y-1">
                    {smartParameters.map(param => {
                      const value = envValues[param.name];
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

              {/* Execution Results */}
              {executionResult && (
                <div className="border rounded-lg bg-gray-50">
                  {/* Header with Status and Response Code */}
                  <div className={`px-4 py-3 border-b ${
                    executionResult.success === true ? 'bg-green-50 border-green-200' :
                    executionResult.success === false ? 'bg-red-50 border-red-200' :
                    'bg-blue-50 border-blue-200'
                  }`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center">
                        <span className={`text-lg mr-2 ${
                          executionResult.success === true ? 'text-green-600' :
                          executionResult.success === false ? 'text-red-600' :
                          'text-blue-600'
                        }`}>
                          {executionResult.success === true ? '✅' : 
                           executionResult.success === false ? '❌' : 
                           '⏳'}
                        </span>
                        <span className={`font-semibold ${
                          executionResult.success === true ? 'text-green-800' :
                          executionResult.success === false ? 'text-red-800' :
                          'text-blue-800'
                        }`}>
                          {executionResult.success === true
                            ? `Success${executionResult.httpStatus ? ` (${executionResult.httpStatus})` : ''}`
                            : executionResult.success === false
                            ? `Error${executionResult.httpStatus ? ` (${executionResult.httpStatus})` : ''}`
                            : 'Processing...'
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
                            onClick={async () => {
                              await navigator.clipboard.writeText(executionResult.output);
                              setCopyButtonText('Copied!');
                              setTimeout(() => setCopyButtonText('Copy Output'), 2000);
                            }}
                            className="text-xs text-blue-600 hover:text-blue-800 underline"
                          >
                            {copyButtonText}
                          </button>
                        </div>
                        <div className="bg-white border p-3 rounded text-xs font-mono whitespace-pre-wrap overflow-auto max-h-96 border-gray-300">
                          {executionResult.output.split('\n').map((line, index) => (
                            <div key={index}>
                              {line.includes('📁 File saved! Click here to open downloads folder') ? (
                                <span>
                                  {line.split('📁 File saved! Click here to open downloads folder')[0]}
                                  <button
                                    onClick={openDownloadsFolder}
                                    className="text-blue-600 hover:text-blue-800 underline cursor-pointer"
                                  >
                                    📁 File saved! Click here to open downloads folder
                                  </button>
                                </span>
                              ) : (
                                line
                              )}
                            </div>
                          ))}
                        </div>
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
                        <pre className="bg-red-50 border border-red-200 p-3 rounded text-xs font-mono whitespace-pre-wrap overflow-auto max-h-96">
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