// File: embedding_qs_series_2_api_use_cases/routes/api/exports.js

const express = require("express");
const router = express.Router();

const createExportSchedule = require("../../helpers/create-export-schedule");
const listExportSchedules = require("../../helpers/list-export-schedules");
const deleteExportSchedule = require("../../helpers/delete-export-schedule");
const updateExportSchedule = require("../../helpers/update-export-schedule");
const getExportScheduleDetails = require("../../helpers/get-export-schedule-details");
const resolveWorkbookId = require("../../helpers/resolve-workbook-id");
const getBearerToken = require("../../helpers/get-access-token");
const axios = require("axios");

// POST /api/exports - Create a new export schedule
router.post("/", async (req, res) => {
  try {
    const exportConfig = req.body;

    if (process.env.DEBUG === "true") {
      console.log("Export schedule request:", exportConfig);
    }

    // Validate required fields
    if (!exportConfig.workbookId) {
      return res.status(400).json({ error: "Missing workbookId" });
    }

    if (!exportConfig.recipients || !Array.isArray(exportConfig.recipients) || exportConfig.recipients.length === 0) {
      return res.status(400).json({ error: "Missing or invalid recipients array" });
    }

    // Validate email addresses
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const invalidEmails = exportConfig.recipients.filter(email => !emailRegex.test(email.trim()));
    if (invalidEmails.length > 0) {
      return res.status(400).json({ error: `Invalid email addresses: ${invalidEmails.join(", ")}` });
    }

    // Resolve workbook ID (from URL ID to UUID)
    if (process.env.DEBUG === "true") {
      console.log("Resolving workbook URL ID:", exportConfig.workbookId);
    }
    
    const workbook = await resolveWorkbookId(exportConfig.workbookId);
    const actualWorkbookId = workbook.id;
    
    if (process.env.DEBUG === "true") {
      console.log("Resolved to workbook UUID:", actualWorkbookId);
      console.log("Workbook details:", { name: workbook.name, urlId: workbook.urlId });
    }

    // Create the export schedule with resolved workbook ID
    const result = await createExportSchedule({
      ...exportConfig,
      workbookId: actualWorkbookId
    });

    res.status(201).json({
      success: true,
      message: "Export schedule created successfully",
      schedule: result
    });

  } catch (error) {
    console.error("Export creation error:", error.message);
    res.status(500).json({ 
      error: "Failed to create export schedule",
      details: error.message 
    });
  }
});

