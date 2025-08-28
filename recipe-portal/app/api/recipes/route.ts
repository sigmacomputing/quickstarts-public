import { NextResponse } from 'next/server';
import { scanAllRecipes, getAuthRecipe } from '../../../lib/recipeScanner';

export async function GET() {
  try {
    const categories = scanAllRecipes();
    const authRecipe = getAuthRecipe();
    
    return NextResponse.json({
      categories,
      authRecipe,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error in recipes API:', error);
    return NextResponse.json(
      { error: 'Failed to scan recipes' },
      { status: 500 }
    );
  }
}