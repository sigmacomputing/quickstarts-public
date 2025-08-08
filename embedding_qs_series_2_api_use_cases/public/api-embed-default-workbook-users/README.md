# API Set Default Workbook QuickStart

## Overview
This QuickStart demonstrates how to implement a default workbook selection feature for embedded Sigma content using the Sigma API and local storage. Users can set one preferred workbook per user account that will automatically load whenever that user is selected.

## Features

### Core Functionality
- **User-Based Default Workbooks**: Each user can have one default workbook that loads automatically
- **Radio Button Interface**: Clean workbook selection using radio buttons instead of dropdowns
- **Collapsible Controls**: Workbook list starts collapsed and can be expanded as needed
- **Persistent Storage**: Default workbook preferences are stored locally using lowDB
- **Visual Indicators**: Default workbooks are highlighted with bold text and "(Default)" labels
- **Auto-loading**: Default workbooks load automatically on user selection and page refresh

## Technical Implementation

### API Endpoints
- `GET /api/default-workbook/:userEmail` - Retrieves user's default workbook
- `POST /api/default-workbook` - Sets a workbook as user's default
- `DELETE /api/default-workbook/:userEmail` - Clears user's default workbook
- `GET /api/workbooks` - Fetches available workbooks
- `POST /api/jwt/workbook` - Generates JWT token for embedding

### Data Storage
Default workbook preferences are stored in `/data/default-workbooks.json` using lowDB for simple JSON-based persistence.

### Race Condition Protection
The implementation includes comprehensive protection against race conditions:
- Operation synchronization flags prevent conflicts during set/clear operations
- Loading debouncing prevents rapid-fire embed loading
- Concurrent load prevention blocks new loads while one is in progress
- Clean state management ensures proper cleanup when switching users

### Sigma Integration
- Custom loading overlay with Sigma postMessage integration
- Support for multiple postMessage event types (`workbook:dataLoaded`, `workbook:loaded`, etc.)
- Fallback timeout mechanisms for stuck loading states
- Emergency "Close Loader" button for problematic loads

## File Structure
api-embed-default-workbook-users/
├── index.html          # Main page with default workbook functionality
└── README.md           # This documentation

## Configuration
Uses the same `.env` configuration as other QuickStarts:
CLIENT_ID=your_sigma_client_id
SECRET=your_sigma_secret
BASE_URL=https://aws-api.sigmacomputing.com/v2
VIEW_EMAIL=view.embed.qs@example.com
BUILD_EMAIL=build.embed.qs@example.com
DEBUG=true

## Troubleshooting

### Common Issues
- **Default Not Loading**: Check browser console for API errors, verify user has workbook access
- **Clear Button Not Working**: Ensure user email is being passed correctly, check API logs
- **Loading Overlay Stuck**: Verify postMessage events are firing, use "Close Loader" button if needed
