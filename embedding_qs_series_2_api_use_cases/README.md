# Sigma Embedding API QuickStarts

A comprehensive collection of examples demonstrating Sigma Computing's embedding capabilities through practical API implementations. These QuickStarts showcase different embedding patterns, from basic authentication to advanced bookmark management and flexible content embedding.

## Overview

This project provides seven distinct QuickStart examples that progressively demonstrate Sigma's embedding features:

1. **Getting Started** - Basic embedding with JWT authentication
2. **Embed Bookmarks** - Direct Sigma API bookmark functionality  
3. **Bookmark Sharing with Local DB** - Enhanced bookmarks with local storage and sharing
4. **Embed Controls** - Flexible embedding (workbook/page/element types)
5. **API Export Modal** - Scheduled export functionality using the Sigma API
6. **Custom Loading Screen** - Enhanced embedding with custom loading overlays
7. **Menu Control & Page Navigation** - Advanced menu visibility control and page navigation

Each QuickStart includes a complete web interface with user switching, debug information, and comprehensive documentation.

## Quick Start

### Prerequisites
- Node.js (v14 or higher)
- Sigma Computing account with API access
- Client credentials (Client ID and Secret) from Sigma

### Installation
1. Clone this repository
2. Install dependencies:
   ```bash
   npm install
   ```
3. Configure your environment:
   ```bash
   cp .env.example .env
   # Update .env with your Sigma credentials and configuration
   ```
4. Start the application:
   ```bash
   npm start
   ```
5. Open `http://localhost:3000` in your browser

## Project Structure

```
embedding_qs_series_2_api_use_cases/
├── public/                          # Static web assets
│   ├── api-getting-started/         # Basic embedding QuickStart
│   ├── api-embed-bookmarks/         # Direct API bookmarks
│   ├── api-embed-bookmarks_db/      # Database-enhanced bookmarks
│   ├── api-embed-controls/          # Flexible embed types
│   ├── api-embed-export-modal/      # Scheduled export functionality
│   ├── api-embed-custom-loader/     # Custom loading overlay implementation
│   ├── api-embed-hide-menu-page-nav/ # Menu control and page navigation
│   └── styles/                      # Shared CSS styles
├── routes/                          # Express.js API routes
│   └── api/                         # API endpoints
├── helpers/                         # Utility functions and API wrappers
├── data/                           # Local database storage (JSON)
├── .env                            # Environment configuration
├── server.js                       # Main application server
└── package.json                    # Dependencies and scripts
```

## Features

### Core Functionality
- **JWT Authentication** - Secure token generation for embedding
- **User Role Management** - Switch between View and Build users
- **Workbook Discovery** - Dynamic workbook loading from Sigma API
- **Debug Mode** - Comprehensive logging and token inspection

### Advanced Features
- **Bookmark Management** - Create, save, and share bookmarks
- **Local Database Integration** - Enhanced metadata storage with lowdb
- **Permission-Based Filtering** - User-specific bookmark visibility
- **Flexible Embedding** - Support for workbook, page, and element embedding
- **Custom Loading Overlays** - Branded loading experiences with Sigma postMessage integration
- **Menu Visibility Control** - Toggle Sigma menus on/off with intelligent state management
- **Page Navigation** - Dynamic page discovery and navigation with hidden page filtering
- **Dual Embedding Modes** - Workbook-level vs page-level embedding patterns
- **Responsive Design** - Mobile-friendly interfaces

### Developer Tools
- **Environment Configuration** - Centralized .env management
- **Debug Logging** - Detailed console output when DEBUG=true
- **API Documentation** - Individual README files for each QuickStart
- **User Provisioning** - Automated test user creation

## QuickStart Examples

### 1. Getting Started (`/api-getting-started`)
**Purpose**: Learn the basics of Sigma embedding with JWT authentication

**Features**:
- User and workbook selection
- JWT token generation and display
- Basic embed configuration
- Debug information panel

