'use client';

import { useState } from 'react';
import { Recipe } from '../lib/recipeScanner';
import { CodeViewer } from './CodeViewer';

interface RecipeCardProps {
  recipe: Recipe;
  hasValidToken?: boolean;
  authToken?: string | null;
  baseURL?: string;
}

function getStatusBadge(recipe: Recipe, hasValidToken: boolean) {
  const badges = [];
  
  // Check if this is a download recipe
  const downloadRecipes = ['export-workbook-element-csv.js', 'export-workbook-pdf.js'];
  const isDownloadRecipe = downloadRecipes.some(downloadFileName => 
    recipe.filePath.endsWith(downloadFileName)
  );
  
  if (isDownloadRecipe) {
    badges.push({
      text: '⬇️ Download',
      className: 'bg-blue-100 text-blue-800'
    });
  }
  
  // Only show "Ready to Run" if recipe has no variables AND (doesn't need auth OR has valid token)
  if (recipe.envVariables.length === 0 && (!recipe.isAuthRequired || hasValidToken)) {
    badges.push({
      text: 'Ready to Run',
      className: 'bg-green-100 text-green-800'
    });
  }
  
  return badges.length > 0 ? badges : null;
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

export function RecipeCard({ recipe, hasValidToken = false, authToken, baseURL }: RecipeCardProps) {
  const [showCodeViewer, setShowCodeViewer] = useState(false);
  const badges = getStatusBadge(recipe, hasValidToken);
  const icon = getCategoryIcon(recipe.category);
  
  return (
    <div className="bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow p-6 border border-gray-300">
      {/* Header */}
      <div className="flex items-start justify-between mb-4 gap-3">
        <div className="flex items-start flex-wrap gap-2 flex-1 min-w-0">
          <div className="flex items-center">
            <span className="text-xl mr-3">{icon}</span>
            <h3 className="text-lg font-semibold text-gray-800 leading-tight">
              {recipe.name}
            </h3>
          </div>
          {badges && badges.map((badge, index) => (
            <span key={index} className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${badge.className} shrink-0`}>
              {badge.text}
            </span>
          ))}
        </div>
        <button 
          className="bg-blue-600 text-white px-3 py-1 rounded text-xs font-medium hover:bg-blue-700 transition-colors shrink-0"
          onClick={() => setShowCodeViewer(true)}
        >
          View Recipe
        </button>
      </div>
      
      {/* Description */}
      <p className="text-gray-600 text-sm mb-4 line-clamp-3">
        {recipe.description}
      </p>
      
      {/* Environment Variables */}
      {recipe.envVariables.length > 0 && (
        <div className="mb-3">
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
      
      
      <CodeViewer
        isOpen={showCodeViewer}
        onClose={() => setShowCodeViewer(false)}
        filePath={recipe.filePath}
        fileName={recipe.filePath.split('/').pop() || 'recipe.js'}
        envVariables={recipe.envVariables}
        useEnvFile={false}
        defaultTab="run"
        readmePath={recipe.readmePath}
        authToken={authToken}
        baseURL={baseURL}
      />
    </div>
  );
}