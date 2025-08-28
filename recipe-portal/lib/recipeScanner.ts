import fs from 'fs';
import path from 'path';

export interface Recipe {
  id: string;
  name: string;
  description: string;
  category: string;
  filePath: string;
  envVariables: string[];
  isAuthRequired: boolean;
  readmePath?: string;
}

export interface RecipeCategory {
  name: string;
  recipes: Recipe[];
}

const RECIPES_PATH = path.join(process.cwd(), '..', 'sigma-api-recipes');

/**
 * Extract environment variables from a JavaScript file (excluding core auth variables)
 */
function extractEnvVariables(fileContent: string): string[] {
  const envRegex = /process\.env\.([A-Z_][A-Z0-9_]*)/g;
  const matches = Array.from(fileContent.matchAll(envRegex));
  const envVars = matches.map(match => match[1]);
  
  // Core auth variables that are handled centrally
  const coreAuthVars = new Set(['CLIENT_ID', 'SECRET', 'authURL', 'baseURL']);
  
  // Filter out core auth variables since they're handled by the centralized auth system
  const recipeSpecificVars = envVars.filter(envVar => !coreAuthVars.has(envVar));
  
  return Array.from(new Set(recipeSpecificVars)); // Remove duplicates
}

/**
 * Extract title and description from structured comments
 */
function extractDescription(fileContent: string): string {
  const lines = fileContent.split('\n');
  let description = '';
  
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('// Description:')) {
      description = trimmed.substring(15).trim(); // Remove "// Description:" prefix
      break;
    }
  }
  
  return description || 'No description available';
}

/**
 * Extract title from structured comments
 */
function extractTitle(fileContent: string): string {
  const lines = fileContent.split('\n');
  
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('// Title:')) {
      return trimmed.substring(9).trim(); // Remove "// Title:" prefix
    }
  }
  
  return ''; // Return empty string if no title found
}

/**
 * Generate a human-readable name from filename
 */
function generateRecipeName(filename: string): string {
  return filename
    .replace('.js', '')
    .replace(/-/g, ' ')
    .replace(/_/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Check if recipe requires authentication (references get-access-token)
 */
function requiresAuth(fileContent: string): boolean {
  return fileContent.includes('get-access-token') || fileContent.includes('getBearerToken');
}

/**
 * Scan a single recipe file and extract metadata
 */
function scanRecipeFile(filePath: string, category: string): Recipe | null {
  try {
    const fileContent = fs.readFileSync(filePath, 'utf-8');
    const filename = path.basename(filePath);
    
    // Skip if not a JavaScript file
    if (!filename.endsWith('.js')) {
      return null;
    }
    
    // Check for corresponding README file
    const baseFilename = filename.replace('.js', '');
    const readmePath = path.join(path.dirname(filePath), `${baseFilename}.md`);
    const hasReadme = fs.existsSync(readmePath);

    const extractedTitle = extractTitle(fileContent);
    const recipeName = extractedTitle || generateRecipeName(filename);

    const recipe: Recipe = {
      id: `${category}-${filename.replace('.js', '')}`,
      name: recipeName,
      description: extractDescription(fileContent),
      category: category,
      filePath: filePath,
      envVariables: extractEnvVariables(fileContent),
      isAuthRequired: requiresAuth(fileContent),
      readmePath: hasReadme ? readmePath : undefined
    };
    
    return recipe;
  } catch (error) {
    console.error(`Error scanning recipe file ${filePath}:`, error);
    return null;
  }
}

/**
 * Scan all recipes in the sigma-api-recipes directory
 */
export function scanAllRecipes(): RecipeCategory[] {
  const categories: RecipeCategory[] = [];
  
  try {
    // Check if recipes directory exists
    if (!fs.existsSync(RECIPES_PATH)) {
      console.warn(`Recipes directory not found at: ${RECIPES_PATH}`);
      return categories;
    }
    
    const items = fs.readdirSync(RECIPES_PATH);
    
    for (const item of items) {
      const itemPath = path.join(RECIPES_PATH, item);
      const stat = fs.statSync(itemPath);
      
      // Skip files (like package.json, get-access-token.js at root level)
      if (!stat.isDirectory()) {
        continue;
      }
      
      // Skip hidden directories and node_modules
      if (item.startsWith('.') || item === 'node_modules') {
        continue;
      }
      
      // Scan recipes in this category
      const recipes: Recipe[] = [];
      const categoryFiles = fs.readdirSync(itemPath);
      
      for (const file of categoryFiles) {
        const filePath = path.join(itemPath, file);
        const fileStat = fs.statSync(filePath);
        
        if (fileStat.isFile()) {
          const recipe = scanRecipeFile(filePath, item);
          if (recipe) {
            recipes.push(recipe);
          }
        }
      }
      
      if (recipes.length > 0) {
        categories.push({
          name: item.charAt(0).toUpperCase() + item.slice(1),
          recipes: recipes.sort((a, b) => a.name.localeCompare(b.name))
        });
      }
    }
    
    return categories.sort((a, b) => a.name.localeCompare(b.name));
  } catch (error) {
    console.error('Error scanning recipes:', error);
    return categories;
  }
}

/**
 * Find the authentication recipe (get-access-token.js)
 */
export function getAuthRecipe(): Recipe | null {
  try {
    const authFilePath = path.join(RECIPES_PATH, 'get-access-token.js');
    
    if (fs.existsSync(authFilePath)) {
      return scanRecipeFile(authFilePath, 'authentication');
    }
    
    return null;
  } catch (error) {
    console.error('Error finding auth recipe:', error);
    return null;
  }
}