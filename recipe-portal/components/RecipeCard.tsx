'use client';

import { useState } from 'react';
import { Recipe } from '../lib/recipeScanner';
import { CodeViewer } from './CodeViewer';

interface RecipeCardProps {
  recipe: Recipe;
  hasValidToken?: boolean;
}

function getStatusBadge(recipe: Recipe, hasValidToken: boolean) {
  // Only show "Ready to Run" if recipe has no variables AND (doesn't need auth OR has valid token)
  if (recipe.envVariables.length === 0 && (!recipe.isAuthRequired || hasValidToken)) {
    return {
      text: 'Ready to Run',
      className: 'bg-green-100 text-green-800'
    };
  }
  
  return null; // No badge otherwise
}

function getCategoryIcon(category: string) {
  const icons: Record<string, string> = {
    'connections': '🔗',
    'members': '👥', 
    'teams': '👫',
    'workbooks': '📊',
    'embedding': '🔧',
    'authentication': '🔐'
  };
  
  return icons[category.toLowerCase()] || '📄';
}

export function RecipeCard({ recipe, hasValidToken = false }: RecipeCardProps) {
  const [showCodeViewer, setShowCodeViewer] = useState(false);
  const status = getStatusBadge(recipe, hasValidToken);
  const icon = getCategoryIcon(recipe.category);
  
  return (
    <div className="bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow p-6 border border-gray-300">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center">
          <span className="text-xl mr-3">{icon}</span>
          <h3 className="text-lg font-semibold text-gray-800 leading-tight">
            {recipe.name}
          </h3>
        </div>
        {status && (
          <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${status.className} shrink-0 ml-2`}>
            {status.text}
          </span>
        )}
      </div>
      
      {/* Description */}
      <p className="text-gray-600 text-sm mb-4 line-clamp-3">
        {recipe.description}
      </p>
      
      {/* Environment Variables */}
      {recipe.envVariables.length > 0 && (
        <div className="mb-4">
          <p className="text-xs font-medium text-gray-700 mb-2">Required Variables:</p>
          <div className="flex flex-wrap gap-1">
            {recipe.envVariables.slice(0, 3).map((envVar) => (
              <span 
                key={envVar}
                className="bg-gray-100 text-gray-700 text-xs font-mono px-2 py-1 rounded"
              >
                {envVar}
              </span>
            ))}
            {recipe.envVariables.length > 3 && (
              <span className="bg-gray-100 text-gray-500 text-xs px-2 py-1 rounded">
                +{recipe.envVariables.length - 3} more
              </span>
            )}
          </div>
        </div>
      )}
      
      {/* Actions */}
      <div className="flex items-center justify-end pt-4 border-t border-gray-100">
        <div className="flex space-x-2">
          <button 
            className="bg-blue-600 text-white px-3 py-1 rounded text-xs font-medium hover:bg-blue-700 transition-colors"
            onClick={() => setShowCodeViewer(true)}
          >
            View Recipe
          </button>
        </div>
      </div>
      
      {/* Recipe-specific Instructions */}
      {recipe.category !== 'authentication' && recipe.readmePath && (
        <div className="mt-3 pt-3 border-t border-gray-100">
          <a 
            href={`/api/readme?path=${encodeURIComponent(recipe.readmePath)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800 text-xs underline"
          >
            Instructions →
          </a>
        </div>
      )}
      
      <CodeViewer
        isOpen={showCodeViewer}
        onClose={() => setShowCodeViewer(false)}
        filePath={recipe.filePath}
        fileName={recipe.filePath.split('/').pop() || 'recipe.js'}
        envVariables={recipe.envVariables}
        useEnvFile={false}
        defaultTab="run"
      />
    </div>
  );
}