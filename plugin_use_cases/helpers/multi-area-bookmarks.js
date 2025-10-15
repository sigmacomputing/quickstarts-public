/*
══════════════════════════════════════════════════════════════════════════════════
                           MULTI-AREA BOOKMARKS DATABASE
                              LowDB Storage Management
══════════════════════════════════════════════════════════════════════════════════

PURPOSE:
This module provides persistent storage for multi-area dashboard configurations
using LowDB, overcoming Sigma's single-state bookmark limitations through a
dual-storage architecture.

ARCHITECTURE:
- Sigma Bookmarks: Store exploreKey and workbook state (cloud, single-state)
- LowDB Database: Store multi-area node configurations (local, multi-state)
- Combined: Complete bookmark restoration across all dashboard areas

DATA STRUCTURE:
{
  "bookmarks": {
    "localBookmarkId": {
      "id": "uuid",
      "name": "Bookmark Name",
      "sigmaBookmarkId": "sigma-bookmark-uuid",
      "workbookUrlId": "workbook-id",
      "areas": {
        "viz1_nodeid": "node-id-or-null",
        "viz2_nodeid": "node-id-or-null", 
        "viz3_nodeid": "node-id-or-null"
      },
      "created": "ISO-timestamp",
      "updated": "ISO-timestamp"
    }
  },
  "metadata": {
    "version": "1.0.0",
    "created": "ISO-timestamp"
  }
}

WORKFLOW INTEGRATION:
1. Save: Host captures all area states → Creates Sigma bookmark → Stores here
2. Load: Host fetches from here → Restores all areas → Loads exploreKey from Sigma
3. Update: Modify area configurations without affecting Sigma bookmark
4. Delete: Remove local config → Keep Sigma bookmark for exploreKey history

AUTHORS: Development team with Claude Code assistance
LAST UPDATED: 2025-10-15
══════════════════════════════════════════════════════════════════════════════════
*/

// helpers/multi-area-bookmarks.js
// Local database for multi-area bookmark configurations

const low = require('lowdb');
const FileSync = require('lowdb/adapters/FileSync');
const { v4: uuidv4 } = require('uuid');
const path = require('path');

// Lazy initialization of database
let db = null;

function getDatabase() {
  if (!db) {
    const adapter = new FileSync(path.join(__dirname, '../data/multi-area-bookmarks.json'));
    db = low(adapter);
    
    // Set default structure
    db.defaults({ 
      bookmarks: {},
      metadata: { 
        version: "1.0.0",
        created: new Date().toISOString() 
      }
    }).write();
    
    console.log('[MultiAreaDB] Database initialized');
  }
  return db;
}

/**
 * Save a multi-area bookmark configuration
 * @param {Object} config - Bookmark configuration
 * @param {string} config.name - Bookmark name
 * @param {string} config.sigmaBookmarkId - Associated Sigma bookmark ID
 * @param {Object} config.areas - Area configurations
 * @param {string} config.workbookUrlId - Workbook URL ID
 * @returns {string} Local bookmark ID
 */
function saveMultiAreaBookmark(config) {
  const db = getDatabase();
  const localBookmarkId = uuidv4();
  const timestamp = new Date().toISOString();
  
  const bookmarkData = {
    id: localBookmarkId,
    name: config.name,
    sigmaBookmarkId: config.sigmaBookmarkId,
    workbookUrlId: config.workbookUrlId,
    areas: config.areas || {},
    created: timestamp,
    updated: timestamp
  };
  
  db.set(`bookmarks.${localBookmarkId}`, bookmarkData).write();
  
  console.log(`[MultiAreaDB] Saved bookmark: ${config.name} (${localBookmarkId})`);
  return localBookmarkId;
}

/**
 * Get a multi-area bookmark configuration
 * @param {string} localBookmarkId - Local bookmark ID
 * @returns {Object|null} Bookmark configuration
 */
