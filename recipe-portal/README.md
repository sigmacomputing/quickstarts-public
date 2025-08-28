# QuickStarts API Toolkit
Experiment with Sigma API calls and learn common request flows

## Features

### Recipes:
- **Smart Parameter Detection**: Automatically detects and provides dropdown selection for Sigma resources (teams, members, workbooks, etc.)
- **Interactive Execution**: Run recipes directly in the browser with real-time results
- **Parameter Summary**: View which parameters were used in each request
- **Code Viewing**: Browse the actual JavaScript code for each recipe

### Quick API Explorer:
- **Common Endpoints**: Curated list of the most useful Sigma API endpoints
- **Zero Setup**: List endpoints require no parameters - perfect for quick exploration
- **One Parameter**: Detail endpoints need just one ID to get specific resource information
- **Alphabetical Organization**: Easy to find the endpoint you need

## Authentication & Config Management

### Smart Config System:
- **Complete Configuration Storage**: Server endpoints + API credentials stored together as named "configs"
- **Multi-Environment Support**: Easily switch between Production, Staging, Development environments
- **One-Click Environment Switching**: Load complete configurations instantly
- **Encrypted Local Storage**: AES-256 encryption for credential security

### Config Management Features:
- **Quick Start**: Load saved configs with one click - no manual entry needed
- **Create New Configs**: Mix and match server endpoints with credentials
- **Update Existing Configs**: Modify and save changes to existing configurations
- **Delete Configs**: Remove configs you no longer need
- **Auto-Save**: Configs saved automatically during authentication when enabled
- **Manual Save**: Explicit save button for immediate config storage

### Token Management:
- **File-Based Storage**: Authentication tokens cached in system temp directory
- **Persistent Sessions**: Tokens survive browser/server restarts for the full hour
- **Automatic Expiration**: Tokens expire after 1 hour (Sigma's standard lifetime)
- **Auto-Cleanup**: Expired tokens automatically detected and removed
- **Manual Session End**: Clear authentication anytime with 🚪 End Session button

### Storage Locations

**Config Storage (encrypted)**:
- **macOS**: `~/Library/Application Support/.sigma-portal/encrypted-keys.json`
- **Windows**: `%APPDATA%\.sigma-portal\encrypted-keys.json`  
- **Linux**: `~/.config/.sigma-portal/encrypted-keys.json`

**Token Cache (temporary)**:
- **macOS**: `/var/folders/.../sigma-portal-token.json`
- **Windows**: `%TEMP%\sigma-portal-token.json`
- **Linux**: `/tmp/sigma-portal-token.json`

### Developer Experience Benefits
- **Environment Switching**: Instant switch between Production ↔ Staging ↔ Development
- **Zero Re-entry**: Load complete configs without typing credentials repeatedly
- **Secure Storage**: Military-grade AES-256 encryption for stored credentials
- **Clean Separation**: Configs stored outside project directory (never committed to git)
- **Visual Feedback**: Clear indicators show saved/unsaved state and notifications
- **Flexible Workflow**: Session-only credentials OR persistent named configs

### Config Workflow
1. **First Time**: Enter server endpoint + credentials → Save as named config (e.g., "Production")
2. **Daily Use**: Quick Start → Select "Production" → Instantly loaded and ready
3. **Environment Switch**: Quick Start → Select "Staging" → Switched in one click
4. **New Environment**: "✨ New Config" → Enter details → Save with new name

## Getting Started
Sigma_QuickStart_Public_Repo


1. **Setup**: `npm install && npm run dev`
2. **First-Time Config**: Open any recipe → **Config** tab → Enter server endpoint + credentials → Save as named config
3. **Daily Use**: **Quick Start** section → Select your saved config → Ready to go!
4. **Explore**: Use the ⚡ Quick API tab to explore common endpoints with smart parameters
5. **Run Recipes**: Browse recipes by category and execute them with real-time results

### Config Tab Features
- **Quick Start**: Load saved configs instantly (appears when configs exist)
- **Server Endpoint**: Choose your Sigma organization's server location
- **API Credentials**: Enter Client ID and Client Secret
- **Config Storage**: Save complete configurations with names like "Production", "Staging"
- **Save Config**: Manual save button for immediate storage
- **New Config**: Clear form to create fresh configurations
- **Delete**: Remove configs you no longer need (🗑️ button when config selected)

## Requirements
- Node.js 18+
- Sigma API credentials (Client ID and Secret)
- Valid Sigma organization access

## Development
```bash
npm install
npm run dev
```

Navigate to `http://localhost:3001` to start exploring the Sigma API.

## Project Structure
```
recipe-portal/
├── app/                    # Next.js app directory
│   ├── api/               # API routes
│   │   ├── execute/       # Recipe execution
│   │   ├── resources/     # Resource fetching for dropdowns
│   │   ├── keys/          # Config management (CRUD operations)
│   │   ├── token/         # Token management & caching
│   │   └── call/          # Quick API endpoint calls
├── components/            # React components
│   ├── QuickApiExplorer.tsx  # Quick API exploration interface
│   ├── QuickApiModal.tsx     # API endpoint execution modal
│   ├── SmartParameterForm.tsx # Smart parameter detection & forms
│   ├── CodeViewer.tsx        # Recipe viewer with Config tab
│   ├── AuthRecipeCard.tsx    # Authentication recipe card
│   └── RecipeCard.tsx        # Standard recipe cards
├── lib/                   # Utilities
│   ├── smartParameters.ts # Parameter detection logic
│   ├── keyStorage.ts      # Encrypted config storage
│   └── recipeScanner.ts   # Recipe discovery & analysis
└── recipes/               # Self-contained recipe files (copied from sigma-api-recipes)
    ├── connections/       # Connection-related recipes
    ├── members/           # Member management recipes  
    ├── teams/             # Team management recipes
    ├── workbooks/         # Workbook operations
    ├── embedding/         # Embedding examples
    └── get-access-token.js # Authentication helper
```

For setup instructions and API credential creation, visit the QuickStart: [Sigma REST API Recipes](https://quickstarts.sigmacomputing.com/guide/developers_api_code_samples/index.html?index=..%2F..index#0)