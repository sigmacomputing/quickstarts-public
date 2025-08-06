# API Host Filter Sync QuickStart

## Overview
This QuickStart demonstrates bidirectional filter synchronization between a host application and Sigma embeds. It creates Store Region and Date Range filters in the host application that sync with variables in the embedded Sigma workbook, providing seamless user experience where filter changes immediately update embedded content.

## Features
- Custom Multiselect Control: Store Region dropdown with checkbox interface and predefined values
- jQuery Date Range Picker: Professional date picker with predefined ranges (Today, Last 7 Days, etc.)
- Bidirectional Sync: Host filters populated from Sigma variables and update Sigma when changed
- Real-time Updates: Filter changes immediately update the embedded workbook data
- Loading Indicators: Visual feedback during filter updates using centralized CSS
- Duplicate Prevention: Optimized performance prevents redundant API calls

## Technical Implementation

### Core Technologies
- PostMessage API: Bidirectional communication with Sigma embed
- jQuery DateRangePicker: Professional date range selection with predefined options
- Custom Multiselect: Dropdown with checkbox interface for region selection
- Variable Management: Automatically discovers and syncs with Sigma variables
- Loading States: Centralized loading indicators from main.css
- JWT Generation: Uses `/api/jwt/workbook` endpoint
- Environment Config: Loads configuration from `/env.json`

### Sigma Events Integration
- Variable Discovery: Requests variables and processes `workbook:variables:current` events
- Filter Updates: Sends `workbook:variables:update` events with new filter values
- Event Origin Validation: Ensures postMessage events come from Sigma domains
- Performance Optimization: Duplicate prevention and debounced updates

## File Structure
api-embed-filters/
├── index.html          # Main page with host filter sync implementation
└── README.md           # This documentation

## API Endpoints Used
- `GET /api/workbooks` - Fetches available workbooks
- `POST /api/jwt/workbook` - Generates JWT token for embedding

## Key Code Implementations

### Store Region Multiselect Filter
// STORE REGION FILTER FUNCTIONS (lines 580-830)
- populateStoreRegionFilter() - Creates custom multiselect with checkboxes
- updateSigmaVariable() - Sends region updates to Sigma with duplicate prevention
- findStoreRegionVariable() - Auto-discovers Store-Region control in workbook

// HTML Structure
<div class="custom-multiselect" id="storeRegionSelect">
  <div class="multiselect-display">All Regions</div>
  <div class="multiselect-dropdown">
    <!-- Checkbox options populated dynamically -->
  </div>
</div>

### Date Range Filter with jQuery DateRangePicker
// DATE RANGE FILTER FUNCTIONS (lines 1190-1320)
- initializeDateRangeFilter() - Initializes jQuery daterangepicker with predefined ranges
- updateDateRangeFilter() - Sends date range updates to Sigma in correct min/max format

// Configuration Features
- linkedCalendars: false - Allows same-month date selection (e.g., Jan 1-3)
- showDropdowns: true - Year/month dropdowns for easy navigation
- UTC timezone handling - Formats dates with 'Z' suffix for Sigma compatibility
- Dynamic relative ranges that automatically adjust to current year

// Predefined Ranges Configuration
ranges: {
  'Today': [moment(), moment()],
  'Yesterday': [moment().subtract(1, 'days'), moment().subtract(1, 'days')],
  'Last 7 Days': [moment().subtract(6, 'days'), moment()],
  'Last 30 Days': [moment().subtract(29, 'days'), moment()],
  'This Month': [moment().startOf('month'), moment().endOf('month')],
  'Last Month': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')],
  'This Quarter': [moment().startOf('quarter'), moment().endOf('quarter')],
  'Last Quarter': [moment().subtract(1, 'quarter').startOf('quarter'), moment().subtract(1, 'quarter').endOf('quarter')],
  'This Year': [moment().startOf('year'), moment().endOf('year')],
  'Last Year': [moment().subtract(1, 'year').startOf('year'), moment().subtract(1, 'year').endOf('year')]
}

### Variable Synchronization
// SIGMA EMBED EVENT HANDLING (lines 320-400)
- window.addEventListener("message", ...) - Listens for workbook:variables:current and workbook:variables:onchange
- handleVariablesList() - Processes variable responses and populates filters
- requestVariablesList() - Requests current variable states from Sigma

// Message Format for Variable Updates
{
  type: "workbook:variables:update",
  variables: {
    "Store-Region": "West,South,East",  // Comma-separated regions
    "Date-Filter": "min:2025-01-01T00:00:00Z,max:2025-01-31T23:59:59Z"  // Date range with min/max and UTC timezone
  }
}

### Debug Information
Enable debugging by setting `DEBUG = true` in the console or checking browser developer tools for:
// Date range debugging output
=== DATE RANGE DEBUG ===
Original picker dates: 2024-01-01T00:00:00-08:00 to 2024-01-31T23:59:59-08:00
Display format: 2024-01-01 to 2024-01-31
Sigma format: 2024-01-01T00:00:00Z to 2024-01-31T23:59:59Z
Sending date range update: Date-Filter = min:2024-01-01T00:00:00Z,max:2024-01-31T23:59:59Z

### Date Format Requirements
Sigma expects date ranges in this exact format:
- Single dates: `2024-05-01T08:00:00Z` (ISO 8601 with UTC timezone)
- Date ranges: `min:2024-01-01T00:00:00Z,max:2024-01-31T23:59:59Z`
- UTC timezone: Always append 'Z' suffix for proper timezone handling
- Range bounds: Use `min:`/`max:` prefixes, not `start:`/`end:`

### Alternative: Sigma Relative Date Format
Note: This implementation uses absolute ISO 8601 dates, but Sigma also supports relative date formats like:
- `prior-month-3` (3 months ago)
- `prior-day-7` (7 days ago)  
- `prior-year-1` (1 year ago)

These relative formats automatically adjust and might be more elegant for certain use cases, but this demo uses absolute dates for explicit control and debugging clarity.