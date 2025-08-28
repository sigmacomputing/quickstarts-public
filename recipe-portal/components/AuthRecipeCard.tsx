'use client';

import { useState } from 'react';
import { Recipe } from '../lib/recipeScanner';
import { CodeViewer } from './CodeViewer';

interface AuthRecipeCardProps {
  recipe: Recipe;
  useEnvFile?: boolean;
  onTokenObtained?: () => void;
}

export function AuthRecipeCard({ recipe, useEnvFile = false, onTokenObtained }: AuthRecipeCardProps) {
  const [showCodeViewer, setShowCodeViewer] = useState(false);
  return (
    <div className="bg-gradient-to-r from-amber-50 to-orange-50 border-l-4 border-amber-500 rounded-lg shadow-md p-6 h-full">
      <div className="flex flex-col h-full">
        <div className="flex-1">
          <div className="flex items-center mb-3">
            <span className="text-2xl mr-3">🔐</span>
            <h3 className="text-xl font-semibold text-gray-800">
              Authentication Setup
            </h3>
            <span className="ml-3 bg-amber-100 text-amber-800 text-xs font-medium px-2.5 py-0.5 rounded-full">
              Required First
            </span>
          </div>
          
          <p className="text-gray-700 mb-4">
            Configure your API credentials and generate a bearer token for accessing Sigma&rsquo;s REST API. Tokens are cached for reuse across recipes during your session.
          </p>
          
          {recipe.envVariables.length > 0 && (
            <div className="mb-4">
              <p className="text-sm font-medium text-gray-700 mb-2">Required Environment Variables:</p>
              <div className="flex flex-wrap gap-2">
                {recipe.envVariables.map((envVar) => (
                  <span 
                    key={envVar}
                    className="bg-amber-100 text-amber-800 text-xs font-mono px-2 py-1 rounded"
                  >
                    {envVar}
                  </span>
                ))}
              </div>
            </div>
          )}
          
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
        </div>
        
        <div className="flex justify-between items-center mt-4 pt-4 border-t border-amber-200">
          <div className="text-xs text-gray-600">
            <span className="font-medium">Token Duration:</span> 1 hour (cached for session)
          </div>
          <button 
            className="bg-amber-600 text-white px-4 py-2 rounded-lg hover:bg-amber-700 transition-colors text-sm font-medium"
            onClick={() => setShowCodeViewer(true)}
          >
            View Recipe
          </button>
        </div>
      </div>
      
      <CodeViewer
        isOpen={showCodeViewer}
        onClose={() => setShowCodeViewer(false)}
        filePath={recipe.filePath}
        fileName="get-access-token.js"
        envVariables={useEnvFile ? recipe.envVariables : ['CLIENT_ID', 'SECRET', 'authURL', 'baseURL']}
        useEnvFile={useEnvFile}
        onTokenObtained={onTokenObtained}
      />
    </div>
  );
}