// POST /api/exports/:workbookId/send/:scheduleId - Send an export immediately using schedule configuration
router.post("/:workbookId/send/:scheduleId", async (req, res) => {
  try {
    const { scheduleId, workbookId } = req.params;
    const { recipients } = req.body;

    if (process.env.DEBUG === "true") {
      console.log("Sending immediate export for schedule:", scheduleId);
      console.log("Workbook:", workbookId);
      console.log("Recipients:", recipients);
      console.log("Request received - about to process...");
    }

    // Validate required fields
    if (!scheduleId) {
      return res.status(400).json({ error: "Missing scheduleId" });
    }

    if (!workbookId) {
      return res.status(400).json({ error: "Missing workbookId" });
    }

    if (!recipients || !Array.isArray(recipients) || recipients.length === 0) {
      return res.status(400).json({ error: "Missing or invalid recipients array" });
    }

    // Validate email addresses
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const invalidEmails = recipients.filter(email => !emailRegex.test(email.trim()));
    if (invalidEmails.length > 0) {
      return res.status(400).json({ error: `Invalid email addresses: ${invalidEmails.join(", ")}` });
    }

    // Resolve workbook ID (from URL ID to UUID)
    const workbook = await resolveWorkbookId(workbookId);
    const actualWorkbookId = workbook.id;
    
    if (process.env.DEBUG === "true") {
      console.log("Resolved workbook UUID:", actualWorkbookId);
    }

    if (process.env.DEBUG === "true") {
      console.log("About to fetch schedules for workbook:", actualWorkbookId);
    }

    // Get the existing export schedules to find the one we're working with
    const schedules = await listExportSchedules(actualWorkbookId);
    
    if (process.env.DEBUG === "true") {
      console.log("Retrieved schedules count:", schedules.length);
      console.log("Looking for schedule ID:", scheduleId);
      console.log("Available schedule IDs:", schedules.map(s => s.scheduledNotificationId));
    }

    const schedule = schedules.find(s => s.scheduledNotificationId === scheduleId);
    
    if (!schedule) {
      console.error("Schedule not found in list");
      return res.status(404).json({ error: "Schedule not found" });
    }
    
    if (process.env.DEBUG === "true") {
      console.log("Found schedule configuration:");
      console.log("   Title:", schedule.configV2?.title);
      console.log("   Message:", schedule.configV2?.messageBody);
      console.log("   Format:", schedule.configV2?.notificationAttachments?.[0]?.formatOptions?.type);
      console.log("   Include Link:", schedule.configV2?.includeLink);
      console.log("   Run as Recipient:", schedule.configV2?.runAsRecipient);
      console.log("Full schedule object:", JSON.stringify(schedule, null, 2));
    }

    // Build the send request payload based on the schedule configuration
    const sendPayload = {
      targets: recipients.map(email => ({
        type: "email",
        email: email.trim()
      })),
      config: {
        title: schedule.configV2?.title || "Scheduled Report",
        messageBody: schedule.configV2?.messageBody || "",
        includeLink: false,
        runAsRecipient: schedule.configV2?.runAsRecipient || false
      },
      attachments: schedule.configV2?.notificationAttachments?.map(attachment => ({
        formatOptions: attachment.formatOptions,
        source: {
          type: attachment.workbookExportSource?.type || "all"
        }
      })) || [
        {
          formatOptions: {
            type: "PDF"
          },
          source: {
            type: "all"
          }
        }
      ]
    };

    if (process.env.DEBUG === "true") {
      console.log("Send payload constructed:");
      console.log(JSON.stringify(sendPayload, null, 2));
      console.log("About to send to Sigma API...");
      console.log("URL:", `${process.env.BASE_URL}/workbooks/${actualWorkbookId}/send`);
    }

    // Send the export using Sigma's /send endpoint
    const bearerToken = await getBearerToken();
    if (!bearerToken) {
      throw new Error("Failed to obtain bearer token");
    }

    if (process.env.DEBUG === "true") {
      console.log("Bearer token obtained, making API request...");
    }

    const response = await axios.post(
      `${process.env.BASE_URL}/workbooks/${actualWorkbookId}/send`,
      sendPayload,
      {
        headers: {
          "Authorization": `Bearer ${bearerToken}`,
          "Content-Type": "application/json"
        }
      }
    );

    if (process.env.DEBUG === "true") {
      console.log("Export sent successfully!");
      console.log("Response status:", response.status);
      console.log("Response data:", JSON.stringify(response.data, null, 2));
    }

    res.status(200).json({
      success: true,
      message: "Export sent successfully",
      result: response.data
    });

  } catch (error) {
    const errorMsg = error.response?.data?.message || 
                    error.response?.data?.error || 
                    error.message;

    console.error("Send export error:", errorMsg);
    res.status(500).json({ 
      error: "Failed to send export",
      details: errorMsg 
    });
  }
});

// GET /api/exports/:workbookId - List export schedules for a workbook
router.get("/:workbookId", async (req, res) => {
  try {
    const { workbookId } = req.params;

    if (process.env.DEBUG === "true") {
      console.log("List export schedules for workbook:", workbookId);
    }

    // Resolve workbook ID (from URL ID to UUID)
    const workbook = await resolveWorkbookId(workbookId);
    const actualWorkbookId = workbook.id;

    const schedules = await listExportSchedules(actualWorkbookId);

    res.status(200).json({
      success: true,
      schedules: schedules
    });

  } catch (error) {
    console.error("Export list error:", error.message);
    res.status(500).json({ 
      error: "Failed to list export schedules",
      details: error.message 
    });
  }
});