**Best For**: First-time Sigma embedding implementation

### 2. Embed Bookmarks (`/api-embed-bookmarks`)
**Purpose**: Implement bookmark functionality using Sigma's native API

**Features**:
- Create and manage bookmarks
- ExploreKey capture from embedded content
- User permission-based bookmark creation
- Direct Sigma API integration

**Best For**: Basic bookmark functionality without additional complexity

### 3. Bookmark Sharing with Local DB (`/api-embed-bookmarks_db`)
**Purpose**: Advanced bookmark management with sharing and local storage

**Features**:
- Enhanced bookmark metadata storage
- User-specific sharing controls
- Permission-based bookmark filtering
- Bulk bookmark operations
- "Clear All" functionality with API synchronization

**Best For**: Enterprise scenarios requiring advanced bookmark management

### 4. Embed Controls (`/api-embed-controls`)
**Purpose**: Demonstrate flexible embedding options for different content types

**Features**:
- Dynamic embed type selection (workbook/page/element)
- Cascading content discovery
- Adaptive interface based on embed type
- Content-specific JWT generation

**Best For**: Applications requiring granular content embedding

### 5. API Export Modal (`/api-embed-export-modal`)
**Purpose**: Extend an embedded Sigma workbook with scheduled export functionality using the Sigma REST API

This QuickStart demonstrates how to create a comprehensive export management system within a host application. Unlike basic embedding, this implementation provides `View` users with the ability to create, manage, and immediately send scheduled exports directly from the embedded interface.

**Features**:
- **Export Scheduling**: Create email-based export schedules with custom recipients, subjects, and messages
- **Format Selection**: Support for PDF, CSV, and Excel export formats with configurable options
- **Frequency Management**: Configure daily, weekly, or monthly export schedules with custom timing
- **Export Management**: View, edit, delete, and immediately run existing export schedules
- **Workbook Integration**: Seamless integration with embedded workbook selection and preview
- **Security Features**: View-only embed permissions with recipient privacy protection

We will cover these key workflows:

**1: Schedule an Export:**<br>
Allow users to create scheduled exports by configuring recipients, format, frequency, and timing. The system handles workbook ID resolution and validates all export parameters before creating the schedule via the Sigma API.

**2: Manage Export Schedules:**<br>
Provide users with a comprehensive management interface to view existing schedules, edit configurations (with recipient re-entry for security), and delete schedules they no longer need.

**3: Run Exports Immediately:**<br>
Enable users to trigger immediate export delivery using existing schedule configurations, with the ability to specify custom recipients for ad-hoc sharing.

This approach enables a complete export management experience directly within the embedded environment. It's especially useful for SaaS providers, internal dashboards, or any scenario where users need to share Sigma content via email without requiring direct access to the Sigma interface.

**Best For**: Applications requiring comprehensive export functionality with embedded workbook management

### 6. Custom Loading Screen (`/api-embed-custom-loader`)
**Purpose**: Implement branded loading overlays that properly integrate with Sigma's loading lifecycle

**Features**:
- Custom loading overlay with CSS animations
- Sigma postMessage event integration (`workbook:dataLoaded`)
- High z-index positioning to override Sigma's default loader
- Event-driven loading state management (not timer-based)
- Proper iframe content area coverage

**Best For**: Applications requiring branded loading experiences and professional embed presentation

### 7. Menu Control & Page Navigation (`/api-embed-hide-menu-page-nav`)
**Purpose**: Demonstrate advanced menu visibility control and intelligent page navigation patterns

**Features**:
- Smart menu toggle for workbook-level embeds (hide/show all Sigma menus)
- Dual embedding modes: workbook-level (interactive) vs page-level (clean view)
- Dynamic page discovery with hidden page filtering
- Intelligent UI controls (toggle button only appears when relevant)
- Parameter state management across embedding mode switches
- Security-first page filtering (hidden pages excluded server-side)

**Best For**: Applications requiring granular control over Sigma UI elements and custom navigation experiences

