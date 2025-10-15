# Sigma Dashboard Builder Plugin Host

A complete host application for Sigma's Dashboard Builder plugin that enables dynamic KPI selection and placement in dashboard areas without modifying the original plugin code.

## Overview

This application demonstrates how to build a host for Sigma plugins that enables users to:
- Put a workbook in edit mode
- Click edit buttons under dashboard areas  
- Select KPIs from Sigma's Library modal
- Dynamically place selected KPIs into dashboard areas using Sigma's official APIs

## Features

- **Multi-Area Support**: Supports up to 3 dashboard areas with independent KPI placement
- **Dynamic KPI Placement**: Any KPI can be placed in any dashboard area
- **Bookmark Persistence**: Save and restore custom dashboard configurations using Sigma bookmarks
- **No Plugin Modifications**: Uses original plugin without changes
- **Official Sigma APIs**: Leverages Sigma's inbound event API (`workbook:variables:update`)
- **JWT Authentication**: Secure embedding with team provisioning
- **Production Ready**: Error handling, debugging, responsive design

## Architecture

### Dynamic Workflow
```
1. Edit Button Clicked → Sets Context (vizUrlControl = "viz1_url")
2. User Selects KPI → Outbound Event: {vizEmbedUrlControl: "viz1_url"}  
3. Host Generates URL → Element embed URL + JWT authentication
4. Host Updates Control → workbook:variables:update inbound event
5. Plugin Renders KPI → Automatically detects control change
```

### Control Architecture
**Hidden Controls in Sigma Workbook:**
- `vizUrlControl` - Context switcher (which area is being updated)
- `viz1_url`, `viz2_url`, `viz3_url` - Dashboard area URLs
- `viz1_nodeid`, `viz2_nodeid`, `viz3_nodeid` - Element node IDs for tracking
- `explorekey` - Single explore key control for bookmark persistence

### Key Implementation Details

**Host Application Functions:**
- `handleVizComponentSelected()` - Processes KPI selection and generates embed URLs
- `generateKpiEmbedUrl()` - Creates authenticated element embed URLs  
- `handleBookmarkChange()` - Manages bookmark save/load operations
- `triggerPluginRefresh()` - Implements area cycling for multi-area bookmark restoration
- `storeNodeId()` / `getStoredNodeId()` - Node ID mapping for proper area tracking
- `postMessage()` with `workbook:variables:update` - Updates Sigma controls

**Sigma Workbook Configuration:**
- Edit buttons trigger actions that set `vizUrlControl` to target area
- KPI selection triggers outbound event `vizComponentSelected` with context
- Plugin automatically re-renders when control values change

## Setup

### Prerequisites
- Node.js 14+
- Sigma organization with plugin capabilities  
- Dashboard Builder plugin registered in Sigma
- Sigma workbook with properly configured controls and actions

### Environment Configuration
Create `.env` file in `/plugin_use_cases/`:
```env
# Sigma API Configuration
CLIENT_ID=your_client_id
SECRET=your_secret
ORG_SLUG=your_org_slug
EMBED_URL_BASE=https://app.sigmacomputing.com

# User Configuration
VIEW_EMAIL=view.plugin.user@example.com
VIEW_TEAMS=Embed_Users

# Workbook Configuration  
WORKBOOK_NAME=Custom_Dashboard
WORKSPACE_NAME=Embed_Users

# Debug Settings
DEBUG=true
```

### Installation
```bash
# From the plugin_use_cases directory
npm install

# Start the server  
npm start

# Navigate to dashboard builder
http://localhost:3000/dashboard-builder/
```

## Sigma Workbook Setup

### Required Hidden Controls
Create these controls in your Sigma workbook:

1. **Context Control**
   - Control ID: `vizUrlControl`
   - Label: "URL Control" 
   - Type: Text
   - Default: Empty

2. **Area 1 Controls**
   - Control ID: `viz1_url` | Label: "Area 1 URL" | Type: Text
   - Control ID: `viz1_nodeid` | Label: "Area 1 Node ID" | Type: Text

3. **Area 2 Controls**
   - Control ID: `viz2_url` | Label: "Area 2 URL" | Type: Text  
   - Control ID: `viz2_nodeid` | Label: "Area 2 Node ID" | Type: Text

4. **Area 3 Controls**
   - Control ID: `viz3_url` | Label: "Area 3 URL" | Type: Text
   - Control ID: `viz3_nodeid` | Label: "Area 3 Node ID" | Type: Text

5. **Bookmark Control**
   - Control ID: `explorekey` | Label: "Explore Key" | Type: Text

