export interface SmartParameter {
  name: string;
  type: 'teamId' | 'memberId' | 'workbookId' | 'workspaceId' | 'connectionId' | 'elementId' | 'email' | 'string' | 'number' | 'select' | 'json' | 'boolean' | 'bookmarkId' | 'templateId' | 'datasetId' | 'dataModelId' | 'accountTypeId' | 'date';
  required: boolean;
  friendlyName: string;
  description: string;
  resourceType?: 'teams' | 'members' | 'workbooks' | 'workspaces' | 'connections' | 'bookmarks' | 'templates' | 'datasets' | 'dataModels' | 'accountTypes' | 'workbookElements' | 'materializationSchedules';
  placeholder?: string;
  options?: Array<{label: string; value: string}>;
  dependsOn?: string;
  validation?: {
    pattern?: string;
    minLength?: number;
    maxLength?: number;
  };
}

// Parameter detection patterns
const PARAMETER_PATTERNS: Record<string, Partial<SmartParameter>> = {
  'TEAMID': {
    type: 'teamId',
    resourceType: 'teams',
    friendlyName: 'Team',
    description: 'Select the team to work with'
  },
  'MEMBERID': {
    type: 'memberId', 
    resourceType: 'members',
    friendlyName: 'Member',
    description: 'Select the member to work with'
  },
  'WORKBOOK_ID': {
    type: 'workbookId',
    resourceType: 'workbooks', 
    friendlyName: 'Workbook',
    description: 'Select the workbook to work with'
  },
  'WORKSPACEID': {
    type: 'workspaceId',
    resourceType: 'workspaces',
    friendlyName: 'Workspace', 
    description: 'Select the workspace to work with'
  },
  'CONNECTIONID': {
    type: 'connectionId',
    resourceType: 'connections',
    friendlyName: 'Connection',
    description: 'Select the connection to work with'
  },
  'BOOKMARKID': {
    type: 'bookmarkId',
    resourceType: 'bookmarks',
    friendlyName: 'Favorite/Bookmark',
    description: 'Select the favorite or bookmark to work with'
  },
  'BOOKMARK_ID': {
    type: 'bookmarkId',
    resourceType: 'bookmarks',
    friendlyName: 'Favorite/Bookmark',
    description: 'Select the favorite or bookmark to work with'
  },
  'FAVORITEID': {
    type: 'bookmarkId',
    resourceType: 'bookmarks',
    friendlyName: 'Favorite/Bookmark',
    description: 'Select the favorite or bookmark to work with'
  },
  'FAVORITE_ID': {
    type: 'bookmarkId',
    resourceType: 'bookmarks',
    friendlyName: 'Favorite/Bookmark',
    description: 'Select the favorite or bookmark to work with'
  },
  'TEMPLATEID': {
    type: 'templateId',
    resourceType: 'templates',
    friendlyName: 'Template',
    description: 'Select the template to work with'
  },
  'TEMPLATE_ID': {
    type: 'templateId',
    resourceType: 'templates',
    friendlyName: 'Template',
    description: 'Select the template to work with'
  },
  'DATASETID': {
    type: 'datasetId',
    resourceType: 'datasets',
    friendlyName: 'Dataset',
    description: 'Select the dataset to work with'
  },
  'DATASET_ID': {
    type: 'datasetId',
    resourceType: 'datasets',
    friendlyName: 'Dataset',
    description: 'Select the dataset to work with'
  },
  'DATAMODELID': {
    type: 'dataModelId',
    resourceType: 'dataModels',
    friendlyName: 'Data Model',
    description: 'Select the data model to work with'
  },
  'DATAMODEL_ID': {
    type: 'dataModelId',
    resourceType: 'dataModels',
    friendlyName: 'Data Model',
    description: 'Select the data model to work with'
  },
  'DATA_MODEL_ID': {
    type: 'dataModelId',
    resourceType: 'dataModels',
    friendlyName: 'Data Model',
    description: 'Select the data model to work with'
  },
  'ACCOUNTTYPEID': {
    type: 'accountTypeId',
    resourceType: 'accountTypes',
    friendlyName: 'Account Type',
    description: 'Select the account type to work with'
  },
  'ACCOUNTTYPE_ID': {
    type: 'accountTypeId',
    resourceType: 'accountTypes',
    friendlyName: 'Account Type',
    description: 'Select the account type to work with'
  },
  'ACCOUNT_TYPE_ID': {
    type: 'accountTypeId',
    resourceType: 'accountTypes',
    friendlyName: 'Account Type',
    description: 'Select the account type to work with'
  },
  'ELEMENT_ID': {
    type: 'select',
    resourceType: 'workbookElements',
    friendlyName: 'Workbook Element',
    description: 'Select the workbook element to export',
    placeholder: 'Select element...',
    dependsOn: 'WORKBOOK_ID'
  },
  'SHEET_ID': {
    type: 'select',
    resourceType: 'materializationSchedules',
    friendlyName: 'Schedule Name',
    description: 'Select the materialization schedule to run',
    placeholder: 'Select schedule...',
    dependsOn: 'WORKBOOK_ID'
  },
  'EMAIL': {
    type: 'email',
    friendlyName: 'Email Address',
    description: 'Enter a valid email address',
    placeholder: 'user@example.com',
    validation: {
      pattern: '^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$'
    }
  },
  'NEW_MEMBER_FIRST_NAME': {
    type: 'string',
    friendlyName: 'First Name',
    description: 'Enter the member\'s first name',
    placeholder: 'John'
  },
  'NEW_MEMBER_LAST_NAME': {
    type: 'string', 
    friendlyName: 'Last Name',
    description: 'Enter the member\'s last name',
    placeholder: 'Smith'
  },
  'NEW_MEMBER_TYPE': {
    type: 'select',
    resourceType: 'accountTypes',
    friendlyName: 'Member Type',
    description: 'Select the member account type (fallback: admin, creator, viewer if API unavailable)',
    placeholder: 'Select account type...',
    options: [
      { label: 'Admin', value: 'admin' },
      { label: 'Creator', value: 'creator' },
      { label: 'Viewer', value: 'viewer' }
    ]
  },
  'SYNC_PATH': {
    type: 'json',
    friendlyName: 'Sync Path',
    description: 'JSON array representing the database path to sync (e.g., ["database", "schema"] for schema-level sync)',
    placeholder: '["SAMPLE_DATABASE", "PUBLIC"]'
  },
  'USER_NAME_PATTERN': {
    type: 'string',
    friendlyName: 'Username Pattern',
    description: 'Pattern for generating usernames',
    placeholder: 'user_{index}'
  },
  'DRY_RUN': {
    type: 'boolean',
    friendlyName: 'Dry Run',
    description: 'Preview mode - shows what would be deactivated without making actual changes',
    placeholder: 'true or false'
  },
  'LIMIT': {
    type: 'number',
    friendlyName: 'Row Limit',
    description: 'Maximum rows to export (Default: 100,000 | Max: 1,000,000) - Large downloads may timeout without batching',
    placeholder: '100000',
    validation: {
      min: 1,
      max: 1000000
    }
  },
  'PERMISSION': {
    type: 'select',
    friendlyName: 'Permission Level',
    description: 'Select the permission level to grant',
    placeholder: 'Select permission...',
    options: [
      { label: 'View', value: 'view' },
      { label: 'Explore', value: 'explore' },
      { label: 'Contribute', value: 'contribute' },
      { label: 'Manage', value: 'manage' }
    ]
  },
  'WORKSPACE_PERMISSION': {
    type: 'select',
    friendlyName: 'Workspace Permission Level',
    description: 'Select the workspace permission level to grant',
    placeholder: 'Select permission...',
    options: [
      { label: 'View', value: 'view' },
      { label: 'Explore', value: 'explore' },
      { label: 'Organize', value: 'organize' },
      { label: 'Edit', value: 'edit' }
    ]
  },
  'WORKSPACE_NAME': {
    type: 'string',
    friendlyName: 'Workspace Name',
    description: 'Enter the name for the new workspace',
    placeholder: 'My Workspace'
  },
  'NO_DUPLICATES': {
    type: 'boolean',
    friendlyName: 'Prevent Duplicates',
    description: 'Prevent creating duplicate workspace names',
    placeholder: 'true or false'
  },
  'NEW_WORKBOOK_NAME': {
    type: 'string',
    friendlyName: 'New Workbook Name',
    description: 'Enter the name for the copied workbook',
    placeholder: 'My Copied Workbook'
  },
  'NEW_WORKBOOK_DESCRIPTION': {
    type: 'string',
    friendlyName: 'New Workbook Description',
    description: 'Enter a description for the copied workbook',
    placeholder: 'Copy of the original workbook'
  },
  'START_DATE': {
    type: 'date',
    friendlyName: 'Start Date',
    description: 'Select start date for export range',
    placeholder: '2024-01-01'
  },
  'END_DATE': {
    type: 'date',
    friendlyName: 'End Date',
    description: 'Select end date for export range',
    placeholder: '2024-12-31'
  },
  'EXPORT_FILENAME': {
    type: 'string',
    friendlyName: 'Export Filename',
    description: 'Enter filename for exported CSV file',
    placeholder: 'my-export.csv'
  },
  'MAX_PAGES': {
    type: 'number',
    friendlyName: 'Max Pages',
    description: 'Maximum number of pages to fetch (0 = all pages)',
    placeholder: '5'
  },
};

