'use client';

import { useState, useEffect } from 'react';
import { RecipeCard } from '../components/RecipeCard';
import { CodeViewer } from '../components/CodeViewer';

interface Recipe {
  id: string;
  name: string;
  description: string;
  category: string;
  filePath: string;
  envVariables: string[];
  isAuthRequired: boolean;
}

interface RecipeCategory {
  name: string;
  recipes: Recipe[];
}

interface RecipeData {
  categories: RecipeCategory[];
  authRecipe: Recipe | null;
  timestamp: string;
}

export default function Home() {
  const [recipeData, setRecipeData] = useState<RecipeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCategoryTab, setActiveCategoryTab] = useState<string>('');
  const [hasValidToken, setHasValidToken] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);

  useEffect(() => {
    async function fetchRecipes() {
      try {
        const response = await fetch('/api/recipes');
        if (!response.ok) {
          throw new Error('Failed to fetch recipes');
        }
        const data = await response.json();
        setRecipeData(data);
        // Set first category as active by default
        if (data.categories.length > 0) {
          setActiveCategoryTab(data.categories[0].name);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    }

    async function checkAuthStatus() {
      try {
        const response = await fetch('/api/token');
        if (response.ok) {
          const data = await response.json();
          if (data.hasValidToken) {
            setHasValidToken(true);
          }
        }
      } catch (error) {
        // Ignore errors - just means no token is cached
      }
    }

    fetchRecipes();
    checkAuthStatus();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading recipes...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 mb-4">Error loading recipes: {error}</p>
          <button 
            onClick={() => window.location.reload()} 
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Sort categories alphabetically
  const sortedCategories = recipeData?.categories.sort((a, b) => a.name.localeCompare(b.name)) || [];
  const activeCategory = sortedCategories.find(cat => cat.name === activeCategoryTab);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Header */}
        <header className="mb-6">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h1 className="text-3xl font-bold text-gray-900 mb-2">
                Sigma API Recipe Portal
              </h1>
              
              
              <p className="text-lg text-gray-600 whitespace-nowrap">
                Interactive collection of JavaScript samples demonstrating how to use the Sigma API for specific use cases.
              </p>
            </div>
            
            {/* Auth Button */}
            <div className="ml-4">
              <button
                onClick={() => setShowAuthModal(true)}
                className={`flex items-center px-4 py-2 rounded-lg border transition-colors ${
                  hasValidToken 
                    ? 'bg-green-50 border-green-200 text-green-700 hover:bg-green-100' 
                    : 'bg-red-50 border-red-200 text-red-700 hover:bg-red-100'
                }`}
              >
                <span className="text-sm font-medium">
                  🔐 Authentication {hasValidToken ? '✓' : '⚠️'}
                </span>
              </button>
            </div>
          </div>
        </header>

        {/* Main Content Container */}
        <div className="bg-gray-50 rounded-lg shadow-lg overflow-hidden border border-gray-200">
          {/* Category Tabs */}
          <div className="border-b border-gray-300 bg-gray-100">
            <nav className="flex flex-wrap px-6">
              {sortedCategories.map((category) => (
                <button
                  key={category.name}
                  onClick={() => setActiveCategoryTab(category.name)}
                  className={`px-4 py-3 text-sm font-medium border-b-2 mr-6 ${
                    activeCategoryTab === category.name
                      ? 'text-blue-600 border-blue-600 bg-white'
                      : 'text-gray-600 border-transparent hover:text-gray-800 hover:border-gray-400 bg-gray-100'
                  }`}
                >
                  {category.name} ({category.recipes.length})
                </button>
              ))}
            </nav>
          </div>

          {/* Category Content */}
          <div className="p-6 bg-white">
            {activeCategory && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {activeCategory.recipes.map((recipe) => (
                  <RecipeCard key={recipe.id} recipe={recipe} hasValidToken={hasValidToken} />
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 text-center text-gray-500 text-sm">
            <p>
              Last updated: {recipeData ? new Date(recipeData.timestamp).toLocaleString() : '—'}
            </p>
            <p className="mt-1">
              Recipes are automatically discovered from the sigma-api-recipes directory
            </p>
          </div>
        </div>

        {/* Authentication Modal */}
        {recipeData?.authRecipe && (
          <CodeViewer
            isOpen={showAuthModal}
            onClose={() => setShowAuthModal(false)}
            filePath={recipeData.authRecipe.filePath}
            fileName="get-access-token.js"
            envVariables={['CLIENT_ID', 'SECRET', 'authURL', 'baseURL']}
            useEnvFile={false}
            onTokenObtained={() => {
              setHasValidToken(true);
            }}
            defaultTab="readme"
          />
        )}
      </div>
    </div>
  );
}