### Edit Button Configuration
For each dashboard area's Edit button:

1. **Add Action**: Update Control Value
   - Control: `vizUrlControl`
   - Value: `viz1_url` (or appropriate area identifier)

2. **Add Action**: Open Library Modal
   - Enable KPI selection interface

### KPI Action Configuration
For each KPI in the Library modal:

1. **Add Action**: Generate Iframe Event
   - Event Name: `vizComponentSelected` 
   - Data: `{"vizEmbedUrlControl": "[vizUrlControl]", "nodeId": "ELEMENT_NODE_ID"}`

## Host Implementation

### Core Functions

#### handleVizComponentSelected(values)
```javascript
/**
 * Handles KPI selection from Sigma modal
 * @param {Object} values - Contains vizEmbedUrlControl and nodeId
 */
async function handleVizComponentSelected(values) {
    const targetControl = values.vizEmbedUrlControl;
    const selectedKpiNodeId = values.nodeId;
    
    // Generate authenticated embed URL for selected KPI
    const embedUrl = await generateKpiEmbedUrl(selectedKpiNodeId);
    
    // Update Sigma control using inbound event API
    const iframe = document.getElementById("sigma-embed");
    if (iframe && iframe.contentWindow) {
        const variablesUpdate = {};
        variablesUpdate[targetControl] = embedUrl;
        
        iframe.contentWindow.postMessage({
            type: "workbook:variables:update",
            variables: variablesUpdate
        }, "*");
    }
}
```

#### generateKpiEmbedUrl(nodeId)
```javascript
/**
 * Generates authenticated embed URL for KPI element
 * @param {string} nodeId - Sigma element node ID
 * @returns {Promise<string>} - Complete embed URL with JWT
 */
async function generateKpiEmbedUrl(nodeId) {
    const response = await fetch(`/api/jwt/view?embedType=element&nodeId=${nodeId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sub: 'view' })
    });
    
    const { embedUrl } = await response.json();
    return embedUrl;
}
```

### Message Handling
```javascript
// Listen for outbound events from Sigma workbook
window.addEventListener("message", (event) => {
    if (event.data.type === "vizComponentSelected") {
        handleVizComponentSelected(event.data.values);
    }
});
```

## Technical Implementation

### JWT Generation
The host application generates JWTs for element embedding:

```javascript
// Element-specific embed URL generation
if (embedType === "element" && nodeId) {
    const baseUrl = process.env.EMBED_URL_BASE;
    embedUrl = `${baseUrl}/${process.env.ORG_SLUG}/workbook/${workbook.name}-${workbook.urlId}/element/${nodeId}?:embed=true`;
}

// Add JWT authentication
const finalEmbedUrl = `${embedUrl}?:jwt=${jwt}`;
```

### Control Updates
Uses Sigma's official inbound event API:

```javascript
iframe.contentWindow.postMessage({
    type: "workbook:variables:update", 
    variables: {
        "viz1_url": "https://app.sigmacomputing.com/org/workbook/element/abc123?:jwt=..."
    }
}, "*");
```

### Plugin Integration
The Dashboard Builder plugin automatically:
- Monitors control changes via `variableService.getVariable()`
- Re-renders when `vizUrlControlValue` changes
- Extracts node IDs from URLs for internal tracking
- Registers iframe message listeners for explore key updates

## Bookmark Persistence

### How Bookmarks Work
The dashboard builder supports saving and restoring custom dashboard configurations using Sigma's bookmark system:

1. **KPI Placement**: Place KPIs in any of the 3 dashboard areas
2. **Bookmark Save**: Use Sigma's bookmark feature to save the current state
3. **Bookmark Load**: Restore saved configurations with proper area cycling

### Technical Implementation

#### Area Cycling for Multi-Area Restoration
```javascript
/**
 * Handles bookmark loading with multi-area support
 * Cycles through areas to ensure all KPIs render properly
 */
async function triggerPluginRefresh() {
    const iframe = document.getElementById("sigma-embed");
    if (iframe && iframe.contentWindow) {
        // Reconstruct URLs for all areas
        await reconstructAreaUrl("viz1_url");
        await reconstructAreaUrl("viz2_url"); 
        await reconstructAreaUrl("viz3_url");
        
        // Cycle through areas with delays to force re-subscription
        const areasWithContent = getAreasWithContent();
        let delay = 0;
        
        areasWithContent.forEach((area, index) => {
            setTimeout(() => {
                iframe.contentWindow.postMessage({
                    type: "workbook:variables:update",
                    variables: { "vizUrlControl": area }
                }, "*");
            }, delay);
            delay += 300; // 300ms between each area
        });
    }
}
```

#### Node ID Mapping
```javascript
/**
 * Stores and retrieves node IDs for proper area tracking
 * Prevents KPIs from loading in wrong areas after bookmark restoration
 */
