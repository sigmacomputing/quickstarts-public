# API Embed Bookmarks QuickStart

## Overview
This QuickStart demonstrates Sigma's bookmark functionality, allowing users to save and switch between different views of the same workbook. Bookmarks capture filters, parameters, and other state information that can be recalled later.

## Features
- **User Selection**: Switch between View Users and Build Users
- **Workbook Selection**: Choose from available workbooks
- **Bookmark Management**: 
  - View existing bookmarks in a dropdown
  - Create new bookmarks (Build Users only)
  - Switch between bookmarks and original workbook
- **Interactive Embed**: Bookmarks capture current state when created
- **Information Panel**: Toggle sidebar with JWT and debug information

## How It Works

### Bookmark Workflow
1. **Select User & Workbook**: Choose a user and workbook to embed
2. **Interact with Content**: Apply filters, change parameters, or navigate within the workbook
3. **Create Bookmark** (Build Users only): 
   - Interact with the embedded content to generate an `exploreKey`
   - Enter a bookmark name and click "Create Bookmark"
   - The current state is saved as a bookmark via Sigma's API
4. **Switch Between Views**: Use the "Saved Bookmark" dropdown to switch between bookmarks or return to the "Original Workbook"

### User Permissions
- **View Users**: Can view and switch between existing bookmarks but cannot create new ones
- **Build Users**: Full access to create, view, and switch between bookmarks

### ExploreKey Mechanism
The bookmark functionality relies on Sigma's `exploreKey` system:
- When users interact with embedded content, Sigma generates an `exploreKey` containing the current state
- This `exploreKey` is captured via postMessage events from the iframe
- The `exploreKey` is then used when creating bookmarks to save the current view state

## Technical Implementation

### API Integration
- **Direct Sigma API**: This version uses Sigma's bookmark API directly
- **Bookmark Creation**: Uses `/api/bookmarks/create-bookmark` endpoint
- **Bookmark Listing**: Uses `/api/bookmarks/list` endpoint
- **JWT Generation**: Uses `/api/jwt/api-embed-bookmarks` endpoint

### Key Components
- **PostMessage Listener**: Captures `exploreKey` changes from the embedded iframe
- **Dynamic Controls**: Bookmark creation controls appear only when user has edit permissions
- **State Management**: Tracks current `exploreKey` and user permissions

## File Structure
```
api-embed-bookmarks/
├── index.html          # Main page with bookmark functionality
└── README.md           # This documentation
```

## API Endpoints Used
- `GET /api/workbooks` - Fetches available workbooks
- `GET /api/bookmarks/list` - Lists bookmarks for a workbook
- `POST /api/bookmarks/create-bookmark` - Creates new bookmarks
- `POST /api/jwt/api-embed-bookmarks` - Generates JWT tokens with bookmark support

## Configuration
Respects all standard Sigma embedding parameters from `.env`:
- Build Users get full menu access and folder navigation
- View Users get restricted interface (hidden menu, no folder nav)
- DEBUG mode provides detailed console logging

## Getting Started
1. Configure your `.env` file with Sigma API credentials
2. Start the server: `npm start`
3. Navigate to `/api-embed-bookmarks`
4. Select a Build User to create bookmarks:
   - Choose a workbook and wait for it to load
   - Interact with the content (apply filters, change parameters)
   - Enter a bookmark name and click "Create Bookmark"
5. Switch to a View User to see how bookmarks appear to end users
6. Use the dropdown to switch between saved bookmarks

## Debug Information
Enable DEBUG=true for detailed logging of:
- ExploreKey capture events
- Bookmark creation process
- JWT token generation
- User permission changes

## Important Notes
- **ExploreKey Required**: Bookmarks can only be created after interacting with the embedded content to generate an `exploreKey`
- **Build User Requirement**: Only Build Users can create new bookmarks
- **State Persistence**: Bookmarks are stored in Sigma and persist across sessions
- **Workbook Association**: Bookmarks are tied to specific workbooks

This QuickStart provides the foundation for understanding bookmark functionality before exploring the database-enhanced version in `api-embed-bookmarks_db`.