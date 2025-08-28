'use client';

import { useState, useEffect } from 'react';
import { detectSmartParameters, SmartParameter } from '../lib/smartParameters';
import { QuickApiModal } from './QuickApiModal';

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

interface QuickApiExplorerProps {
  hasValidToken: boolean;
  authToken?: string | null;
}

const QUICK_ENDPOINTS: QuickApiEndpoint[] = [
  // Zero parameter endpoints
  {
    id: 'list-accounttypes',
    name: 'Account Types',
    method: 'GET',
    path: '/account-types',
    description: 'Get a list of all account types',
    category: 'List All',
    parameters: [],
    example: 'View different account type configurations'
  },
  {
    id: 'list-connections',
    name: 'Connections',
    method: 'GET',
    path: '/connections',
    description: 'Get a list of all data connections',
    category: 'List All',
    parameters: [],
    example: 'See all configured data sources'
  },
  {
    id: 'list-datamodels',
    name: 'Data Models',
    method: 'GET',
    path: '/dataModels',
    description: 'Get a list of all data models',
    category: 'List All',
    parameters: [],
    example: 'See all available data models'
  },
  {
    id: 'list-members',
    name: 'Members',
    method: 'GET',
    path: '/members',
    description: 'Get a list of all members in your organization',
    category: 'List All',
    parameters: [],
    example: 'See all users and their details'
  },
  {
    id: 'list-teams',
    name: 'Teams',
    method: 'GET',
    path: '/teams',
    description: 'Get a list of all teams in your organization',
    category: 'List All',
    parameters: [],
    example: 'Perfect for seeing all available teams'
  },
  {
    id: 'list-templates',
    name: 'Templates',
    method: 'GET',
    path: '/templates',
    description: 'Get a list of available templates',
    category: 'List All',
    parameters: [],
    example: 'Browse reusable templates'
  },
  {
    id: 'list-workbooks',
    name: 'Workbooks',
    method: 'GET',
    path: '/workbooks',
    description: 'Get a list of all workbooks you have access to',
    category: 'List All',
    parameters: [],
    example: 'Browse all available workbooks'
  },
  {
    id: 'list-workspaces',
    name: 'Workspaces',
    method: 'GET',
    path: '/workspaces',
    description: 'Get a list of all workspaces',
    category: 'List All',
    parameters: [],
    example: 'View organizational structure'
  },
  // Single parameter endpoints
  {
    id: 'get-datamodel',
    name: 'Data Model Details',
    method: 'GET',
    path: '/dataModels/{dataModelId}',
    description: 'Get detailed information about a specific data model',
    category: 'Get Details',
    parameters: detectSmartParameters(['dataModelId']),
    example: 'Get data model structure and metadata'
  },
  {
    id: 'get-member',
    name: 'Member Details',
    method: 'GET',
    path: '/members/{memberId}',
    description: 'Get detailed information about a specific member',
    category: 'Get Details',
    parameters: detectSmartParameters(['memberId']),
    example: 'Get user profile and permissions'
  },
  {
    id: 'get-team',
    name: 'Team Details',
    method: 'GET',
    path: '/teams/{teamId}',
    description: 'Get detailed information about a specific team',
    category: 'Get Details',
    parameters: detectSmartParameters(['teamId']),
    example: 'Get team members and permissions'
  },
  {
    id: 'get-workbook',
    name: 'Workbook Details',
    method: 'GET',
    path: '/workbooks/{workbookId}',
    description: 'Get detailed information about a specific workbook',
    category: 'Get Details',
    parameters: detectSmartParameters(['workbookId']),
    example: 'Get workbook metadata and structure'
  },
  {
    id: 'get-workbook-pages',
    name: 'Workbook Pages',
    method: 'GET',
    path: '/workbooks/{workbookId}/pages',
    description: 'Get all pages in a workbook with their metadata',
    category: 'Get Details',
    parameters: detectSmartParameters(['workbookId']),
    example: 'See all pages and their structure in the workbook'
  }
];

