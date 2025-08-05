# API Loading Indicators QuickStart

## Overview
This QuickStart demonstrates how to implement custom loading indicators for Sigma embeds that display while the workbook is loading. It listens for Sigma's `workbook:dataLoaded` postMessage event to know when to hide the loading indicator, providing a smooth user experience during embed initialization.

## Features
- Custom Loading Indicators: Professional loading spinner with translucent iframe overlay
- Event-Driven Loading: Listens for Sigma's `workbook:dataLoaded` event to hide loading indicator
- Timeout Protection: 30-second timeout with user-friendly error message
- Visual Feedback: Iframe becomes translucent while loading with centered spinner overlay
- User Selection: Switch between View Users and Build Users to see different permission levels
- Workbook Selection: Choose from available workbooks in your Sigma environment
- JWT Token Display: View the generated JWT token and its decoded payload for learning purposes
- Information Panel: Toggle sidebar showing embed URL, JWT token, and decoded JWT payload
- Responsive Design: Clean, mobile-friendly interface

## Technical Implementation

### Core Technologies
- PostMessage API: Listens for Sigma's `workbook:dataLoaded` event
- Custom CSS Overlay: Positioned loading spinner with iframe translucency
- Timeout Handling: 30-second safety timeout with error recovery
- JWT Generation: Uses `/api/jwt/workbook` endpoint
- Workbook Data: Fetches available workbooks from `/api/workbooks`
- Environment Config: Loads configuration from `/env.json`
- Debug Mode: Enable DEBUG=true in .env file for detailed console logging

### Sigma Events Integration
- Event Origin Validation: Ensures postMessage events come from Sigma domains
- Event Type Filtering: Specifically listens for `workbook:dataLoaded` events
- Multiple Load Handling: Properly handles switching between workbooks
- Error Recovery: Hides loading indicator if embed loading fails

## File Structure
api-embed-custom-loader/
├── index.html          # Main page with custom loading indicator implementation
└── README.md           # This comprehensive documentation

## API Endpoints Used
- `GET /api/workbooks` - Fetches available workbooks
- `POST /api/jwt/workbook` - Generates JWT token for embedding

## Configuration
The page respects all embedding configuration options from your `.env` file:
- `EMBED_URL_BASE` - Used for postMessage origin validation
- `hide_folder_navigation`
- `hide_menu` 
- `menu_position`
- `theme`
- `lng` (language)
- And other standard Sigma embedding parameters

## Custom Loading Indicator Implementation

### CSS Classes and Styling
- `.embed-loading-overlay` - Positioned overlay covering the iframe area
- `.loading-spinner` - Centered spinner container with shadow
- `.spinner` - Animated CSS spinner using Sigma orange color (#f57c00)
- `.loading-text` - Loading message text styling
- `#sigma-embed.loading` - Translucency effect (opacity: 0.3) during loading

### JavaScript Functions
- `showEmbedLoader()` - Displays overlay, adds loading class, starts timeout
- `hideEmbedLoader()` - Hides overlay, removes loading class, clears timeout
- `showLoadingError()` - Shows timeout error message to user

### Event Handling
- Listens for `window.addEventListener("message")` events
- Validates event origin against Sigma domains
- Filters for `event.data.type === "workbook:dataLoaded"`
- Automatically hides loader when event received