# API Bookmark Sharing with Local DB QuickStart

## Overview
This advanced QuickStart extends basic bookmark functionality with local database storage, sharing capabilities, and comprehensive bookmark management. It demonstrates how to enhance Sigma's bookmark API with additional metadata and sharing controls.

## Features

### Core Bookmark Functionality
- **User Selection**: Switch between View Users and Build Users with different permission levels
- **Workbook Selection**: Choose from available workbooks
- **Bookmark Management**: Create, view, delete, and switch between bookmarks
- **Clear All Bookmarks**: Bulk delete all bookmarks with confirmation dialog (Build Users only)
- **Auto-State Management**: Automatic panel closure and form reset when switching to View Users

### Advanced Features
- **Local Database Storage**: Bookmarks stored in local `bookmarks.json` with additional metadata
- **Sharing Controls**: 
  - Share bookmarks with specific users or teams
  - "Embed_Users" team sharing for organization-wide access
  - Private bookmarks (creator only)
- **Permission-Based Filtering**: View Users only see bookmarks shared with them
- **Bookmark Panel**: Comprehensive sidebar for creating and managing bookmarks
- **Real-time Updates**: Automatic refresh of bookmark lists after operations

### User Interface
- **Toggle Info Panel**: Collapsible sidebar with JWT and debug information
- **Bookmark Management Panel**: Slide-out panel for creating, editing, and deleting bookmarks
- **Permission-Based UI**: Management buttons only visible to Build Users
- **Smart State Management**: Form automatically resets when switching between Original Workbook and bookmarks
- **Responsive Design**: Mobile-friendly interface with proper button positioning and panel behavior

## How It Works

### Database-Enhanced Workflow
1. **User & Workbook Selection**: Choose user type and workbook
2. **Bookmark Creation** (Build Users only):
   - Click "Manage Bookmarks" button to open the bookmark panel
   - Interact with embedded content to generate `exploreKey`
   - Fill out bookmark details:
     - Name and description
     - Sharing options (Private, specific users, or Embed_Users team)
   - Submit to save both in Sigma API and local database
3. **Bookmark Access**: 
   - View Users see only bookmarks shared with them
   - Build Users see all bookmarks they created
4. **Bookmark Management**: Delete individual bookmarks or clear all bookmarks

### Sharing System
- **Private**: Only the creator can see the bookmark
- **User-Specific**: Share with individual email addresses
- **Team Sharing**: Share with "Embed_Users" team for organization access
- **Permission Filtering**: Automatic filtering based on user permissions

### Local Database Integration
The system maintains a local `bookmarks.json` file that stores:
```json
{
  "id": "sigma-bookmark-id",
  "userEmail": "creator@example.com", 
  "workbookUrlId": "workbook-identifier",
  "exploreKey": "captured-state",
  "name": "Bookmark Name",
  "descr": "Description",
  "isShared": true/false,
  "sharedWith": ["email1@example.com", "team:Embed_Users"]
}
```

## Technical Implementation

### API Architecture
- **Dual Storage**: Bookmarks saved to both Sigma API and local database
- **Synchronization**: Clear All operation removes from both systems
- **Filtering**: Local database enables advanced permission filtering

### API Endpoints

#### Local Bookmark Management Endpoints
These are custom endpoints implemented in this QuickStart for enhanced bookmark functionality:
- `GET /api/bookmarks_db` - Lists bookmarks with filtering and sharing logic
- `POST /api/bookmarks_db` - Creates bookmarks in both Sigma API and local database
- `DELETE /api/bookmarks_db/bookmarks/:id` - Deletes specific bookmark from both systems
- `DELETE /api/bookmarks_db/clear-all` - Bulk delete operation for all bookmarks

#### Sigma API Integration Endpoints
These endpoints interact with Sigma's REST API:
- `POST /api/jwt/api-embed-bookmarks_db` - Generate embed JWT tokens for Sigma embedding
- Additional Sigma bookmark API calls are made internally through the local endpoints above

### Advanced Features
- **State Management**: Comprehensive form reset and panel management
- **User Role Enforcement**: Automatic UI changes and panel closure when switching between user types
- **Error Handling**: Graceful handling of API failures with user feedback  
- **Debug Logging**: Extensive DEBUG mode logging for troubleshooting and state tracking
- **Throttling**: API rate limiting for bulk operations
- **Button Overlap Prevention**: Smart CSS and state management prevents UI conflicts

## File Structure
```
api-embed-bookmarks_db/
├── index.html          # Main page with enhanced bookmark functionality
└── README.md           # This documentation
```

## Configuration

### Environment Variables
All standard Sigma embedding parameters plus:
- `DEBUG=true` - Enable detailed console logging
- Database file automatically created at `/data/bookmarks.json`

### User Setup
Configure your `.env` with:
- `VIEW_EMAIL` - Email for View User testing
- `BUILD_EMAIL` - Email for Build User testing
- `SIGMA_API_KEY` and related Sigma credentials

## Getting Started

### Basic Usage
1. Configure `.env` file with Sigma credentials
2. Start server: `npm start`  
3. Navigate to `/api-embed-bookmarks_db`
4. Select Build User and workbook
5. Click "Manage Bookmarks" to open bookmark panel
6. Interact with embedded content and create bookmarks
7. Switch to View User to test permission filtering and automatic panel management

### Testing Sharing Features
1. Create bookmarks as Build User with different sharing settings:
   - Private bookmark
   - Bookmark shared with View User email
   - Bookmark shared with "team:Embed_Users"
2. Switch to View User to verify filtering works correctly
3. Test "Clear All Bookmarks" functionality

### Debug Mode
Enable `DEBUG=true` to see:
- Bookmark creation process
- Permission filtering logic
- API synchronization between Sigma and local database
- State management during operations
- User role switching and panel management
- Button visibility and CSS state changes

## Important Notes

### Permission System
- **View Users**: Only see bookmarks explicitly shared with them or "team:Embed_Users"
- **Build Users**: See all bookmarks (this can be customized)
- **Creator Access**: Users always see bookmarks they created

### Data Persistence  
- **Sigma API**: Primary bookmark storage with Sigma's native functionality
- **Local Database**: Additional metadata for sharing and filtering
- **Synchronization**: Both systems updated during create/delete operations

### Error Handling
- Graceful fallbacks if local database is unavailable
- User-friendly error messages for API failures
- Automatic state reset after errors

## Advanced Customization
This QuickStart provides a foundation for building sophisticated bookmark management systems with:
- Custom sharing permissions
- Advanced filtering logic  
- Additional metadata storage
- Integration with external user management systems

The local database approach enables rich bookmark experiences beyond what Sigma's API provides natively.