'use client';

import { useState, useEffect, useCallback } from 'react';
import { RecipeCard } from '../components/RecipeCard';
import { CodeViewer } from '../components/CodeViewer';
import { QuickApiExplorer } from '../components/QuickApiExplorer';

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
  const [activeTopTab, setActiveTopTab] = useState<'recipes' | 'quickapi'>('recipes');
  const [activeCategoryTab, setActiveCategoryTab] = useState<string>('');
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [authBaseURL, setAuthBaseURL] = useState<string>('https://aws-api.sigmacomputing.com/v2'); // Store baseURL from auth config
  const [hasValidToken, setHasValidToken] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [clearingToken, setClearingToken] = useState(false);
  const [quickApiKey, setQuickApiKey] = useState(0);

  // Function to check auth status (reusable)
  const checkAuthStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/token');
      if (response.ok) {
        const data = await response.json();
        if (data.hasValidToken) {
          setHasValidToken(true);
          setAuthToken(data.token);
          if (data.baseURL) {
            setAuthBaseURL(data.baseURL); // Store baseURL to prevent race conditions
          }
        } else {
          setHasValidToken(false);
          setAuthToken(null);
        }
      } else {
        setHasValidToken(false);
        setAuthToken(null);
      }
    } catch (error) {
      setHasValidToken(false);
      setAuthToken(null);
    }
  }, []);

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

    fetchRecipes();
    checkAuthStatus();
  }, [checkAuthStatus]);

  // Periodically check auth status every 30 seconds
  useEffect(() => {
    const interval = setInterval(checkAuthStatus, 30000);
    return () => clearInterval(interval);
  }, [checkAuthStatus]);

  const clearToken = async () => {
    setClearingToken(true);
    try {
      const response = await fetch('/api/token/clear', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ clearAll: true })
      });
      
      if (response.ok) {
        setHasValidToken(false);
        setAuthToken(null);
        // If auth modal is open, close it to trigger form reset on next open
        if (showAuthModal) {
          setShowAuthModal(false);
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
              <div className="flex items-center mb-2">
                <img src="/crane.png" alt="Sigma Logo" className="h-10 mr-3" />
                <h1 className="text-3xl font-bold text-gray-900">
            QuickStarts API Toolkit
                </h1>
              </div>
              
              
              <p className="text-lg text-gray-600">
                Experiment with Sigma API calls and learn common request flows
              </p>
            </div>
            
            {/* Action Buttons */}
            <div className="flex gap-3 flex-shrink-0">
              <button
                onClick={() => window.open(`/api/readme?path=${encodeURIComponent('README.md')}`, '_blank')}
                className="flex items-center px-4 py-2 rounded-lg border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors"
              >
                <span className="text-sm font-medium">
                  Documentation
                </span>
              </button>
              
              {hasValidToken ? (
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowAuthModal(true)}
                    className="flex items-center px-4 py-2 rounded-lg border border-green-200 bg-green-50 text-green-700 hover:bg-green-100 transition-colors"
                  >
                    <span className="text-green-600 mr-2">✓</span>
                    <span className="text-sm font-medium">
                      Authenticated
                    </span>
                  </button>
                  <button
                    onClick={clearToken}
                    disabled={clearingToken}
                    className="flex items-center px-3 py-2 rounded-lg border border-gray-300 bg-gray-50 text-gray-700 hover:bg-gray-100 transition-colors disabled:opacity-50"
                  >
                    <span className="text-sm font-medium whitespace-nowrap">
                      {clearingToken ? 'Ending...' : 'End Session'}
                    </span>
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowAuthModal(true)}
                  className="flex items-center px-4 py-2 rounded-lg border border-red-200 bg-red-50 text-red-700 hover:bg-red-100 transition-colors"
                >
                  <span className="text-sm font-medium">
                    Authentication Required
                  </span>
                </button>
              )}
            </div>
          </div>
        </header>

        {/* Main Content Container */}
        <div className="bg-gray-50 rounded-lg shadow-lg overflow-hidden border border-gray-200">
          {/* Top Level Tabs */}
          <div className="border-b border-gray-300 bg-white">
            <nav className="flex">
              <button
                onClick={() => setActiveTopTab('recipes')}
                className={`px-6 py-4 text-sm font-medium border-b-2 ${
                  activeTopTab === 'recipes'
                    ? 'text-white border-blue-600 bg-blue-600'
                    : 'text-gray-600 border-transparent hover:text-gray-800 hover:border-gray-300 bg-gray-100'
                }`}
              >
                Recipes
              </button>
              <button
                onClick={() => {
                  setActiveTopTab('quickapi');
                  // Reset Quick API component to clear any previous results
                  setQuickApiKey(prev => prev + 1);
                }}
                className={`px-6 py-4 text-sm font-medium border-b-2 ${
                  activeTopTab === 'quickapi'
                    ? 'text-white border-blue-600 bg-blue-600'
                    : 'text-gray-600 border-transparent hover:text-gray-800 hover:border-gray-300 bg-gray-100'
                }`}
              >
                Quick API
              </button>
            </nav>
          </div>

          {/* Tab Content */}
          {activeTopTab === 'recipes' ? (
            <>
              {/* Category Tabs */}
              <div className="border-b border-gray-300 bg-gray-100">
                <nav className="flex flex-wrap px-6">
                  {sortedCategories.map((category) => (
                    <button
                      key={category.name}
                      onClick={() => setActiveCategoryTab(category.name)}
                      className={`px-4 py-3 text-sm font-medium border-b-2 mr-6 ${
                        activeCategoryTab === category.name
                          ? 'text-white border-blue-500 bg-blue-500'
                          : 'text-gray-700 border-transparent hover:text-gray-900 hover:border-gray-400 bg-gray-200'
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
                      <RecipeCard 
                        key={recipe.id} 
                        recipe={recipe} 
                        hasValidToken={hasValidToken}
                        authToken={authToken}
                        baseURL={authBaseURL}
                      />
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <QuickApiExplorer key={quickApiKey} hasValidToken={hasValidToken} authToken={authToken} baseURL={authBaseURL} />
          )}

          {/* Footer */}
          <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex justify-between items-center text-gray-500 text-sm">
            <p>© Sigma 2025</p>
            <p>Last updated: {recipeData ? new Date(recipeData.timestamp).toLocaleDateString() : '—'}</p>
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
              // Refresh auth status to get the token and baseURL
              setTimeout(async () => {
                try {
                  const response = await fetch('/api/token');
                  if (response.ok) {
                    const data = await response.json();
                    if (data.hasValidToken) {
                      setAuthToken(data.token);
                      if (data.baseURL) {
                        setAuthBaseURL(data.baseURL); // Update baseURL to prevent race conditions
                      }
                    }
                  }
                } catch (error) {
                  // Ignore errors
                }
              }, 1000);
            }}
            onTokenCleared={() => {
              setHasValidToken(false);
              setAuthToken(null);
            }}
            defaultTab="readme"
            hasValidToken={hasValidToken}
          />
        )}
      </div>
    </div>
  );
}
