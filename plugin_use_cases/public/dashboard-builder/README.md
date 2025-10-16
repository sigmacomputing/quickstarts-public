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

### Dual Storage System
- Sigma Bookmarks: Store exploreKey and workbook state (single-state, cloud)
- LowDB Database: Store multi-area configurations (multi-state, local)  
- Combined: Complete bookmark restoration across all dashboard areas

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


## ARCHITECTURE COMPONENTS
1: Core Files & Responsibilities

  | File                                 | Lines  | Purpose                                                         |
  |--------------------------------------|--------|-----------------------------------------------------------------|
  | /public/dashboard-builder/index.html | 1,500+ | Main orchestrator with plugin hosting, state management, and UI |
  | /helpers/multi-area-bookmarks.js     | 181    | LowDB database operations and CRUD functions                    |
  | /routes/api/multi-area-bookmarks.js  | 230    | RESTful API endpoints for bookmark management                   |
  | /server/server.js                    | 79     | Express server with API routing and static serving              |
  | /data/multi-area-bookmarks.json      | Auto   | Persistent LowDB database file                                  |

 2: API Endpoints

  Multi-Area Bookmark Management:
  • POST   /api/multi-area-bookmarks/save           - Create new bookmark
  • GET    /api/multi-area-bookmarks/list           - List workbook bookmarks
  • GET    /api/multi-area-bookmarks/get/:id        - Get specific bookmark
  • DELETE /api/multi-area-bookmarks/delete/:id     - Delete bookmark
  • GET    /api/multi-area-bookmarks/stats          - Database statistics

  JWT & Legacy:
  • POST   /api/jwt/view?bookmarkId                 - Generate embed URLs
  • POST   /api/bookmarks/create-bookmark           - Create Sigma bookmarks

  
