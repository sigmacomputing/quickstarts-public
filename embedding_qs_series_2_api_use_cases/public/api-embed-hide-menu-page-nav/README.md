# API Hide Menu - Page Navigation QuickStart
This project demonstrates how to control Sigma menu visibility and navigate between workbook pages in embedded applications using the Sigma Embedding API.

## Features
- Dual embedding modes - Workbook-level (with menus) vs page-level (clean view) embedding
- Smart menu control - Toggle Sigma menus on/off for workbook-level embeds
- Page navigation - Dropdown selector for navigating to specific workbook pages
- User role testing - Switch between View and Build users to test different permissions
- JWT security - Secure embedding with proper authentication and parameter passing

## Core Concepts

### Embedding Modes
This demonstration showcases two distinct Sigma embedding approaches:

Workbook-Level Embedding:
- Displays full workbook with all Sigma menus (folder nav, main menu, page tabs)
- Toggle button allows showing/hiding all menus simultaneously  
- Best for: Interactive exploration, user-driven navigation
- URL format: `/workbook/{name}-{id}`

Page-Level Embedding:
- Displays individual page content only (clean, focused view)
- No navigation menus (by Sigma design - pages are standalone)
- Best for: Dashboards, reports, embedded analytics
- URL format: `/workbook/{name}-{id}/page/{pageId}`

### Menu Control Logic
The system uses intelligent parameter management:

- Initial state: Uses `.env` defaults (typically menus visible)
- Toggle button: Overrides defaults to hide/show menus
- Page selection: Automatically switches between embedding modes
- Parameter flow: Frontend → JWT Route → Build URL → Sigma Embed

## Technical Implementation

### Key Parameters
# .env Configuration
HIDE_FOLDER_NAVIGATION=false  # Show folder navigation
HIDE_MENU=false               # Show main menu bar
HIDE_PAGE_CONTROLS=false      # Show page controls
MENU_POSITION=top             # Position menus at top

### Parameter Logic
Workbook-level (menus visible):
hideFolderNav = "false"
hideMenu = "false" 
hidePageControls = "false"
menuPosition = "top"

Workbook-level (menus hidden):
hideFolderNav = "true"
hideMenu = "true" 
hidePageControls = "true"
menuPosition = "none"

Page-level (always clean):
hideFolderNav = "true"
hideMenu = "true" 
hidePageControls = "true"
menuPosition = "none"

### API Endpoints
The application uses several API endpoints to provide dynamic page navigation:

Page Discovery:
GET /api/pages?workbookUrlId={workbookId}
- Fetches list of all pages in a selected workbook
- Filters out hidden pages - Pages marked as `hidden: true` in Sigma are excluded
- Returns array of page objects with `pageId` and `name` properties  
- Used to populate the page dropdown dynamically
- Example response:
[
  {"pageId": "3LYCS8UtIU", "name": "Page 1"},
  {"pageId": "9XmN2PqR5K", "name": "Sales Dashboard"}, 
  {"pageId": "7KpL4WnD8M", "name": "Analytics Overview"}
]

JWT Generation:
POST /api/jwt/workbook?embedType={type}&workbookUrlId={id}&targetId={pageId}
- Generates secure JWT token for embedding
- `embedType`: "workbook" (all pages) or "page" (single page)
- `targetId`: Required for page-level embeds, specifies which page
- Request body includes menu visibility parameters
- Returns JWT and complete embed URL

### Page Navigation Implementation
Frontend Flow:
1. Workbook Selection → Triggers `loadPages(workbookUrlId)`
2. API Call → `fetch('/api/pages?workbookUrlId=' + workbookId)`
3. Dropdown Population → Pages added to dropdown with "Workbook (all pages)" as default
4. Page Selection → Triggers `loadEmbed()` with appropriate `embedType` and `targetId`

Key Functions:
- `loadPages(workbookUrlId)` - Fetches and populates page dropdown
- `loadEmbed()` - Generates JWT and loads embed with current page selection
- Page selection automatically switches between workbook/page embedding modes

### File Structure
- `index.html` - Main application with embedding logic and UI
- `routes/api/jwt.js` - JWT generation with parameter extraction
- `helpers/build-embed-url.js` - URL construction with parameter handling
- `.env` - Default menu visibility configuration

## Troubleshooting

### Menus Not Appearing
- Verify `.env` has `MENU_POSITION=top` (not `none` or empty)
- Check menu parameters are `false` in `.env` for default visible state
- Inspect JWT payload for correct `hide_*` parameter values

### Toggle Button Issues
- Button only appears for workbook-level embeds (hidden for pages by design)
- Ensure `menusHidden` state resets when switching between workbook/page modes
- Check console logs for parameter values being sent to Sigma

### Custom Loader Problems  
- Verify CSS has `z-index: 9999 !important` on `.embed-loading-overlay`
- Check that loader appears before iframe src is set
- Ensure loader is hidden after iframe load event

### Page Navigation Issues
- Hidden pages not filtering: Check server logs for filtering messages when `DEBUG=true`
- Page fails to load: Hidden pages in Sigma will fail to embed and may revert to default page
- Missing pages: Only visible pages (`hidden: false`) appear in dropdown by design

## Security Notes
- Menu parameters are passed through JWT for security
- Page navigation doesn't expose internal Sigma URLs
- User permissions are enforced at the JWT level
- All embed URLs include proper authentication tokens