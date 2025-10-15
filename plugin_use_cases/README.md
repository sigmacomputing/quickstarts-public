# Sigma Dashboard Builder - Multi-Area KPI Placement System

A sophisticated host application for Sigma's Dashboard Builder plugin that enables users to place different KPIs across three independent dashboard areas with persistent bookmark management.

## Key Features

- **Multi-Area KPI Placement**: Place different KPIs in 3 independent dashboard areas
- **Persistent Bookmarks**: Save and restore complete multi-area configurations  
- **Incremental Building**: Add KPIs to existing bookmarks without losing current state
- **Cross-Contamination Prevention**: Each area operates independently
- **Real-time Synchronization**: ExploreKey sync across all areas
- **Secure Authentication**: JWT-based authentication with automatic token refresh

## Architecture

### Dual Storage System
- **Sigma Bookmarks**: Store exploreKey and workbook state (single-state, cloud)
- **LowDB Database**: Store multi-area configurations (multi-state, local)  
- **Combined**: Complete bookmark restoration across all dashboard areas

This project provides host application examples for Sigma plugins, demonstrating advanced multi-area plugin integration and persistent state management.

## Project Structure

```
plugin_use_cases/
├── .env                    # Configuration file (copy from .env.example)
├── package.json           # Node.js dependencies
├── server/
│   └── server.js          # Express server for hosting
├── helpers/
│   └── create-jwt.js      # JWT generation utilities
├── routes/
│   └── api/
│       └── jwt.js         # JWT API endpoints
└── public/
    ├── styles/            # Shared CSS styles
    └── dashboard-builder/ # Dashboard Builder plugin host
        └── index.html     # Host application
```

## Quick Start

### Prerequisites

1. **Sigma Instance Access**: You need a Sigma instance with:
   - API credentials (Client ID and Secret)
   - A registered plugin (e.g., "Dashboard Builder")
   - A workbook configured for the plugin

2. **Node.js**: Version 14 or higher

### Setup

1. **Clone and Navigate**:
   ```bash
   cd plugin_use_cases
   ```

2. **Install Dependencies**:
   ```bash
   npm install
   ```

3. **Configure Environment**:
   - Copy `.env` to create your configuration
   - Update the following required fields:
     ```
     ORG_SLUG=your-sigma-org
     CLIENT_ID=your-client-id
     SECRET=your-client-secret
     ADMIN_EMAIL=your-admin-email@company.com
     ```

4. **Start the Server**:
   ```bash
   npm start
   ```

5. **Access the Application**:
   - Open http://localhost:3000
   - Navigate to the Dashboard Builder example

## Dashboard Builder Plugin Host

The Dashboard Builder host application demonstrates:

- **Plugin Integration**: Embedding a Sigma plugin in a host application
- **Bidirectional Communication**: Messages between host and plugin
- **Element Selection**: UI for selecting dashboard elements
- **JWT Authentication**: Secure embedding with proper tokens

### Usage

1. **Select User**: Choose between View or Build user
2. **Enter Workbook ID**: Provide the ID of your Dashboard Builder workbook
3. **Connect Plugin**: Click to establish the connection
4. **Select Elements**: Use the gallery to choose dashboard elements
5. **Add to Dashboard**: Send selected elements to the plugin

### Plugin Communication

The host application communicates with the plugin via `postMessage`:

**Messages sent to plugin**:
- `CONFIGURE`: Initial plugin configuration
- `ADD_ELEMENTS`: Selected elements to add to dashboard

**Messages received from plugin**:
- `PLUGIN_READY`: Plugin has loaded and is ready
- `ELEMENT_SELECTED`: User selected an element in the plugin
- `DASHBOARD_UPDATED`: Dashboard configuration changed

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ORG_SLUG` | Your Sigma organization identifier | Yes |
| `CLIENT_ID` | Sigma API client ID | Yes |
| `SECRET` | Sigma API client secret | Yes |
| `ADMIN_EMAIL` | Admin user email for API calls | Yes |
| `PLUGIN_NAME` | Name of your registered plugin | No |
| `WORKBOOK_NAME` | Default workbook name | No |
| `PORT` | Server port (default: 3000) | No |
| `DEBUG` | Enable debug logging (default: true) | No |

### Plugin-Specific Settings

Additional configuration for plugin behavior:
- `HIDE_FOLDER_NAVIGATION`: Hide folder navigation in embed
- `HIDE_MENU`: Hide Sigma menu
- `MENU_POSITION`: Menu position (top/bottom/none)
- `THEME`: Plugin theme (light/dark)

## Extending to Other Plugins

To add support for additional plugins:

1. **Create Plugin Directory**:
   ```bash
   mkdir public/your-plugin-name
   ```

2. **Copy Template**:
   Use `dashboard-builder/index.html` as a starting point

3. **Customize Communication**:
   - Update message types in JavaScript
   - Modify UI elements for your plugin's needs
   - Add plugin-specific configuration

4. **Update Server Routes**:
   Add any plugin-specific API endpoints if needed

## Development

### Adding New Features

1. **Plugin Communication**: Extend the `postMessage` handlers
2. **UI Elements**: Add new controls in the sidebar
3. **API Endpoints**: Create additional routes in `routes/api/`
4. **Configuration**: Add new environment variables

### Debugging

- Set `DEBUG=true` in `.env` for verbose logging
- Use browser developer tools to inspect plugin messages
- Check server logs for API errors

## Security Notes

- Never commit `.env` files with real credentials
- JWT tokens are short-lived (5 minutes) for security
- Validate all plugin communications
- Use HTTPS in production environments

## Support

For issues with:
- **Sigma Platform**: Contact Sigma support
- **Plugin Development**: Refer to Sigma plugin documentation
- **This Host Application**: Check the issues in this repository