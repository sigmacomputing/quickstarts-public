// file: embedding_qs_series_2_api_use_cases/routes/api/default-workbook.js

const express = require("express");
const router = express.Router();
const low = require('lowdb');
const FileSync = require('lowdb/adapters/FileSync');
const path = require('path');

const adapter = new FileSync(path.join(__dirname, '../../data/default-workbooks.json'));
const db = low(adapter);

// Initialize the database
function initDB() {
  db.defaults({ defaults: [] }).write();
}

// GET /api/default-workbook/:userEmail - Get user's default workbook
router.get("/:userEmail", (req, res) => {
  const { userEmail } = req.params;
  
  try {
    initDB();
    
    const userDefault = db.get('defaults').find({ userEmail }).value();
    
    if (!userDefault) {
      return res.status(200).json({ hasDefault: false });
    }
    
    res.status(200).json({ 
      hasDefault: true, 
      ...userDefault 
    });
    
  } catch (err) {
    console.error("Error getting default workbook:", err.message);
    res.status(500).json({ error: err.message || "Failed to get default workbook" });
  }
});

// POST /api/default-workbook - Set user's default workbook
router.post("/", (req, res) => {
  const { 
    userEmail, 
    memberID, 
    workbookName, 
    workbookUrlId 
  } = req.body;

  if (!userEmail || !memberID || !workbookName || !workbookUrlId) {
    return res.status(400).json({ 
      error: "Missing required fields: userEmail, memberID, workbookName, workbookUrlId" 
    });
  }

  try {
    initDB();
    
    // Remove any existing default for this user
    db.get('defaults').remove((entry) => entry.userEmail === userEmail).write();
    
    // Add new default
    const newDefault = {
      userEmail,
      memberID,
      workbookName,
      workbookUrlId,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };
    
    db.get('defaults').push(newDefault).write();
    
    if (process.env.DEBUG === "true") {
      console.log(`Default workbook set for ${userEmail}: ${workbookName}`);
    }
    
    res.status(200).json({ 
      success: true, 
      message: "Default workbook set successfully",
      default: newDefault
    });
    
  } catch (err) {
    console.error("Error setting default workbook:", err.message);
    res.status(500).json({ error: err.message || "Failed to set default workbook" });
  }
});

// DELETE /api/default-workbook/:userEmail - Clear user's default workbook
router.delete("/:userEmail", (req, res) => {
  const { userEmail } = req.params;
  
  try {
    initDB();
    
    const beforeCount = db.get('defaults').size().value();
    
    // Find and remove the specific user's default
    db.get('defaults').remove((entry) => entry.userEmail === userEmail).write();
    
    const afterCount = db.get('defaults').size().value();
    
    if (process.env.DEBUG === "true") {
      console.log(`Default workbook cleared for ${userEmail}`);
    }
    
    res.status(200).json({ 
      success: true, 
      message: "Default workbook cleared successfully",
      removed: beforeCount > afterCount
    });
    
  } catch (err) {
    console.error("Error clearing default workbook:", err.message);
    res.status(500).json({ error: err.message || "Failed to clear default workbook" });
  }
});

module.exports = router;