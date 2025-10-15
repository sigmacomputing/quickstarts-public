# Sigma Dashboard Builder - Multi-Area KPI Placement System
A sample host application for Sigma's Dashboard Builder plugin that enables users to place different KPIs across three independent dashboard areas with persistent bookmark management.

Please refer to the QuickStart: Use Case: Dashboard Builder Plugin for instructions. Sigma QuickStarts can be found at:
https://quickstarts.sigmacomputing.com/

## Key Features
- Multi-Area KPI Placement: Place different KPIs in 3 independent dashboard areas
- Persistent Bookmarks: Save and restore complete multi-area configurations  
- Incremental Building: Add KPIs to existing bookmarks without losing current state
- Cross-Contamination Prevention: Each area operates independently
- Real-time Synchronization: ExploreKey sync across all areas
- Secure Authentication: JWT-based authentication with automatic token refresh

## Architecture

### Dual Storage System
- Sigma Bookmarks: Store exploreKey and workbook state (single-state, cloud)
- LowDB Database: Store multi-area configurations (multi-state, local)  
- Combined: Complete bookmark restoration across all dashboard areas

This project provides host application examples for Sigma plugins, demonstrating advanced multi-area plugin integration and persistent state management.

## Project Structure
plugin_use_cases/
├── .env                   # Configuration file (copy from .env.example)
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


## Dashboard Builder Plugin Host
The Dashboard Builder host application demonstrates:

- Plugin Integration: Embedding a Sigma plugin in a host application
- Bidirectional Communication: Messages between host and plugin
- Element Selection: UI for selecting dashboard elements
- JWT Authentication: Secure embedding with proper tokens

### Plugin Communication
The host application communicates with the plugin via `postMessage`:

Messages sent to plugin:
- `CONFIGURE`: Initial plugin configuration
- `ADD_ELEMENTS`: Selected elements to add to dashboard

Messages received from plugin:
- `PLUGIN_READY`: Plugin has loaded and is ready
- `ELEMENT_SELECTED`: User selected an element in the plugin
- `DASHBOARD_UPDATED`: Dashboard configuration changed