// Fuzzy matching for parameter names
function fuzzyMatch(paramName: string, context?: { filePath?: string }): Partial<SmartParameter> | null {
  const upperParam = paramName.toUpperCase();
  
  // Direct match
  if (PARAMETER_PATTERNS[upperParam]) {
    return PARAMETER_PATTERNS[upperParam];
  }
  
  // OpenAPI parameter pattern matching
  if (upperParam === 'TEAMID' || upperParam === 'TEAM_ID' || upperParam.includes('TEAMID')) {
    return PARAMETER_PATTERNS['TEAMID'];
  }
  if (upperParam === 'MEMBERID' || upperParam === 'MEMBER_ID' || upperParam.includes('MEMBERID')) {
    // Don't return MEMBERID pattern for master-script.js since it's set programmatically
    if (context?.filePath?.includes('master-script')) {
      return null;
    }
    return PARAMETER_PATTERNS['MEMBERID'];
  }
  if (upperParam === 'WORKBOOKID' || upperParam === 'WORKBOOK_ID' || upperParam.includes('WORKBOOKID')) {
    return PARAMETER_PATTERNS['WORKBOOK_ID'];
  }
  if (upperParam === 'WORKSPACEID' || upperParam === 'WORKSPACE_ID' || upperParam.includes('WORKSPACEID')) {
    // Don't return WORKSPACEID pattern for master-script.js since it's set programmatically
    if (context?.filePath?.includes('master-script')) {
      return null;
    }
    return PARAMETER_PATTERNS['WORKSPACEID'];
  }
  if (upperParam === 'CONNECTIONID' || upperParam === 'CONNECTION_ID' || upperParam.includes('CONNECTIONID')) {
    return PARAMETER_PATTERNS['CONNECTIONID'];
  }
  if (upperParam === 'BOOKMARKID' || upperParam === 'BOOKMARK_ID' || upperParam.includes('BOOKMARKID')) {
    return PARAMETER_PATTERNS['BOOKMARKID'];
  }
  if (upperParam === 'FAVORITEID' || upperParam === 'FAVORITE_ID' || upperParam.includes('FAVORITEID')) {
    return PARAMETER_PATTERNS['FAVORITEID'];
  }
  if (upperParam === 'TEMPLATEID' || upperParam === 'TEMPLATE_ID' || upperParam.includes('TEMPLATEID')) {
    return PARAMETER_PATTERNS['TEMPLATEID'];
  }
  if (upperParam === 'DATASETID' || upperParam === 'DATASET_ID' || upperParam.includes('DATASETID')) {
    return PARAMETER_PATTERNS['DATASETID'];
  }
  
  // Fuzzy matching for broader patterns
  if (upperParam.includes('TEAM')) {
    return PARAMETER_PATTERNS['TEAMID'];
  }
  if (upperParam.includes('MEMBER')) {
    return PARAMETER_PATTERNS['MEMBERID'];
  }
  if (upperParam.includes('WORKBOOK')) {
    return PARAMETER_PATTERNS['WORKBOOK_ID'];
  }
  if (upperParam.includes('WORKSPACE')) {
    return PARAMETER_PATTERNS['WORKSPACEID'];
  }
  if (upperParam.includes('CONNECTION')) {
    return PARAMETER_PATTERNS['CONNECTIONID'];
  }
  if (upperParam.includes('BOOKMARK')) {
    return PARAMETER_PATTERNS['BOOKMARKID'];
  }
  if (upperParam.includes('FAVORITE')) {
    return PARAMETER_PATTERNS['FAVORITEID'];
  }
  if (upperParam.includes('TEMPLATE')) {
    return PARAMETER_PATTERNS['TEMPLATEID'];
  }
  if (upperParam.includes('DATASET')) {
    return PARAMETER_PATTERNS['DATASETID'];
  }
  if (upperParam.includes('EMAIL')) {
    return PARAMETER_PATTERNS['EMAIL'];
  }
  if (upperParam.includes('ELEMENT')) {
    return PARAMETER_PATTERNS['ELEMENT_ID'];
  }
  if (upperParam.includes('SHEET')) {
    return PARAMETER_PATTERNS['SHEET_ID'];
  }
  if (upperParam.includes('SYNC') && upperParam.includes('PATH')) {
    return PARAMETER_PATTERNS['SYNC_PATH'];
  }
  if (upperParam.includes('USER') && upperParam.includes('PATTERN')) {
    return PARAMETER_PATTERNS['USER_NAME_PATTERN'];
  }
  if (upperParam.includes('DRY') && upperParam.includes('RUN')) {
    return PARAMETER_PATTERNS['DRY_RUN'];
  }
  if (upperParam.includes('LIMIT')) {
    return PARAMETER_PATTERNS['LIMIT'];
  }
  if (upperParam.includes('WORKSPACE') && upperParam.includes('PERMISSION')) {
    return PARAMETER_PATTERNS['WORKSPACE_PERMISSION'];
  }
  if (upperParam.includes('PERMISSION')) {
    return PARAMETER_PATTERNS['PERMISSION'];
  }
  if (upperParam.includes('WORKSPACE') && upperParam.includes('NAME')) {
    return PARAMETER_PATTERNS['WORKSPACE_NAME'];
  }
  if (upperParam.includes('NO') && upperParam.includes('DUPLICATE')) {
    return PARAMETER_PATTERNS['NO_DUPLICATES'];
  }
  if (upperParam.includes('NEW') && upperParam.includes('WORKBOOK') && upperParam.includes('NAME')) {
    return PARAMETER_PATTERNS['NEW_WORKBOOK_NAME'];
  }
  if (upperParam.includes('NEW') && upperParam.includes('WORKBOOK') && upperParam.includes('DESCRIPTION')) {
    return PARAMETER_PATTERNS['NEW_WORKBOOK_DESCRIPTION'];
  }
  if (upperParam.includes('START') && upperParam.includes('DATE')) {
    return PARAMETER_PATTERNS['START_DATE'];
  }
  if (upperParam.includes('END') && upperParam.includes('DATE')) {
    return PARAMETER_PATTERNS['END_DATE'];
  }
  if (upperParam.includes('EXPORT') && upperParam.includes('FILENAME')) {
    return PARAMETER_PATTERNS['EXPORT_FILENAME'];
  }
  if (upperParam.includes('MAX') && upperParam.includes('PAGE')) {
    return PARAMETER_PATTERNS['MAX_PAGES'];
  }
  if (upperParam.includes('FIRST') && upperParam.includes('NAME')) {
    return PARAMETER_PATTERNS['NEW_MEMBER_FIRST_NAME'];
  }
  if (upperParam.includes('LAST') && upperParam.includes('NAME')) {
    return PARAMETER_PATTERNS['NEW_MEMBER_LAST_NAME'];
  }
  if (upperParam.includes('TYPE')) {
    return PARAMETER_PATTERNS['NEW_MEMBER_TYPE'];
  }
  
  return null;
}

