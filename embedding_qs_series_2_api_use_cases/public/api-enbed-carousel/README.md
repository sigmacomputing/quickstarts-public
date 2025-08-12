# API Getting Started QuickStart

## Overview
This is the foundational QuickStart page that demonstrates the basic Sigma embedding workflow using JWT authentication. It provides a simple interface to select users and workbooks, and displays the embedded Sigma content.

## Features
- User Selection: Switch between View Users and Build Users to see different permission levels
- Workbook Selection: Choose from available workbooks in your Sigma environment
- JWT Token Display: View the generated JWT token and its decoded payload for learning purposes
- Information Panel: Toggle sidebar showing embed URL, JWT token, and decoded JWT payload
- Responsive Design: Clean, mobile-friendly interface

## How It Works

### Authentication Flow
1. Select a user (View or Build user) from the dropdown
2. Choose a workbook to embed
3. The application generates a JWT token with appropriate claims for the selected user
4. The JWT is used to authenticate and authorize the embedded Sigma content

### User Types
- View Users: Can view and interact with the embedded content but cannot edit
- Build Users: Have full editing capabilities within the embedded workbook

## Technical Implementation
- JWT Generation: Uses `/api/jwt/api-getting-started` endpoint
- Workbook Data: Fetches available workbooks from `/api/workbooks`
- Environment Config: Loads configuration from `/env.json`
- Debug Mode: Enable DEBUG=true in .env file for detailed console logging

## File Structure
```
api-getting-started/
├── index.html          # Main page with embedded Sigma content
└── README.md           # This documentation
```

## API Endpoints Used
- `GET /api/workbooks` - Fetches available workbooks
- `POST /api/jwt/api-getting-started` - Generates JWT token for embedding

## Configuration
The page respects all embedding configuration options from your `.env` file:
- `hide_folder_navigation`
- `hide_menu`
- `menu_position`
- `theme`
- `lng` (language)
- And other standard Sigma embedding parameters

## Getting Started
1. Ensure your `.env` file is properly configured with Sigma API credentials
2. Start the server: `npm start`
3. Navigate to `/api-getting-started`
4. Select a user and workbook to see the embedded content
5. Use the Toggle Info Panel to view JWT details and debug information

## Debug Information
When DEBUG=true is set in your environment:
- Console logging shows detailed JWT information
- Embed URL and token details are displayed in the sidebar
- User selection and workbook loading events are logged

This QuickStart serves as the foundation for understanding Sigma embedding concepts before exploring more advanced features in the other API examples.