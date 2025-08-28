import { NextResponse } from 'next/server';
import { 
  storeCredentials, 
  getStoredCredentials, 
  hasStoredCredentials, 
  clearStoredCredentials,
  getStoredCredentialNames,
  getDefaultCredentialSetName,
  setDefaultCredentialSet 
} from '../../../lib/keyStorage';

// GET - Check if stored credentials exist and optionally retrieve them
export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const retrieve = searchParams.get('retrieve') === 'true';
    const list = searchParams.get('list') === 'true';
    const setName = searchParams.get('set');
    
    const hasKeys = await hasStoredCredentials();
    
    if (!hasKeys) {
      return NextResponse.json({
        hasStoredKeys: false,
        credentials: null,
        credentialSets: [],
        defaultSet: null
      });
    }
    
    const credentialSets = await getStoredCredentialNames();
    const defaultSet = await getDefaultCredentialSetName();
    
    if (list) {
      // Return list of available sets
      return NextResponse.json({
        hasStoredKeys: true,
        credentialSets,
        defaultSet,
        credentials: null
      });
    }
    
    if (retrieve) {
      const credentials = await getStoredCredentials(setName || undefined);
      return NextResponse.json({
        hasStoredKeys: true,
        credentials: credentials || null,
        credentialSets,
        defaultSet
      });
    }
    
    return NextResponse.json({
      hasStoredKeys: true,
      credentials: null,
      credentialSets,
      defaultSet
    });
    
  } catch (error) {
    console.error('Error checking stored keys:', error);
    return NextResponse.json(
      { error: 'Failed to check stored credentials' },
      { status: 500 }
    );
  }
}

// POST - Store configuration (credentials + server settings)
export async function POST(request: Request) {
  try {
    const { clientId, clientSecret, name, setAsDefault, baseURL, authURL } = await request.json();
    
    if (!clientId || !clientSecret) {
      return NextResponse.json(
        { error: 'Client ID and Client Secret are required' },
        { status: 400 }
      );
    }
    
    if (!name || name.trim() === '') {
      return NextResponse.json(
        { error: 'Credential set name is required' },
        { status: 400 }
      );
    }
    const credentialSetName = name.trim();
    const success = await storeCredentials(clientId, clientSecret, credentialSetName, baseURL, authURL);
    
    // Set as default if requested
    if (success && setAsDefault) {
      await setDefaultCredentialSet(credentialSetName);
    }
    
    if (success) {
      return NextResponse.json({
        success: true,
        message: 'Credentials stored successfully'
      });
    } else {
      return NextResponse.json(
        { error: 'Failed to store credentials' },
        { status: 500 }
      );
    }
    
  } catch (error) {
    console.error('Error storing credentials:', error);
    return NextResponse.json(
      { error: 'Failed to store credentials' },
      { status: 500 }
    );
  }
}

// DELETE - Clear stored credentials (all or specific config)
export async function DELETE(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const configName = searchParams.get('config');
    
    const success = await clearStoredCredentials(configName || undefined);
    
    if (success) {
      const message = configName 
        ? `Config "${configName}" deleted successfully`
        : 'All stored credentials cleared successfully';
        
      return NextResponse.json({
        success: true,
        message
      });
    } else {
      return NextResponse.json(
        { error: 'Failed to clear stored credentials' },
        { status: 500 }
      );
    }
    
  } catch (error) {
    console.error('Error clearing stored credentials:', error);
    return NextResponse.json(
      { error: 'Failed to clear stored credentials' },
      { status: 500 }
    );
  }
}