export function detectSmartParameters(envVariables: string[], context?: { filePath?: string }): SmartParameter[] {
  // Filter out MEMBERID and WORKSPACEID for master-script.js since they're set programmatically
  let filteredEnvVariables = envVariables;
  if (context?.filePath?.includes('master-script')) {
    filteredEnvVariables = envVariables.filter(param => 
      param !== 'MEMBERID' && param !== 'WORKSPACEID'
    );
  }
  
  return filteredEnvVariables.map(paramName => {
    let detected = fuzzyMatch(paramName, context);
    
    // Special handling for PERMISSION parameter based on context
    if (paramName === 'PERMISSION' && context?.filePath?.includes('workspace')) {
      detected = PARAMETER_PATTERNS['WORKSPACE_PERMISSION'];
    }
    
    if (detected) {
      return {
        name: paramName,
        required: true,
        friendlyName: detected.friendlyName || paramName,
        description: detected.description || `Enter ${paramName}`,
        ...detected
      } as SmartParameter;
    }
    
    // Default fallback for unknown parameters
    return {
      name: paramName,
      type: 'string' as const,
      required: true,
      friendlyName: paramName.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase()),
      description: `Enter ${paramName}`,
      placeholder: `Enter ${paramName.toLowerCase()}...`
    };
  });
}

// Get parameter suggestions based on code analysis
export function analyzeRecipeCode(code: string, context?: { filePath?: string }): { suggestedParameters: string[] } {
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
  
  let filteredParameters = Array.from(parameters);
  
  // Filter out MEMBERID and WORKSPACEID for master-script.js since they're set programmatically
  if (context?.filePath?.includes('master-script')) {
    filteredParameters = filteredParameters.filter(param => 
      param !== 'MEMBERID' && param !== 'WORKSPACEID'
    );
  }
  
  return {
    suggestedParameters: filteredParameters
  };
}