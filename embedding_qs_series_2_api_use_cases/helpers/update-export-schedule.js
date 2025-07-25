// File: embedding_qs_series_2_api_use_cases/helpers/update-export-schedule.js

require("dotenv").config();
const axios = require("axios");
const getBearerToken = require("./get-access-token");

const baseURL = process.env.BASE_URL;

/**
 * Updates an existing export schedule using the Sigma API PATCH endpoint
 * 
 * @param {string} scheduleId - Sigma schedule ID (scheduledNotificationId)
 * @param {Object} exportConfig - Export configuration object
 * @param {string} exportConfig.workbookId - Sigma workbook ID
 * @param {Array<string>} exportConfig.recipients - Array of email addresses
 * @param {string} exportConfig.subject - Email subject
 * @param {string} exportConfig.message - Email message body
 * @param {string} exportConfig.format - Export format (PDF, CSV, XLSX)
 * @param {string} exportConfig.frequency - Schedule frequency (daily, weekly, monthly)
 * @param {string} exportConfig.time - Time in HH:MM format
 * @returns {Promise<Object|null>} Updated export schedule object or null if request fails
 */
async function updateExportSchedule(scheduleId, exportConfig) {
  const {
    workbookId,
    recipients,
    subject,
    message,
    format,
    frequency,
    time
  } = exportConfig;

  if (!scheduleId) {
    throw new Error("Missing required field: scheduleId");
  }

  if (!recipients || !Array.isArray(recipients) || recipients.length === 0) {
    throw new Error("Missing required field: recipients");
  }

  const bearerToken = await getBearerToken();
  if (!bearerToken) {
    throw new Error("Failed to obtain bearer token");
  }

  try {
    // Convert time to cron specification
    const [hours, minutes] = (time || "09:00").split(":");
    let cronSpec;
    
    switch (frequency) {
      case "daily":
        cronSpec = `${minutes} ${hours} * * *`; // Every day at specified time
        break;
      case "weekly":
        cronSpec = `${minutes} ${hours} * * 1`; // Every Monday at specified time
        break;
      case "monthly":
        cronSpec = `${minutes} ${hours} 1 * *`; // First day of every month at specified time
        break;
      default:
        cronSpec = `${minutes} ${hours} * * *`; // Default to daily
    }

    // Create target array with email recipients
    const targets = recipients.map(email => ({
      email: email.trim()
    }));

    // Map format to correct API format
    const formatType = format === "XLSX" ? "XLSX" : format === "CSV" ? "CSV" : "PDF";
    
    const requestBody = {
      target: targets,
      schedule: {
        cronSpec: cronSpec,
        timezone: "America/New_York"
      },
      configV2: {
        title: subject,
        messageBody: message || "Hello, you've received a document.",
        notificationAttachments: [
          {
            formatOptions: {
              type: formatType,
              ...(formatType === "PDF" && { layout: "portrait" })
            },
            workbookExportSource: {
              type: "all" // Export entire workbook
            }
          }
        ],
        notificationName: `Export - ${subject}`,
        includeLink: false,
        runAsRecipient: false,
        attachmentSettings: {
          mergePdfAttachments: false,
          zipAttachments: false
        },
        conditionOptions: {
          type: "always"
        }
      }
    };

    // Try the workbook-specific endpoint first, then fall back to direct schedule endpoint
    const possibleUrls = [
      `${baseURL}/workbooks/${workbookId}/schedules/${scheduleId}`, // Workbook-specific
      `${baseURL}/schedules/${scheduleId}` // Direct schedule endpoint
    ];

    let response = null;
    let lastError = null;

    for (let i = 0; i < possibleUrls.length; i++) {
      const url = possibleUrls[i];
      
      if (process.env.DEBUG === "true") {
        console.log(`Updating export schedule with data (attempt ${i + 1}):`, JSON.stringify(requestBody, null, 2));
        console.log(`PATCH URL (attempt ${i + 1}):`, url);
        console.log("Bearer token available:", !!bearerToken);
        console.log("Schedule ID being used:", scheduleId);
        console.log("Workbook ID being used:", workbookId);
      }

      try {
        response = await axios.patch(
          url,
          requestBody,
          {
            headers: {
              "Authorization": `Bearer ${bearerToken}`,
              "Content-Type": "application/json"
            }
          }
        );
        
        if (process.env.DEBUG === "true") {
          console.log(`Update successful with URL (attempt ${i + 1}):`, url);
        }
        break; // Success, exit loop
        
      } catch (error) {
        lastError = error;
        if (process.env.DEBUG === "true") {
          console.log(`Update failed with URL (attempt ${i + 1}):`, url, error.response?.status);
        }
        // Continue to next URL if not the last attempt
        if (i === possibleUrls.length - 1) {
          throw error; // Re-throw the last error if all attempts failed
        }
      }
    }

    if (process.env.DEBUG === "true") {
      console.log("Export schedule updated successfully:", response.data);
    }

    return response.data;

  } catch (error) {
    const errorMsg = error.response?.data?.message || 
                    error.response?.data?.error || 
                    error.message;

    if (process.env.DEBUG === "true") {
      console.error("Error updating export schedule:", errorMsg);
      console.error("Full error response:", error.response?.data);
    }

    throw new Error(`Failed to update export schedule: ${errorMsg}`);
  }
}

module.exports = updateExportSchedule;