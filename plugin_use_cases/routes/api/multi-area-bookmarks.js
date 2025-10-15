/*
══════════════════════════════════════════════════════════════════════════════════
                          MULTI-AREA BOOKMARKS API ROUTES
                               RESTful Endpoint Management
══════════════════════════════════════════════════════════════════════════════════

PURPOSE:
RESTful API endpoints for managing multi-area bookmark configurations with
dual-storage architecture integrating Sigma bookmarks and LowDB persistence.

ENDPOINTS:
• POST   /api/multi-area-bookmarks/save           - Create new multi-area bookmark
• GET    /api/multi-area-bookmarks/list           - List bookmarks for workbook
• GET    /api/multi-area-bookmarks/get/:id        - Get specific bookmark
• GET    /api/multi-area-bookmarks/get-by-sigma/:id - Get by Sigma bookmark ID
• PUT    /api/multi-area-bookmarks/update/:id     - Update bookmark
• DELETE /api/multi-area-bookmarks/delete/:id     - Delete bookmark
• GET    /api/multi-area-bookmarks/stats          - Database statistics

DUAL STORAGE WORKFLOW:
1. Save: Create Sigma bookmark (exploreKey) → Store multi-area config in LowDB
2. Load: Fetch multi-area config from LowDB → Use linked Sigma bookmark for exploreKey
3. Delete: Remove from LowDB → Keep Sigma bookmark for exploreKey history

DATA FLOW:
Frontend → API Routes → LowDB Helper → Local Database
        ↘ Create Bookmark Helper → Sigma Cloud API

ERROR HANDLING:
- 400: Missing required fields or invalid parameters
- 404: Bookmark not found
- 500: Server errors with detailed logging

AUTHORS: Development team with Claude Code assistance
LAST UPDATED: 2025-10-15
══════════════════════════════════════════════════════════════════════════════════
*/

// routes/api/multi-area-bookmarks.js
// API routes for multi-area bookmark management

const express = require('express');
const router = express.Router();
const createBookmark = require('../../helpers/create-bookmark');
const {
  saveMultiAreaBookmark,
  getMultiAreaBookmark,
  getMultiAreaBookmarkBySigmaId,
  listMultiAreaBookmarks,
  updateMultiAreaBookmark,
  deleteMultiAreaBookmark,
  getStats
} = require('../../helpers/multi-area-bookmarks');

const DEBUG = process.env.DEBUG === 'true';

/**
 * POST /api/multi-area-bookmarks/save
 * Save a multi-area bookmark configuration
 */
router.post('/save', async (req, res) => {
  try {
    const { 
      name, 
      userEmail, 
      workbookUrlId, 
      exploreKey, 
      areas 
    } = req.body;

    if (!name || !userEmail || !workbookUrlId || !exploreKey || !areas) {
      return res.status(400).json({ 
        error: 'Missing required fields: name, userEmail, workbookUrlId, exploreKey, areas' 
      });
    }

    if (DEBUG) {
      console.log('[MultiAreaAPI] Saving multi-area bookmark:', {
        name,
        userEmail,
        workbookUrlId,
        exploreKey,
        areaCount: Object.keys(areas).filter(key => areas[key]).length
      });
    }

    // Step 1: Create Sigma bookmark for exploreKey storage
    const sigmaBookmark = await createBookmark({
      userEmail,
      workbookUrlId,
      exploreKey,
      name
    });

    if (DEBUG) {
      console.log('[MultiAreaAPI] Created Sigma bookmark:', sigmaBookmark.bookmarkId);
    }

    // Step 2: Save multi-area configuration to local database
    const localBookmarkId = saveMultiAreaBookmark({
      name,
      sigmaBookmarkId: sigmaBookmark.bookmarkId,
      workbookUrlId,
      areas
    });

    res.json({
      success: true,
      localBookmarkId,
      sigmaBookmarkId: sigmaBookmark.bookmarkId,
      name,
      areas
    });

  } catch (err) {
    console.error('[MultiAreaAPI] Save error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

/**
 * GET /api/multi-area-bookmarks/list?workbookUrlId=xxx
 * List all multi-area bookmarks for a workbook
 */
router.get('/list', (req, res) => {
  try {
    const { workbookUrlId } = req.query;

    if (!workbookUrlId) {
      return res.status(400).json({ error: 'Missing workbookUrlId' });
    }

    const bookmarks = listMultiAreaBookmarks(workbookUrlId);

    // Transform for frontend compatibility
    const entries = bookmarks.map(bookmark => ({
      localBookmarkId: bookmark.id,
      sigmaBookmarkId: bookmark.sigmaBookmarkId,
      name: bookmark.name,
      areas: bookmark.areas,
      created: bookmark.created,
      updated: bookmark.updated
    }));

    res.json({ entries });

  } catch (err) {
    console.error('[MultiAreaAPI] List error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

/**
 * GET /api/multi-area-bookmarks/get/:id
 * Get a specific multi-area bookmark
 */
router.get('/get/:id', (req, res) => {
  try {
    const { id } = req.params;
    const bookmark = getMultiAreaBookmark(id);

    if (!bookmark) {
      return res.status(404).json({ error: 'Bookmark not found' });
    }

    res.json(bookmark);

  } catch (err) {
    console.error('[MultiAreaAPI] Get error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

/**
 * GET /api/multi-area-bookmarks/get-by-sigma/:sigmaId
 * Get a multi-area bookmark by Sigma bookmark ID
 */
router.get('/get-by-sigma/:sigmaId', (req, res) => {
  try {
    const { sigmaId } = req.params;
    const bookmark = getMultiAreaBookmarkBySigmaId(sigmaId);

    if (!bookmark) {
      return res.status(404).json({ error: 'Bookmark not found' });
    }

    res.json(bookmark);

  } catch (err) {
    console.error('[MultiAreaAPI] Get by Sigma ID error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

/**
 * PUT /api/multi-area-bookmarks/update/:id
 * Update a multi-area bookmark
 */
router.put('/update/:id', (req, res) => {
  try {
    const { id } = req.params;
    const updates = req.body;

    const success = updateMultiAreaBookmark(id, updates);

    if (!success) {
      return res.status(404).json({ error: 'Bookmark not found' });
    }

    res.json({ success: true, message: 'Bookmark updated successfully' });

  } catch (err) {
    console.error('[MultiAreaAPI] Update error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

/**
 * DELETE /api/multi-area-bookmarks/delete/:id
 * Delete a multi-area bookmark
 */
router.delete('/delete/:id', (req, res) => {
  try {
    const { id } = req.params;
    
    // Get bookmark to find associated Sigma bookmark
    const bookmark = getMultiAreaBookmark(id);
    if (!bookmark) {
      return res.status(404).json({ error: 'Bookmark not found' });
    }

    // Delete from local database
    const success = deleteMultiAreaBookmark(id);

    if (!success) {
      return res.status(500).json({ error: 'Failed to delete bookmark' });
    }

    // Note: We could also delete the Sigma bookmark here if needed
    // But keeping it for exploreKey history might be useful

    res.json({ 
      success: true, 
      message: 'Multi-area bookmark deleted successfully',
      deletedBookmark: bookmark.name
    });

  } catch (err) {
    console.error('[MultiAreaAPI] Delete error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

/**
 * GET /api/multi-area-bookmarks/stats
 * Get database statistics
 */
router.get('/stats', (req, res) => {
  try {
    const stats = getStats();
    res.json(stats);
  } catch (err) {
    console.error('[MultiAreaAPI] Stats error:', err.message);
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;