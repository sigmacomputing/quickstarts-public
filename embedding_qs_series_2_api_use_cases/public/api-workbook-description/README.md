# API Workbook Description QuickStart
This demonstration shows how to add and manage workbook descriptions using a local database store from a host application modal interface.

## Overview
This QuickStart demonstrates how to extend an embedded Sigma workbook with description management functionality using a local lowdb JSON database. Since Sigma's REST API doesn't provide native workbook description support, this implementation uses a local storage solution to provide users with workbook description capabilities directly within the host application. This same pattern can be extended to store other custom metadata about workbooks such as usage notes, business context, data lineage information, or any other supplementary information that would help users of the embed understand and effectively use the workbook content.

## Features
- Description Modal Interface: Clean modal dialog for adding and editing workbook descriptions
- Local Storage: Persistent description storage using lowdb JSON database
- Workbook Integration: Select and describe available workbooks with embedded preview
- Smart Description Display: Description text appears below the title only when content exists
- Dynamic Button Positioning: "Workbook Description" button intelligently positions itself based on content visibility
- User Tracking: Track creation and modification with member ID attribution
- Build User Access: Restricted to Build users only for enhanced permissions

## How It Works

### Adding Workbook Descriptions
1. Select Workbook: Choose a workbook from the dropdown to enable description functionality
2. Open Description Modal: Click "Workbook Description" button (enabled after workbook selection)
3. Add Description: 
   - Enter description text in the textarea
   - Submit to save via local API endpoint
4. View Description: Description appears below the title (only when content exists)

### Managing Workbook Descriptions
- Edit Descriptions: Modal automatically loads existing description for editing
- Delete Descriptions: Remove descriptions with confirmation dialog (only available when editing existing descriptions)
- Smart Display: Description text only appears when content exists (no placeholder text)
- Dynamic Layout: Button position adjusts automatically based on content visibility
- Real-time Updates: Description display updates immediately after saving or deleting
- User Attribution: Tracks who created and last updated each description
- Persistent Storage: Descriptions saved to local JSON file for persistence

## Technical Implementation

### Core Components
- Workbook Selection: Dynamically loads available workbooks via `/api/workbooks`
- Sigma Embed: Displays selected workbook using JWT authentication for Build users
- Local Database: Uses lowdb for JSON-based description storage
- Description API: Custom REST endpoints for CRUD operations
- Workbook ID Resolution: Handles URL ID to UUID mapping for consistency

### Database Structure
The local database stores descriptions with the following structure:
```json
{
  "workbookDescriptions": [
    {
      "id": "unique-id",
      "workbookId": "workbook-url-id",
      "workbookUuid": "workbook-uuid",
      "description": "Description text",
      "createdBy": "user-email",
      "updatedBy": "user-email",
      "createdAt": "2025-01-01T00:00:00.000Z",
      "updatedAt": "2025-01-01T00:00:00.000Z"
    }
  ]
}
```

### Security Features
- JWT Authentication: Secure embed URLs with proper token validation
- Build User Access: Enhanced permissions through Build user authentication
- Local Storage: Descriptions stored locally for data privacy
- Member ID Tracking: Audit trail for description changes

### User Experience
- Responsive Modal: Clean modal interface with overlay and ESC key support
- Form Validation: Required field validation and helpful error messages
- State Management: Proper loading states and submission protection
- Live Updates: Description display updates without page refresh
- Intelligent UI: Description text and button positioning adapt based on content availability
- Clean Interface: No placeholder text cluttering the interface when no description exists
- Debug Mode: Comprehensive logging when DEBUG=true in environment

## API Endpoints

### Local Description Management Endpoints
These are custom endpoints implemented in this QuickStart for local description storage:
- `POST /api/workbook-descriptions` - Create new workbook description
- `GET /api/workbook-descriptions/:workbookId` - Get description for workbook
- `PUT /api/workbook-descriptions/:workbookId` - Update existing description
- `DELETE /api/workbook-descriptions/:workbookId` - Delete description

### Sigma API Integration Endpoints
These endpoints interact with Sigma's REST API:
- `GET /api/workbooks` - Fetch available workbooks from Sigma
- `POST /api/jwt/api-workbook-description` - Generate embed JWT tokens for Sigma embedding

## Configuration

### Environment Variables
- BUILD_EMAIL: Email address for embed Build user authentication
- DEBUG: Enable detailed console logging for development
- Standard embed options: Theme, navigation, menu settings, etc.

### Database Setup
- Storage Location: `data/wb-descriptions.json`
- Automatic Creation: Database file created automatically if it doesn't exist
- Backup Recommended: Consider backing up the JSON file for production use

### Workbook Requirements
- Workbooks must be accessible to the configured Build user
- Build user provides enhanced permissions for workbook interaction

## File Structure
```
api-workbook-description/
├── index.html          # Main page with embedded Sigma content and modal
└── README.md           # This documentation

Supporting files:
├── data/wb-descriptions.json           # Local database storage
├── helpers/local-wb-descriptions-store.js  # Database helper
└── routes/api/workbook-descriptions.js # API routes
```

## Getting Started

1. Environment Setup: Ensure your `.env` file includes the required Sigma API credentials and BUILD_EMAIL configuration
2. User Permissions: Verify the Build user has access to workbooks
3. Database Initialization: The local database will be created automatically on first use
4. Access the Interface: Navigate to `/api-workbook-description` from the main application
5. Select Workbook: Choose a workbook to enable description functionality
6. Add Descriptions: Use the "Workbook Description" button to create your first description

## Key Concepts

### Local Database Storage
Since Sigma's REST API doesn't provide native workbook description functionality, this implementation uses:
- lowdb: Lightweight JSON database for Node.js applications
- File-based Storage: Descriptions stored in `data/wb-descriptions.json`
- ACID Operations: Consistent read/write operations through lowdb adapter

### Workbook ID Resolution
The system handles both identifier types for consistency:
- URL IDs: Short identifiers used in Sigma URLs (user-facing)
- UUIDs: Full workbook identifiers for internal API consistency
- Dual Storage: Both IDs stored for future compatibility

### Build User Benefits
Build users provide enhanced capabilities:
- Creation Permissions: Ability to create and modify workbook content
- Enhanced Access: Broader workbook and data access permissions
- Administrative Functions: Suitable for description management tasks

## Data Management

### Storage Location
- File Path: `data/wb-descriptions.json`
- Format: JSON with structured workbook description objects
- Backup: Recommended to backup this file for data persistence

### Migration Considerations
- Export Capability: JSON format allows easy data export/import
- API Compatibility: Structure designed for potential future Sigma API integration
- User Attribution: Member ID tracking supports user management

## Troubleshooting

### Common Issues
- Description Button Disabled: Ensure a workbook is selected first
- Modal Not Opening: Check workbook selection and JavaScript console for errors
- Descriptions Not Saving: Verify file permissions for `data/` directory
- Database Errors: Check lowdb file access and JSON structure integrity

### Debug Mode
Enable `DEBUG=true` in your environment to see detailed logging for:
- API request/response cycles for descriptions
- Workbook ID resolution process
- Database read/write operations
- JWT token generation and validation
- Modal state changes and form submissions

### File System Requirements
- Directory Access: Application needs read/write access to `data/` directory
- JSON Integrity: Ensure `wb-descriptions.json` maintains valid JSON structure
- Concurrent Access: lowdb handles concurrent access automatically