function getMultiAreaBookmark(localBookmarkId) {
  const db = getDatabase();
  const bookmark = db.get(`bookmarks.${localBookmarkId}`).value();
  
  if (bookmark) {
    console.log(`[MultiAreaDB] Retrieved bookmark: ${bookmark.name} (${localBookmarkId})`);
  } else {
    console.log(`[MultiAreaDB] Bookmark not found: ${localBookmarkId}`);
  }
  
  return bookmark;
}

/**
 * Get a multi-area bookmark by Sigma bookmark ID
 * @param {string} sigmaBookmarkId - Sigma bookmark ID
 * @returns {Object|null} Bookmark configuration
 */
function getMultiAreaBookmarkBySigmaId(sigmaBookmarkId) {
  const db = getDatabase();
  const bookmarks = db.get('bookmarks').value();
  
  for (const [localId, bookmark] of Object.entries(bookmarks)) {
    if (bookmark.sigmaBookmarkId === sigmaBookmarkId) {
      console.log(`[MultiAreaDB] Found by Sigma ID: ${bookmark.name} (${localId})`);
      return bookmark;
    }
  }
  
  console.log(`[MultiAreaDB] No bookmark found for Sigma ID: ${sigmaBookmarkId}`);
  return null;
}

/**
 * List all multi-area bookmarks for a workbook
 * @param {string} workbookUrlId - Workbook URL ID
 * @returns {Array} Array of bookmark configurations
 */
function listMultiAreaBookmarks(workbookUrlId) {
  const db = getDatabase();
  const bookmarks = db.get('bookmarks').value();
  const workbookBookmarks = [];
  
  for (const [localId, bookmark] of Object.entries(bookmarks)) {
    if (bookmark.workbookUrlId === workbookUrlId) {
      workbookBookmarks.push(bookmark);
    }
  }
  
  console.log(`[MultiAreaDB] Found ${workbookBookmarks.length} bookmarks for workbook: ${workbookUrlId}`);
  return workbookBookmarks.sort((a, b) => new Date(b.created) - new Date(a.created));
}

/**
 * Update a multi-area bookmark configuration
 * @param {string} localBookmarkId - Local bookmark ID
 * @param {Object} updates - Updates to apply
 * @returns {boolean} Success status
 */
function updateMultiAreaBookmark(localBookmarkId, updates) {
  const db = getDatabase();
  const existing = db.get(`bookmarks.${localBookmarkId}`).value();
  
  if (!existing) {
    console.log(`[MultiAreaDB] Cannot update non-existent bookmark: ${localBookmarkId}`);
    return false;
  }
  
  const updatedData = {
    ...existing,
    ...updates,
    updated: new Date().toISOString()
  };
  
  db.set(`bookmarks.${localBookmarkId}`, updatedData).write();
  
  console.log(`[MultiAreaDB] Updated bookmark: ${existing.name} (${localBookmarkId})`);
  return true;
}

/**
 * Delete a multi-area bookmark
 * @param {string} localBookmarkId - Local bookmark ID
 * @returns {boolean} Success status
 */
function deleteMultiAreaBookmark(localBookmarkId) {
  const db = getDatabase();
  const existing = db.get(`bookmarks.${localBookmarkId}`).value();
  
  if (!existing) {
    console.log(`[MultiAreaDB] Cannot delete non-existent bookmark: ${localBookmarkId}`);
    return false;
  }
  
  db.unset(`bookmarks.${localBookmarkId}`).write();
  
  console.log(`[MultiAreaDB] Deleted bookmark: ${existing.name} (${localBookmarkId})`);
  return true;
}

/**
 * Get database statistics
 * @returns {Object} Database statistics
 */
function getStats() {
  const db = getDatabase();
  const bookmarks = db.get('bookmarks').value();
  
  return {
    totalBookmarks: Object.keys(bookmarks).length,
    metadata: db.get('metadata').value()
  };
}

module.exports = {
  saveMultiAreaBookmark,
  getMultiAreaBookmark,
  getMultiAreaBookmarkBySigmaId,
  listMultiAreaBookmarks,
  updateMultiAreaBookmark,
  deleteMultiAreaBookmark,
  getStats
};