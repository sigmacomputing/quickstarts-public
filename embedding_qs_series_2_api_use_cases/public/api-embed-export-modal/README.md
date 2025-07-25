# API Export Modal QuickStart

This demonstration shows how to create and manage scheduled exports using the Sigma API from a host application modal interface.

## Overview

This QuickStart demonstrates how to extend an embedded Sigma workbook with scheduled export functionality using the Sigma REST API. Unlike basic embedding scenarios, this implementation provides users with comprehensive export management capabilities directly within the host application.

## Features

- **Export Modal Interface**: Clean modal dialog for configuring export schedules
- **Email Configuration**: Set recipients, subject, and message for scheduled reports
- **Format Selection**: Choose between PDF, CSV, and Excel formats
- **Scheduling Options**: Configure daily, weekly, or monthly export frequency with custom times
- **Export Management**: View, edit, delete, and run existing export schedules
- **Workbook Integration**: Select and export from available workbooks with embedded preview

## How It Works

### Creating Export Schedules
1. **Select Workbook**: Choose a workbook from the dropdown to enable export functionality
2. **Open Export Modal**: Click "Schedule Export" button (enabled after workbook selection)
3. **Configure Export**: 
   - Set recipient email addresses (comma-separated)
   - Customize subject line and message
   - Choose export format (PDF, CSV, Excel)
   - Set frequency (daily, weekly, monthly) and time
4. **Create Schedule**: Submit to create the export schedule via Sigma API

### Managing Export Schedules
- **View Schedules**: "Manage Exports" button appears when schedules exist for selected workbook
- **Edit Schedules**: Modify existing export configurations (recipients require re-entry for security)
- **Run Now**: Immediately trigger an export with custom recipient list
- **Delete Schedules**: Remove export schedules with confirmation

## Technical Implementation

### Core Components
- **Workbook Selection**: Dynamically loads available workbooks via `/api/workbooks`
- **Sigma Embed**: Displays selected workbook using JWT authentication for View users
- **Export API Integration**: Uses Sigma's scheduled notification endpoints
- **Workbook ID Resolution**: Handles URL ID to UUID mapping for API compatibility

### Security Features
- **JWT Authentication**: Secure embed URLs with proper token validation
- **Email Validation**: Client-side validation for recipient email addresses
- **View-Only Access**: Embeds use View user permissions for security
- **Recipient Privacy**: API doesn't expose existing recipients for security compliance

### User Experience
- **Responsive Modals**: Clean modal interfaces with overlay and ESC key support
- **Form Validation**: Required field validation and helpful error messages
- **State Management**: Proper loading states and submission protection
- **Debug Mode**: Comprehensive logging when DEBUG=true in environment

## API Endpoints

### Export Management
- `POST /api/exports` - Create new export schedule
- `GET /api/exports/:workbookId` - List schedules for workbook
- `PATCH /api/exports/:scheduleId` - Update existing export schedule
- `DELETE /api/exports/:workbookId/:scheduleId` - Delete schedule
- `POST /api/exports/:workbookId/send/:scheduleId` - Send export immediately

### Supporting Endpoints
- `GET /api/workbooks` - Fetch available workbooks
- `POST /api/jwt/api-embed-export-modal` - Generate embed JWT tokens

## Configuration

### Environment Variables
- **VIEW_EMAIL**: Email address for embed View user authentication
- **DEBUG**: Enable detailed console logging for development
- **Standard embed options**: Theme, navigation, menu settings, etc.

### Workbook Requirements
- Workbooks must be accessible to the configured View user
- Export functionality requires appropriate Sigma permissions
- Users must have email delivery permissions in Sigma

## Getting Started

1. **Environment Setup**: Ensure your `.env` file includes the required Sigma API credentials and VIEW_EMAIL configuration
2. **User Permissions**: Verify the View user has access to workbooks and export permissions
3. **Access the Interface**: Navigate to `/api-embed-export-modal` from the main application
4. **Select Workbook**: Choose a workbook to enable export functionality
5. **Create Exports**: Use the "Schedule Export" button to create your first scheduled export

## Key Concepts

### Export Schedules
Export schedules are persistent configurations that define:
- **Recipients**: Email addresses to receive the export
- **Content**: Which workbook to export and in what format
- **Timing**: When and how frequently to send the export
- **Metadata**: Subject lines, message content, and delivery options

### Workbook ID Resolution
The system automatically handles the conversion between:
- **URL IDs**: Short identifiers used in Sigma URLs (visible to users)
- **UUIDs**: Full workbook identifiers required by the Sigma API

### Security Model
- **View-Only Embeds**: Users interact with read-only workbook content
- **API-Based Management**: All export operations use secure API endpoints
- **Recipient Privacy**: Existing recipient lists are not exposed for security reasons

## Troubleshooting

### Common Issues
- **Export Button Disabled**: Ensure a workbook is selected first
- **API Errors**: Check Sigma credentials and user permissions in `.env`
- **Email Validation**: Verify recipient email addresses are properly formatted
- **Schedule Not Appearing**: Confirm the workbook has existing schedules

### Debug Mode
Enable `DEBUG=true` in your environment to see detailed logging for:
- API request/response cycles
- Workbook ID resolution process
- Export schedule operations
- JWT token generation and validation

