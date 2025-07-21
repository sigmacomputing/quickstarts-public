# API Embed Controls QuickStart

## Overview
This QuickStart demonstrates Sigma's flexible embedding options, allowing you to embed different types of content (workbooks, pages, or elements) with various display configurations. It showcases how to dynamically control embed parameters and content types through a unified interface.

## Features

### Flexible Embed Types
- **Workbook**: Full workbook embedding with complete navigation
- **Page**: Single page embedding from a workbook
- **Element**: Individual visualization or control element embedding

### Dynamic Controls
- **User Selection**: Switch between View Users and Build Users
- **Workbook Selection**: Choose from available workbooks
- **Page Selection**: Select specific pages within workbooks (for page/element embeds)
- **Element Selection**: Choose individual elements on pages (for element embeds)
- **Real-time Updates**: Interface adapts based on selected embed type

### Embedding Configuration
- **Responsive Interface**: Controls appear/disappear based on embed type selection
- **Parameter Management**: Dynamic JWT generation with appropriate claims
- **Debug Information**: Toggle sidebar with embed URLs and JWT details

## How It Works

### Embed Type Workflow
1. **Select User & Workbook**: Choose user permissions and target workbook
2. **Choose Embed Type**: Select from workbook, page, or element embedding
3. **Configure Content** (if applicable):
   - For **Page Embed**: Select specific page from dropdown
   - For **Element Embed**: Select page, then choose specific element
4. **View Embedded Content**: Content updates automatically based on selections

### Dynamic Interface Behavior
- **Workbook Embed**: Shows user/workbook controls only
- **Page Embed**: Adds page selection dropdown
- **Element Embed**: Adds both page and element selection dropdowns
- **Cascading Dependencies**: Page selection updates element options

### Permission Levels
- **View Users**: Standard viewing permissions with restricted interface
- **Build Users**: Full editing capabilities and enhanced interface options

## Technical Implementation

### API Integration
- **Dynamic Endpoint**: Uses `/api/jwt/api-embed-controls` with flexible parameters
- **Content Discovery**: 
  - `/api/workbooks` - Lists available workbooks
  - `/api/pages` - Gets pages for selected workbook
  - `/api/elements` - Gets elements for selected page
- **JWT Adaptation**: Token claims adapt to embed type requirements

### Key Features
- **Cascading Dropdowns**: Page selection triggers element loading
- **State Management**: Maintains selection state across embed type changes
- **Error Handling**: Graceful fallbacks for missing content
- **Debug Integration**: Comprehensive logging in DEBUG mode

## File Structure
```
api-embed-controls/
├── index.html          # Main page with flexible embed controls
└── README.md           # This documentation
```

## API Endpoints Used
- `GET /api/workbooks` - Fetches available workbooks
- `GET /api/pages?workbookUrlId={id}` - Gets pages for specific workbook  
- `GET /api/elements?workbookUrlId={id}&pageUrlId={pageId}` - Gets elements for specific page
- `POST /api/jwt/api-embed-controls` - Generates JWT for specified embed type and content

## Embed Type Details

### Workbook Embedding
- **Use Case**: Full workbook access with navigation
- **Best For**: Complete analytics dashboards, multi-page reports
- **User Experience**: Users can navigate between pages and explore full content

### Page Embedding  
- **Use Case**: Single page focus without navigation
- **Best For**: Specific dashboard views, focused reporting
- **User Experience**: Clean, focused view of single page content

### Element Embedding
- **Use Case**: Individual charts, tables, or controls
- **Best For**: Micro-integrations, specific visualizations in external apps
- **User Experience**: Seamless integration of individual components

## Configuration

### Environment Setup
All standard Sigma embedding parameters apply:
- User permissions affect available interface options
- Theme and language settings carry through to embedded content
- Debug mode provides detailed logging of selection and JWT generation

### Customization Options
The interface demonstrates how to:
- Build dynamic embedding interfaces
- Handle different content types with single codebase
- Manage cascading dependencies between selections
- Provide appropriate user experiences for different embed types

## Getting Started

### Basic Exploration
1. Configure `.env` file with Sigma API credentials
2. Start server: `npm start`
3. Navigate to `/api-embed-controls`
4. Try different combinations:
   - Select workbook embed type and choose workbook
   - Switch to page embed and select specific page
   - Try element embed and choose individual components

### Advanced Testing
1. **Permission Testing**: Compare View User vs Build User experiences across embed types
2. **Content Testing**: Test with workbooks containing multiple pages and various element types
3. **Interface Testing**: Observe how controls adapt to embed type selections
4. **Debug Testing**: Enable DEBUG mode to see JWT generation and API calls

## Debug Information
Enable `DEBUG=true` for detailed logging:
- Embed type selection events
- Cascading dropdown population
- JWT generation with different parameters
- API calls for content discovery

## Use Cases

### Application Integration
- **Micro-dashboards**: Embed specific charts in external applications
- **Focused Reporting**: Show single pages without navigation complexity
- **Full Analytics**: Provide complete workbook access when needed

### User Experience Design
- **Progressive Disclosure**: Start with workbooks, drill down to elements
- **Context-Appropriate Embedding**: Match embed type to use case
- **Seamless Integration**: Elements blend naturally with host applications

## Important Notes
- **Content Dependencies**: Page and element embeds require valid parent content
- **Permission Inheritance**: Embedded content respects user permissions
- **Performance Considerations**: Element embeds typically load faster than full workbooks
- **Navigation Context**: Page/element embeds lose workbook navigation context

This QuickStart provides a foundation for building sophisticated embedding interfaces that adapt to different content types and user needs.