## Configuration

### Environment Variables
The `.env` file controls all aspects of the application:

```env
# Sigma API Configuration
AUTH_URL=https://aws-api.sigmacomputing.com/v2/auth/token
BASE_URL=https://aws-api.sigmacomputing.com/v2
CLIENT_ID=your_client_id
SECRET=your_client_secret

# Test Users
VIEW_EMAIL=view.embed.qs@example.com
BUILD_EMAIL=build.embed.qs@example.com

# Embed Parameters
HIDE_MENU=true
THEME=dark
DEBUG=true
```

### User Provisioning
The application includes user provisioning capabilities:
- Navigate to `/tools/preload-users.html`
- Automatically creates test users with appropriate permissions
- Sets up workspace and team assignments

## API Endpoints

### Core Endpoints
- `GET /api/workbooks` - List available workbooks
- `POST /api/jwt/*` - Generate JWT tokens for different QuickStarts
- `GET /env.json` - Environment configuration for frontend

### Bookmark Endpoints
- `GET /api/bookmarks/list` - List bookmarks for a workbook
- `POST /api/bookmarks/create-bookmark` - Create new bookmark
- `GET /api/bookmarks_db` - Enhanced bookmark listing with filtering
- `POST /api/bookmarks_db` - Create bookmark with local storage
- `DELETE /api/bookmarks_db/clear-all` - Bulk delete bookmarks

### Export Endpoints
- `POST /api/exports` - Create new export schedule
- `GET /api/exports/:workbookId` - List export schedules for a workbook
- `PATCH /api/exports/:scheduleId` - Update existing export schedule
- `DELETE /api/exports/:workbookId/:scheduleId` - Delete export schedule
- `POST /api/exports/:workbookId/send/:scheduleId` - Send export immediately

### Content Discovery
- `GET /api/pages` - List pages in a workbook (with hidden page filtering)
- `GET /api/elements` - List elements on a page

## Development

### Debug Mode
Enable comprehensive logging by setting `DEBUG=true` in your `.env` file:
- JWT token generation details
- API request/response logging
- User permission changes
- Bookmark operation tracking

### Local Development with logging
```bash
# Run with debug logging
DEBUG=true npm start
```

### Testing
Each QuickStart can be tested independently:
1. Start the server
2. Navigate to specific QuickStart URL
3. Use different user types to test permissions
4. Enable DEBUG mode for detailed logging

## Deployment

### Production Considerations
- **Security**: Never commit real credentials to version control
- **Environment**: Use production Sigma URLs in `.env`
- **HTTPS**: Ensure HTTPS for production deployments
- **Rate Limiting**: Implement API rate limiting for production use

### Environment Setup
1. Update `.env` with production values
2. Set appropriate `NODE_ENV=production`
3. Configure proper CORS settings
4. Set up monitoring and logging

## Troubleshooting

### Common Issues
- **JWT Errors**: Check CLIENT_ID and SECRET in `.env`
- **CORS Issues**: Verify EMBED_URL_BASE matches your Sigma instance
- **User Permissions**: Ensure test users have appropriate Sigma permissions
- **Bookmark Issues**: Check workbook sharing and user access rights

### Debug Steps
1. Enable `DEBUG=true` in `.env`
2. Check browser console for detailed logs
3. Verify API endpoints are responding correctly
4. Confirm Sigma credentials and permissions

## Contributing

This project follows standard Node.js development practices:
- Use meaningful commit messages
- Test all QuickStart examples before submitting
- Update documentation for new features
- Follow existing code style and structure

## Support

This project is designed to work with corresponding Sigma QuickStarts. Visit https://quickstarts.sigmacomputing.com to get more information.

For technical issues:
- Check the individual QuickStart README files
- Enable DEBUG mode for detailed logging
- Review the Sigma API documentation
- Check environment configuration in `.env`

## License

This project is provided as educational material for learning Sigma embedding concepts and API implementation patterns.