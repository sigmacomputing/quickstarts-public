# API Workbook Carousel QuickStart

## Overview
This QuickStart demonstrates an interactive workbook selection experience using a simple, stable carousel interface. Users can visually browse through available workbooks using thumbnail images and smooth navigation, providing an engaging way to discover and select embedded content.

## Features
- Simple Carousel Navigation: Clean horizontal slider with previous/next buttons
- User-Specific Content: Dynamic filtering showing only workbooks accessible to the selected user
- Thumbnail Support: Visual workbook previews with stable image display
- Instant Visual Feedback: Loading indicators and selected state animations
- Stable Performance: Custom implementation designed for reliability during all interactions

## Key Technical Design: User-Specific Workbook Filtering

### API Architecture
This carousel implements user-specific content filtering using Sigma's member-based API approach:

// Uses member-specific API endpoint
const res = await fetch("/api/workbook-copy-create/all-workbooks");

### How Filtering Works
1. Member ID Resolution: Resolves the selected embed user's member ID
2. Permission-Based Filtering: Calls `/members/{memberId}/files` to get user-accessible content
3. Shows only workbooks the selected user can actually access
4. Cross-Workspace Access: Not limited to specific workspace folders

- Best Practice: Production embed apps should use workspace organization for better content governance

### API Endpoints Used
- `GET /api/workbook-copy-create/all-workbooks` - User-specific workbook filtering
- `POST /api/jwt/{currentMode}` - Dynamic JWT generation based on user type
- `GET /env.json` - Environment configuration and user account types

## File Structure
api-embed-carousel/
├── index.html          # Main carousel interface
└── README.md           # This documentation

## Thumbnail Configuration
1. Location: Place images in `/public/assets/workbook-thumbnails/`
2. Naming: Use exact workbook names as filenames (e.g., `Sales Dashboard.png`)
3. Format: PNG format recommended, 240x140px optimal size
4. Fallback: Missing thumbnails show "Missing Thumbnail" placeholder


## Technical Implementation

### Custom Carousel Implementation
- Simple HTML structure with CSS transforms for smooth sliding
- Previous/next button navigation with keyboard support
- Fixed positioning to avoid layout conflicts
- Stable image display without DOM manipulation during interactions

### User State Management
- Mode Switching: Automatic carousel reset when changing users
- Loading States: Immediate visual feedback with spinner and workbook name
- Selection Memory: Maintains selected workbook display after carousel closes
- Stable Navigation: Simple slide tracking without complex state management

### JWT Generation
- Dynamic Modes: View users get `["view"]`, Build users get `["build"]` permissions
- Real-time Generation: JWT created on workbook selection with user-specific claims
- Debug Display: Decoded JWT payload visible in sidebar for learning