function storeNodeId(nodeIdControl, nodeId) {
    areaNodeIdMap[nodeIdControl] = nodeId;
    if (DEBUG) console.log(`Stored node ID: ${nodeIdControl} → ${nodeId}`);
}

function getStoredNodeId(nodeIdControl) {
    return areaNodeIdMap[nodeIdControl] || null;
}
```

### Bookmark Workflow
1. **Configure KPIs**: Place KPIs in dashboard areas using the edit buttons
2. **Save Bookmark**: Use Sigma's bookmark icon to save current configuration  
3. **Load Bookmark**: Select saved bookmark from Sigma's bookmark dropdown
4. **Area Cycling**: Host automatically cycles through areas to restore all KPIs

## Multi-Area Configuration

### All Three Areas Pre-Configured
The host application supports all 3 dashboard areas out of the box:

1. **Area 1**: Uses `viz1_url` and `viz1_nodeid` controls
2. **Area 2**: Uses `viz2_url` and `viz2_nodeid` controls  
3. **Area 3**: Uses `viz3_url` and `viz3_nodeid` controls

### Edit Button Configuration
For each dashboard area's Edit button:

- **Area 1 Edit**: Set `vizUrlControl = "viz1_url"`
- **Area 2 Edit**: Set `vizUrlControl = "viz2_url"`
- **Area 3 Edit**: Set `vizUrlControl = "viz3_url"`

### Dynamic Workflow
The same `vizComponentSelected` event works for all areas automatically based on the current `vizUrlControl` context.

## Troubleshooting

### Plugin Won't Load
- Verify workbook name matches `WORKBOOK_NAME` in `.env`
- Check that user has access to the workbook  
- Ensure plugin is registered with the workbook
- Review JWT configuration in browser developer tools

### KPI Selection Not Working
- Check browser console for `vizComponentSelected` events
- Verify KPI actions are configured with correct event name
- Ensure `vizUrlControl` is set before KPI selection
- Test with `DEBUG=true` for verbose logging

### Bookmark Loading Issues
- Verify `explorekey` control exists in workbook
- Check that node ID mapping is preserved during bookmark save
- Ensure area cycling completes before testing KPI rendering
- Look for "Plugin context set to" messages in console during area cycling

### Authentication Issues
- Validate Sigma API credentials in `.env`
- Check user email exists in Sigma organization
- Verify organization slug is correct
- Review JWT payload includes team information

### Control Update Failures
- Confirm control IDs match exactly (case-sensitive)
- Check iframe is loaded before sending postMessage
- Verify `workbook:variables:update` message format
- Test control updates manually in browser console

### Multi-Area Loading Problems
- Check that all area controls (`viz1_url`, `viz2_url`, `viz3_url`) exist
- Verify node ID controls (`viz1_nodeid`, `viz2_nodeid`, `viz3_nodeid`) are created
- Ensure area cycling delays (300ms) are sufficient for your workbook
- Test with single area first, then add additional areas

## Advanced Customization

### Custom KPI Sources
Extend the workflow to support KPIs from external sources:

```javascript
async function generateCustomKpiUrl(kpiConfig) {
    // Generate URL for custom KPI source
    return `https://your-kpi-service.com/embed/${kpiConfig.id}`;
}
```

### Enhanced Error Handling
Add robust error handling for production use:

```javascript
async function handleVizComponentSelected(values) {
    try {
        if (!values.vizEmbedUrlControl || !values.nodeId) {
            throw new Error("Missing required parameters");
        }
        
        const embedUrl = await generateKpiEmbedUrl(values.nodeId);
        // ... rest of implementation
        
    } catch (error) {
        console.error("KPI selection failed:", error);
        // Show user-friendly error message
    }
}
```

### Integration with Backend Systems
Save and restore dashboard configurations:

```javascript
async function saveDashboardState() {
    const currentState = {
        viz1_url: getCurrentControlValue('viz1_url'),
        viz2_url: getCurrentControlValue('viz2_url'),
        viz3_url: getCurrentControlValue('viz3_url')
    };
    
    await fetch('/api/dashboards', {
        method: 'POST',
        body: JSON.stringify(currentState)
    });
}
```

This host application provides a complete foundation for implementing dynamic dashboard builders with Sigma plugins while leveraging official APIs and maintaining compatibility with the original plugin code.