# Dashboard Builder - Technical Documentation

## Overview

The Dashboard Builder is a sophisticated host application for Sigma's Plugin framework that enables dynamic KPI placement across multiple dashboard areas with persistent bookmark management. It implements a comprehensive system for managing exploreKey synchronization, bookmark persistence, and multi-area KPI restoration.

## Architecture

### Core Components

1. **Host Application** (`index.html`) - Main orchestrator containing all logic
2. **Plugin Integration** - Embeds Sigma's Dashboard Builder plugin in 3 areas
3. **API Layer** - Node.js Express routes for bookmark management
4. **JWT Authentication** - Secure embed URL generation with exploreKey matching

### Plugin Configuration

Each area has its own plugin instance with dedicated controls:
- **Area 1**: `viz1_url`, `viz1_nodeid`, `viz1_explorekey`
- **Area 2**: `viz2_url`, `viz2_nodeid`, `viz2_explorekey`  
- **Area 3**: `viz3_url`, `viz3_nodeid`, `viz3_explorekey`

### Common Explore Key Pattern

Uses a unified `explorekey` control that stores the most recent exploreKey for bookmark persistence, following Sigma's single-exploreKey-per-bookmark architecture.

## Key Features

### 1. Dynamic KPI Placement
- Users can place different KPIs in any of the 3 dashboard areas
- Each area maintains independent state with its own controls
- Real-time switching between areas during configuration

### 2. Bookmark Management
- **Save**: Creates bookmarks with API integration using stabilized exploreKeys
- **Load**: Restores all KPIs across areas using atomic restoration process
- **Delete**: Individual bookmark deletion with API cleanup
- **Update**: Automatic bookmark updates with successful restoration exploreKeys

### 3. ExploreKey Synchronization
- **Common Explore Key Approach**: Single source of truth for bookmark exploreKeys
- **Stabilization Process**: Waits for exploreKey changes to stabilize before bookmark operations
- **JWT Matching**: Ensures embed URLs have matching JWTs for current exploreKeys
- **URL Regeneration**: Automatic refresh with stabilized exploreKeys during restoration

## Technical Implementation

### Bookmark Save Process

```javascript
async function saveBookmark() {
  // 1. Set protection flag to prevent feedback loops
  isInSaveProcess = true;
  
  // 2. Clear unused area controls to prevent stale KPI restoration
  await clearUnusedAreaControls();
  
  // 3. Wait for area restoration and exploreKey stabilization (2s)
  await new Promise(resolve => setTimeout(resolve, 2000));
  
  // 4. Get final stabilized exploreKey
  const finalExploreKey = await getCurrentAreaExploreKey();
  
  // 5. Save bookmark with correct exploreKey via API
  const response = await fetch("/api/bookmarks/create-bookmark", {
    method: "POST",
    body: JSON.stringify({
      userEmail: env.VIEW_EMAIL,
      workbookUrlId: workbookUrlId,
      exploreKey: finalExploreKey,
      name: bookmarkName
    })
  });
  
  // 6. Schedule post-save refresh to ensure KPI loads
  setTimeout(async () => {
    isInSaveProcess = false;
    await refreshCurrentAreaAfterSave();
  }, 5000);
}
```

### Bookmark Load Process

```javascript
async function loadSelectedBookmark(bookmarkId) {
  // 1. Reload workbook with bookmark
  await reloadWorkbook(bookmarkId);
  
  // 2. Wait for workbook to load, then restore KPIs
  setTimeout(async () => {
    await attemptDirectKPIRestoration();
  }, 2000);
}

async function rebuildFromBookmarkControls() {
  // 1. Wait for node mapping to be rebuilt from controls
  await rebuildNodeMapping();
  
  // 2. Trigger atomic restoration process
  triggerPluginRefresh();
}
```

### Atomic Restoration Process

```javascript
async function triggerPluginRefresh() {
  // 1. Build URL updates for all areas with stored node IDs
  const allVariables = {};
  const areas = ["viz1_url", "viz2_url", "viz3_url"];
  
  for (const areaControl of areas) {
    const nodeId = getStoredNodeId(nodeIdControl);
    if (nodeId) {
      const embedUrl = await generateKpiEmbedUrl(nodeId);
      allVariables[areaControl] = embedUrl;
    }
  }
  
  // 2. Clear existing URLs first, then set new ones
  if (Object.keys(allVariables).length > 0) {
    // Clear phase
    iframe.contentWindow.postMessage({
      type: "workbook:variables:update",
      variables: clearVariables
    }, "*");
    
    // Set phase (after delay)
    setTimeout(() => {
      iframe.contentWindow.postMessage({
        type: "workbook:variables:update",
        variables: allVariables
      }, "*");
    }, 200);
  }
}
```

### ExploreKey Management

```javascript
async function handleExploreKeyChange(data) {
  // 1. Update tracking variable
  currentExploreKey = data.exploreKey;
  
  // 2. Update area-specific exploreKey control
  const exploreKeyControl = getExploreKeyControlForArea(currentAreaContext);
  const variablesUpdate = {};
  variablesUpdate[exploreKeyControl] = data.exploreKey;
  
  // 3. Update Common Explore Key (for bookmarks)
  variablesUpdate["explorekey"] = data.exploreKey;
  
  // 4. Send atomic update
  iframe.contentWindow.postMessage({
    type: "workbook:variables:update",
    variables: variablesUpdate
  }, "*");
  
  // 5. Trigger bookmark update (if appropriate)
  await updateBookmarkWithSuccessfulRestoration(data.exploreKey);
  
  // 6. Regenerate URLs for better performance (if not in save process)
  await regenerateUrlsWithCurrentExploreKey(data.exploreKey);
}
```