// PATCH /api/exports/:scheduleId - Update an export schedule
router.patch("/:scheduleId", async (req, res) => {
  try {
    const { scheduleId } = req.params;
    const exportConfig = req.body;

    if (process.env.DEBUG === "true") {
      console.log("Export schedule update request:", exportConfig);
      console.log("Schedule ID:", scheduleId);
    }

    // Validate required fields
    if (!scheduleId) {
      return res.status(400).json({ error: "Missing scheduleId" });
    }

    if (!exportConfig.recipients || !Array.isArray(exportConfig.recipients) || exportConfig.recipients.length === 0) {
      return res.status(400).json({ error: "Missing or invalid recipients array" });
    }

    // Validate email addresses
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const invalidEmails = exportConfig.recipients.filter(email => !emailRegex.test(email.trim()));
    if (invalidEmails.length > 0) {
      return res.status(400).json({ error: `Invalid email addresses: ${invalidEmails.join(", ")}` });
    }

    // We need the workbook ID for the update endpoint
    // The frontend should provide the workbook ID in the export config
    if (!exportConfig.workbookId) {
      return res.status(400).json({ error: "Missing workbookId in export configuration" });
    }

    // Resolve workbook ID (from URL ID to UUID) if needed
    let actualWorkbookId = exportConfig.workbookId;
    try {
      const workbook = await resolveWorkbookId(exportConfig.workbookId);
      actualWorkbookId = workbook.id;
      
      if (process.env.DEBUG === "true") {
        console.log("Resolved workbook URL ID to UUID:", actualWorkbookId);
      }
    } catch (err) {
      // If resolution fails, assume it's already a UUID
      if (process.env.DEBUG === "true") {
        console.log("Workbook ID resolution failed, assuming it's already a UUID:", actualWorkbookId);
      }
    }

    // Update the export schedule
    const result = await updateExportSchedule(scheduleId, {
      ...exportConfig,
      workbookId: actualWorkbookId
    });

    res.status(200).json({
      success: true,
      message: "Export schedule updated successfully",
      schedule: result
    });

  } catch (error) {
    console.error("Export update error:", error.message);
    res.status(500).json({ 
      error: "Failed to update export schedule",
      details: error.message 
    });
  }
});

// DELETE /api/exports/:workbookId/:scheduleId - Delete an export schedule
router.delete("/:workbookId/:scheduleId", async (req, res) => {
  try {
    const { workbookId, scheduleId } = req.params;

    if (process.env.DEBUG === "true") {
      console.log("Delete export schedule:", scheduleId, "for workbook:", workbookId);
    }

    // Resolve workbook ID (from URL ID to UUID)
    const workbook = await resolveWorkbookId(workbookId);
    const actualWorkbookId = workbook.id;

    await deleteExportSchedule(actualWorkbookId, scheduleId);

    res.status(200).json({
      success: true,
      message: "Export schedule deleted successfully"
    });

  } catch (error) {
    console.error("Export deletion error:", error.message);
    res.status(500).json({ 
      error: "Failed to delete export schedule",
      details: error.message 
    });
  }
});

// GET /api/exports/details/:scheduleId - Get detailed export schedule information including recipients
router.get("/details/:scheduleId", async (req, res) => {
  try {
    const { scheduleId } = req.params;

    if (process.env.DEBUG === "true") {
      console.log("Get export schedule details for:", scheduleId);
    }

    const scheduleDetails = await getExportScheduleDetails(scheduleId);

    res.status(200).json({
      success: true,
      schedule: scheduleDetails
    });

  } catch (error) {
    console.error("Export details error:", error.message);
    res.status(500).json({ 
      error: "Failed to get export schedule details",
      details: error.message 
    });
  }
});

module.exports = router;