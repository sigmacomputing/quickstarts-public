// File: embedding_qs_series_2_api_use_cases/routes/api/workbook-descriptions.js
// API routes for workbook description operations with local database storage

const express = require("express");
const router = express.Router();
const resolveWorkbookId = require("../../helpers/resolve-workbook-id");
const db = require("../../helpers/local-wb-descriptions-store");

// Initialize DEBUG mode
const DEBUG = process.env.DEBUG === "true";

/**
 * GET /api/workbook-descriptions/:workbookId
 * Get workbook description by workbook URL ID
 */
router.get("/:workbookId", async (req, res) => {
  try {
    const { workbookId } = req.params;

    if (DEBUG) {
      console.log("Fetching workbook description for:", workbookId);
    }

    // Resolve workbook to get full details
    const workbook = await resolveWorkbookId(workbookId);
    const actualWorkbookId = workbook.id;

    // Look for existing description using either URL ID or UUID
    const descriptions = db.get("workbookDescriptions").value();
    const description = descriptions.find(desc => 
      desc.workbookUrlId === workbookId || desc.workbookId === actualWorkbookId
    );

    if (description) {
      if (DEBUG) console.log("Found existing description:", description.description);
      res.json({ 
        success: true, 
        description: description,
        workbook: {
          id: actualWorkbookId,
          urlId: workbook.urlId,
          name: workbook.name
        }
      });
    } else {
      if (DEBUG) console.log("No description found for workbook");
      res.json({ 
        success: true, 
        description: null,
        workbook: {
          id: actualWorkbookId,
          urlId: workbook.urlId,
          name: workbook.name
        }
      });
    }

  } catch (error) {
    console.error("Error fetching workbook description:", error.message);
    res.status(500).json({ 
      success: false,
      error: "Failed to fetch workbook description",
      details: error.message 
    });
  }
});

/**
 * POST /api/workbook-descriptions
 * Create a new workbook description
 */
router.post("/", async (req, res) => {
  try {
    const { workbookId, description, memberId } = req.body;

    if (DEBUG) {
      console.log("Creating workbook description:", { workbookId, description: description?.substring(0, 50) + "...", memberId });
    }

    // Validate required fields
    if (!workbookId || !description || !memberId) {
      return res.status(400).json({ 
        success: false,
        error: "Missing required fields: workbookId, description, memberId" 
      });
    }

    // Resolve workbook to get full details
    const workbook = await resolveWorkbookId(workbookId);
    const actualWorkbookId = workbook.id;

    // Check if description already exists
    const descriptions = db.get("workbookDescriptions").value();
    const existingDescription = descriptions.find(desc => 
      desc.workbookUrlId === workbookId || desc.workbookId === actualWorkbookId
    );

    if (existingDescription) {
      return res.status(409).json({
        success: false,
        error: "Description already exists for this workbook. Use PUT to update."
      });
    }

    // Create new description entry
    const newDescription = {
      workbookId: actualWorkbookId,
      workbookUrlId: workbook.urlId,
      workbookName: workbook.name,
      description: description,
      createdBy: memberId,
      updatedBy: memberId,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };

    // Save to database
    db.get("workbookDescriptions")
      .push(newDescription)
      .write();

    if (DEBUG) console.log("Workbook description created successfully");

    res.status(201).json({
      success: true,
      message: "Workbook description created successfully",
      description: newDescription
    });

  } catch (error) {
    console.error("Error creating workbook description:", error.message);
    res.status(500).json({ 
      success: false,
      error: "Failed to create workbook description",
      details: error.message 
    });
  }
});

/**
 * PUT /api/workbook-descriptions/:workbookId
 * Update an existing workbook description
 */
router.put("/:workbookId", async (req, res) => {
  try {
    const { workbookId } = req.params;
    const { description, memberId } = req.body;

    if (DEBUG) {
      console.log("Updating workbook description for:", workbookId);
    }

    // Validate required fields
    if (!description || !memberId) {
      return res.status(400).json({ 
        success: false,
        error: "Missing required fields: description, memberId" 
      });
    }

    // Resolve workbook to get full details
    const workbook = await resolveWorkbookId(workbookId);
    const actualWorkbookId = workbook.id;

    // Find existing description
    const descriptions = db.get("workbookDescriptions");
    const existingIndex = descriptions.value().findIndex(desc => 
      desc.workbookUrlId === workbookId || desc.workbookId === actualWorkbookId
    );

    if (existingIndex === -1) {
      return res.status(404).json({
        success: false,
        error: "Description not found for this workbook"
      });
    }

    // Update the description
    const updatedDescription = {
      ...descriptions.value()[existingIndex],
      description: description,
      updatedBy: memberId,
      updatedAt: new Date().toISOString()
    };

    descriptions.nth(existingIndex).assign(updatedDescription).write();

    if (DEBUG) console.log("Workbook description updated successfully");

    res.json({
      success: true,
      message: "Workbook description updated successfully",
      description: updatedDescription
    });

  } catch (error) {
    console.error("Error updating workbook description:", error.message);
    res.status(500).json({ 
      success: false,
      error: "Failed to update workbook description",
      details: error.message 
    });
  }
});

/**
 * DELETE /api/workbook-descriptions/:workbookId
 * Delete a workbook description
 */
router.delete("/:workbookId", async (req, res) => {
  try {
    const { workbookId } = req.params;

    if (DEBUG) {
      console.log("Deleting workbook description for:", workbookId);
    }

    // Resolve workbook to get full details
    const workbook = await resolveWorkbookId(workbookId);
    const actualWorkbookId = workbook.id;

    // Find and remove the description
    const descriptions = db.get("workbookDescriptions");
    const removed = descriptions.remove(desc => 
      desc.workbookUrlId === workbookId || desc.workbookId === actualWorkbookId
    ).write();

    if (removed.length === 0) {
      return res.status(404).json({
        success: false,
        error: "Description not found for this workbook"
      });
    }

    if (DEBUG) console.log("Workbook description deleted successfully");

    res.json({
      success: true,
      message: "Workbook description deleted successfully"
    });

  } catch (error) {
    console.error("Error deleting workbook description:", error.message);
    res.status(500).json({ 
      success: false,
      error: "Failed to delete workbook description",
      details: error.message 
    });
  }
});

module.exports = router;