export function QuickApiExplorer({ hasValidToken, authToken }: QuickApiExplorerProps) {
  const [activeCategory, setActiveCategory] = useState<'List All' | 'Get Details'>('List All');
  const [selectedEndpoint, setSelectedEndpoint] = useState<QuickApiEndpoint | null>(null);
  const [showModal, setShowModal] = useState(false);

  const categories = ['List All', 'Get Details'] as const;
  const filteredEndpoints = QUICK_ENDPOINTS.filter(endpoint => endpoint.category === activeCategory);

  const handleEndpointClick = (endpoint: QuickApiEndpoint) => {
    setSelectedEndpoint(endpoint);
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setSelectedEndpoint(null);
  };

  // Clear results when component mounts/unmounts
  useEffect(() => {
    return () => {
      setSelectedEndpoint(null);
    };
  }, []);

  return (
    <div className="p-6 bg-white min-h-screen">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Common GET Methods</h2>
          <p className="text-gray-600">
            Quickly test common Sigma API endpoints with minimal setup. Perfect for exploring your data and getting familiar with the API.
          </p>
        </div>

        {!hasValidToken && (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
            <div className="flex items-center">
              <span className="text-amber-600 mr-2">🔐</span>
              <div>
                <p className="text-amber-800 font-medium">Authentication Required</p>
                <p className="text-amber-700 text-sm">Please authenticate first to test these API endpoints.</p>
              </div>
            </div>
          </div>
        )}

        {/* Category Tabs */}
        <div className="mb-6">
          <div className="flex border-b border-gray-200">
            {categories.map((category) => (
              <button
                key={category}
                onClick={() => setActiveCategory(category)}
                className={`px-4 py-2 text-sm font-medium border-b-2 mr-4 ${
                  activeCategory === category
                    ? 'text-white border-blue-500 bg-blue-500'
                    : 'text-gray-700 border-transparent hover:text-gray-900 hover:border-gray-400 bg-gray-200'
                }`}
              >
                {category}
              </button>
            ))}
          </div>
        </div>

        {/* Endpoint Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredEndpoints.map((endpoint) => (
            <div
              key={endpoint.id}
              className="bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow p-6 border border-gray-300 cursor-pointer"
              onClick={() => handleEndpointClick(endpoint)}
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-4 gap-3">
                <div className="flex items-start flex-wrap gap-2 flex-1 min-w-0">
                  <div className="flex items-center">
                    <span className="text-xs font-medium px-2.5 py-0.5 rounded-full bg-green-100 text-green-800 mr-3">
                      {endpoint.method}
                    </span>
                    <h3 className="text-lg font-semibold text-gray-800 leading-tight">
                      {endpoint.name}
                    </h3>
                  </div>
                  {endpoint.parameters.length > 0 && (
                    <span className="text-xs font-medium px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-800 shrink-0">
                      {endpoint.parameters.length} param{endpoint.parameters.length !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>
                <button 
                  className="bg-blue-600 text-white px-3 py-1 rounded text-xs font-medium hover:bg-blue-700 transition-colors shrink-0"
                  onClick={() => handleEndpointClick(endpoint)}
                >
                  Test API
                </button>
              </div>
              
              {/* Description */}
              <p className="text-gray-600 text-sm mb-4 line-clamp-3">
                {endpoint.description}
              </p>
              
              {/* API Path */}
              <div className="mb-3">
                <p className="text-xs font-medium text-gray-700 mb-2">API Endpoint:</p>
                <code className="text-xs font-mono text-gray-700 bg-gray-100 px-2 py-1 rounded block">
                  {endpoint.method} {endpoint.path}
                </code>
              </div>
            </div>
          ))}
        </div>

        {/* Modal */}
        {selectedEndpoint && (
          <QuickApiModal
            isOpen={showModal}
            onClose={handleCloseModal}
            endpoint={selectedEndpoint}
            hasValidToken={hasValidToken}
            authToken={authToken}
          />
        )}
      </div>
    </div>
  );
}