## OPERATIONAL WORKFLOWS
  1: Save Bookmark Process

  1. Capture State: Host reads all area node IDs (viz1_nodeid, viz2_nodeid, viz3_nodeid)
  2. Create Sigma Bookmark: Store exploreKey and workbook state in Sigma Cloud
  3. Store Local Config: Save multi-area configuration in LowDB with Sigma bookmark link
  4. Update UI: Refresh bookmark dropdown and set selection to new bookmark

  2: Load Bookmark Process

  1. Fetch Configuration: Load multi-area config from LowDB by local bookmark ID
  2. Load Workbook: Reload iframe with linked Sigma bookmark (gets exploreKey)
  3. Restore Areas: Generate URLs for all configured areas and update controls atomically
  4. Sync State: Update local tracking variables and prevent contamination

  3: Delete Bookmark Process

  1. Remove Local: Delete multi-area configuration from LowDB
  2. Preserve History: Keep Sigma bookmark for exploreKey history
  3. Reset UI: Update dropdown and reload if current bookmark was deleted

  ## SYSTEM FLOW DIAGRAMS

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                           DASHBOARD BUILDER SYSTEM                              │
  │                          Multi-Area KPI Placement                               │
  └─────────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                              COMPONENT OVERVIEW                                 │
  └─────────────────────────────────────────────────────────────────────────────────┘

      ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
      │   AREA 1        │    │   AREA 2        │    │   AREA 3        │
      │                 │    │                 │    │                 │
      │ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
      │ │ Sigma Plugin│ │    │ │ Sigma Plugin│ │    │ │ Sigma Plugin│ │
      │ │  (iframe)   │ │    │ │  (iframe)   │ │    │ │  (iframe)   │ │
      │ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
      │                 │    │                 │    │                 │
      │ Controls:       │    │ Controls:       │    │ Controls:       │
      │ • viz1_url      │    │ • viz2_url      │    │ • viz3_url      │
      │ • viz1_nodeid   │    │ • viz2_nodeid   │    │ • viz3_nodeid   │
      └─────────────────┘    └─────────────────┘    └─────────────────┘
               │                        │                        │
               └────────────────────────┼────────────────────────┘
                                        │
               ┌────────────────────────▼────────────────────────┐
               │             HOST APPLICATION                    │
               │            (index.html)                        │
               │                                                │
               │  ┌─────────────────────────────────────────┐   │
               │  │        MESSAGE ROUTING SYSTEM           │   │
               │  │                                         │   │
               │  │ • exploreKey synchronization            │   │
               │  │ • Node selection handling               │   │
               │  │ • Variable update distribution          │   │
               │  │ • Cross-contamination prevention        │   │
               │  └─────────────────────────────────────────┘   │
               │                                                │
               │  ┌─────────────────────────────────────────┐   │
               │  │       BOOKMARK ORCHESTRATION            │   │
               │  │                                         │   │
               │  │ • Multi-area state capture              │   │
               │  │ • Dual storage coordination             │   │
               │  │ • Atomic restoration management         │   │
               │  └─────────────────────────────────────────┘   │
               └────────────────────────┬───────────────────────┘
                                        │
               ┌────────────────────────▼────────────────────────┐
               │              API LAYER                          │
               │         (Express.js Routes)                     │
               │                                                 │
               │  /api/multi-area-bookmarks/*                    │
               │  /api/jwt/view                                  │
               │  /api/bookmarks/* (legacy)                      │
               └────────────────────────┬────────────────────────┘
                                        │
               ┌────────────────────────▼────────────────────────┐
               │             DUAL STORAGE SYSTEM                 │
               └─────────────────────────────────────────────────┘
                        │                        │
               ┌────────▼──────────┐    ┌────────▼──────────┐
               │   SIGMA CLOUD     │    │   LOCAL LOWDB     │
               │   (Remote API)    │    │   (JSON File)     │
               │                   │    │                   │
               │ • exploreKey      │    │ • viz1_nodeid     │
               │ • bookmark name   │    │ • viz2_nodeid     │
               │ • workbook state  │    │ • viz3_nodeid     │
               │ • creation date   │    │ • local metadata  │
               │                   │    │                   │
               │ ✓ Cloud storage   │    │ ✓ Multi-area      │
               │ ✓ API integrated  │    │ ✓ Independent     │
               │ ✗ Single-state    │    │ ✓ Fast access     │
               └───────────────────┘    └───────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                                SAVE WORKFLOW                                    │
  └─────────────────────────────────────────────────────────────────────────────────┘

  USER ACTION: Save Bookmark
        │
        ▼
  [1] CAPTURE CURRENT STATE
        │
        ├─► Read viz1_nodeid control
        ├─► Read viz2_nodeid control
        ├─► Read viz3_nodeid control
        └─► Get current exploreKey
        │
        ▼
  [2] CREATE SIGMA BOOKMARK
        │
        ├─► POST /api/bookmarks/create-bookmark
        ├─► Payload: { exploreKey, name, workbookUrlId }
        └─► Returns: sigmaBookmarkId
        │
        ▼
  [3] STORE MULTI-AREA CONFIG
        │
        ├─► POST /api/multi-area-bookmarks/save
        ├─► Payload: {
        │     name, sigmaBookmarkId, workbookUrlId,
        │     areas: { viz1_nodeid, viz2_nodeid, viz3_nodeid }
        │   }
        └─► Returns: localBookmarkId
        │
        ▼
  [4] UPDATE UI
        │
        ├─► Reload bookmark dropdown
        ├─► Set dropdown to new bookmark
        └─► Show success message

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                                LOAD WORKFLOW                                    │
  └─────────────────────────────────────────────────────────────────────────────────┘

  USER ACTION: Select Bookmark
        │
        ▼
  [1] FETCH BOOKMARK DATA
        │
        ├─► GET /api/multi-area-bookmarks/get/:localBookmarkId
        └─► Returns: { sigmaBookmarkId, areas: {...} }
        │
        ▼
  [2] RELOAD WORKBOOK
        │
        ├─► Generate JWT with sigmaBookmarkId
        ├─► Reload iframe with bookmark URL
        └─► Wait for workbook load
        │
        ▼
  [3] RESTORE ALL AREAS (Atomic)
        │
        ├─► For each area with nodeId:
        │   ├─► Generate embed URL with current exploreKey
        │   ├─► Prepare variable update
        │   └─► Add to batch update
        │
        ├─► Send single message with all updates:
        │   └─► { viz1_url, viz1_nodeid, viz2_url, viz2_nodeid, ... }
        │
        └─► Update local tracking variables

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                              MESSAGE FLOW                                       │
  └─────────────────────────────────────────────────────────────────────────────────┘

  PLUGIN TO HOST:
  ┌─────────────────┐         ┌─────────────────────────────────┐
  │ Sigma Plugin    │────────▶│ Host Application                │
  │ (iframe)        │         │                                 │
  └─────────────────┘         │ Message Types:                  │
                              │ • workbook:exploreKey:onchange  │
                              │ • workbook:variables:onchange   │
                              │ • workbook:id:onchange          │
                              │ • workbook:bookmark:onchange    │
                              └─────────────────────────────────┘

  HOST TO PLUGIN:
  ┌─────────────────────────────────┐         ┌─────────────────┐
  │ Host Application                │────────▶│ Sigma Plugin    │
  │                                 │         │ (iframe)        │
  │ Message Types:                  │         └─────────────────┘
  │ • workbook:variables:update     │
  │ • workbook:variables:get        │
  └─────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                            ERROR HANDLING FLOW                                  │
  └─────────────────────────────────────────────────────────────────────────────────┘

  ERROR SOURCES:
  ├─► API Failures (Network, Server Errors)
  ├─► Database Issues (LowDB Access, Corruption)
  ├─► JWT Expiration/Generation Failures
  ├─► Plugin Communication Failures
  └─► Invalid User Input/Missing Data

  ERROR HANDLING:
  ├─► Try-Catch Blocks with Detailed Logging
  ├─► User-Friendly Error Messages
  ├─► Graceful Degradation (Continue with Available Features)
  ├─► Automatic Retry for Transient Failures
  └─► Fallback to Original Workbook on Critical Failures

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                           SECURITY & PERFORMANCE                                │
  └─────────────────────────────────────────────────────────────────────────────────┘

  SECURITY:
  ├─► JWT Token Expiration (5 minutes)
  ├─► Input Validation on All API Endpoints
  ├─► No Sensitive Data in Client Logs
  └─► Secure HTTP Headers and CORS

  PERFORMANCE:
  ├─► Lazy Database Initialization
  ├─► JWT Caching for Same ExploreKey
  ├─► Atomic Variable Updates (Single Message)
  ├─► Efficient Message Filtering
  └─► Background Database Operations

  ┌─────────────────────────────────────────────────────────────────────────────────┐
  │                              DATA STRUCTURES                                    │
  └─────────────────────────────────────────────────────────────────────────────────┘

  LOWDB BOOKMARK STRUCTURE:
  {
    "id": "uuid-local-bookmark-id",
    "name": "User-Friendly Name",
    "sigmaBookmarkId": "sigma-cloud-bookmark-id",
    "workbookUrlId": "workbook-identifier",
    "areas": {
      "viz1_nodeid": "NDqnIvkXP2" | null,
      "viz2_nodeid": "4Mv2YcqPSJ" | null,
      "viz3_nodeid": "-j-GzZaxjj" | null
    },
    "created": "2025-10-15T14:31:52.604Z",
    "updated": "2025-10-15T14:31:52.604Z"
  }

  RUNTIME STATE TRACKING:
  - currentExploreKey: Active exploreKey for JWT generation
  - areaNodeIdMap: { "viz1_nodeid": "nodeId", ... }
  - availableBookmarks: Array of bookmark objects for dropdown
  - currentBookmarkId: Currently loaded bookmark ID