## Feedback Loop Prevention

### Save Process Protection
- `isInSaveProcess` flag prevents URL regeneration during bookmark save
- Extended cooldown periods prevent bookmark updates immediately after save
- Post-save refresh ensures KPI loads without triggering loops

### Timing Controls
- **Bookmark Update Cooldown**: 30 seconds after save
- **URL Regeneration Block**: 5 seconds during save process
- **Stabilization Wait**: 2 seconds for exploreKey stabilization

### Smart Regeneration
- Only regenerates URLs during actual restoration contexts
- Skips regeneration for areas without node IDs
- Uses current exploreKey for JWT matching

## API Integration

### Bookmark Routes

#### Create Bookmark
```javascript
POST /api/bookmarks/create-bookmark
{
  "userEmail": "view.plugin.user@example.com",
  "workbookUrlId": "2mQMgBnScoDR8e3KRA5R6l",
  "exploreKey": "f9709e3b-5aed-462a-9393-26950a04c14b",
  "name": "My Dashboard"
}
```

#### List Bookmarks
```javascript
GET /api/bookmarks/list?workbookUrlId=2mQMgBnScoDR8e3KRA5R6l
```

#### Update Bookmark
```javascript
PUT /api/bookmarks/update
{
  "workbookUrlId": "2mQMgBnScoDR8e3KRA5R6l",
  "bookmarkId": "792b7dce-20e7-4a6d-9ac1-23dc833dcc79",
  "exploreKey": "f9709e3b-5aed-462a-9393-26950a04c14b"
}
```

#### Delete Bookmark
```javascript
DELETE /api/bookmarks/delete
{
  "workbookUrlId": "2mQMgBnScoDR8e3KRA5R6l",
  "bookmarkId": "792b7dce-20e7-4a6d-9ac1-23dc833dcc79"
}
```

## Key Variables

### Global State
```javascript
let selectedKpiNodeId = null;      // Currently selected KPI node ID
let currentExploreKey = null;      // Current explore key for bookmark restoration
let workbookUrlId = null;          // Current workbook URL ID
let availableBookmarks = [];       // List of available bookmarks
let currentBookmarkId = null;      // Currently loaded bookmark ID
let lastSavedBookmark = null;      // Track last saved bookmark for updates
let currentAreaContext = null;     // Track current area context for URL regeneration
let isInSaveProcess = false;       // Flag to prevent URL regeneration during save
```

### Node Mapping
```javascript
let areaNodeIdMap = {};            // Maps area controls to node IDs
// Example: { "viz1_nodeid": "NDqnIvkXP2", "viz2_nodeid": "4Mv2YcqPSJ" }
```

## Control Mapping

### Area Controls
- `viz1_url` → KPI embed URL for Area 1
- `viz1_nodeid` → Node ID for Area 1  
- `viz1_explorekey` → ExploreKey for Area 1
- Similar pattern for `viz2_*` and `viz3_*`

### Special Controls
- `explorekey` → Common Explore Key (for bookmarks)
- `vizUrlControl` → Plugin's main URL control (set to empty during restoration)

## Message Flow

### Plugin → Host Messages
```javascript
// ExploreKey changes
{
  type: "workbook:exploreKey:onchange",
  exploreKey: "f9709e3b-5aed-462a-9393-26950a04c14b"
}

// Variable changes
{
  type: "workbook:variables:onchange",
  workbook: { variables: {...} }
}

// Node selection changes
{
  type: "workbook:id:onchange",
  nodeId: "NDqnIvkXP2",
  nodeType: "element"
}
```

### Host → Plugin Messages
```javascript
// Variable updates
{
  type: "workbook:variables:update",
  variables: {
    "viz1_url": "https://app.sigmacomputing.com/...",
    "viz1_explorekey": "f9709e3b-5aed-462a-9393-26950a04c14b"
  }
}

// Variable requests
{
  type: "workbook:variables:get",
  variables: ["viz1_nodeid", "viz2_nodeid", "viz3_nodeid"]
}
```

## Troubleshooting

### Common Issues

1. **"No areas to restore"** - Fixed by ensuring `rebuildNodeMapping()` completes before `triggerPluginRefresh()`
2. **ExploreKey mismatch loops** - Fixed with save process protection flags and cooldown periods
3. **KPI not loading after save** - Fixed with post-save URL refresh mechanism
4. **Bookmark dropdown reverting** - Fixed by preventing `loadBookmarks()` during bookmark switches

### Debug Logging

Set `DEBUG = true` for comprehensive logging:
- ExploreKey changes and synchronization
- Bookmark save/load operations
- URL regeneration processes
- Area restoration steps
- API calls and responses

## Performance Optimizations

1. **JWT Caching** - Reuses JWTs when exploreKey matches
2. **Atomic Updates** - Batches variable updates to prevent timing issues
3. **Smart Regeneration** - Only regenerates URLs when necessary
4. **Throttled API Calls** - 200ms delays between bulk operations

## Security Considerations

- JWT tokens have 5-minute expiration
- All API calls use proper authentication headers
- ExploreKey validation prevents unauthorized access
- No sensitive data stored in local variables

## Future Enhancements

1. **Enhanced Error Handling** - More robust error recovery mechanisms
2. **Performance Metrics** - Track restoration times and success rates
3. **Bulk Operations** - Batch bookmark operations for efficiency
4. **Area Templates** - Predefined KPI configurations for quick setup