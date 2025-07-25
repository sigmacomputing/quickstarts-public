// File: embedding_qs_series_2_api_use_cases/helpers/create-export-schedule.js

require("dotenv").config();
const axios = require("axios");
const getBearerToken = require("./get-access-token");

const baseURL = process.env.BASE_URL;

/**
 * Creates a scheduled export for a workbook using the Sigma API
 * 
 * @param {Object} exportConfig - Export configuration object
 * @param {string} exportConfig.workbookId - Sigma workbook ID
 * @param {Array<string>} exportConfig.recipients - Array of email addresses
 * @param {string} exportConfig.subject - Email subject
 * @param {string} exportConfig.message - Email message body
 * @param {string} exportConfig.format - Export format (PDF, CSV, XLSX)
 * @param {string} exportConfig.frequency - Schedule frequency (daily, weekly, monthly)
 * @param {string} exportConfig.time - Time in HH:MM format
 * @returns {Promise<Object|null>} Export schedule object or null if request fails
 */
async function createExportSchedule(exportConfig) {
  const {
    workbookId,
    recipients,
    subject,
    message,
    format,
    frequency,
    time
  } = exportConfig;

  if (!workbookId || !recipients || !Array.isArray(recipients) || recipients.length === 0) {
    throw new Error("Missing required fields: workbookId and recipients");
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
        exportAttachments: [
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
        exportName: `Export - ${subject}`,
        includeLink: false,
        runAsRecipient: false,
        attachmentSettings: {
          mergeAttachments: false,
          zipAttachments: false
        },
        conditionOptions: {
          type: "always"
        }
      }
    };

    if (process.env.DEBUG === "true") {
      console.log("Creating export schedule with data:", JSON.stringify(requestBody, null, 2));
      console.log("POST URL:", `${baseURL}/workbooks/${workbookId}/schedules`);
      console.log("Bearer token available:", !!bearerToken);
    }

    const response = await axios.post(
      `${baseURL}/workbooks/${workbookId}/schedules`,
      requestBody,
      {
        headers: {
          "Authorization": `Bearer ${bearerToken}`,
          "Content-Type": "application/json"
        }
      }
    );

    if (process.env.DEBUG === "true") {
      console.log("Export schedule created successfully:", response.data);
    }

    return response.data;

  } catch (error) {
    const errorMsg = error.response?.data?.message || 
                    error.response?.data?.error || 
                    error.message;

    if (process.env.DEBUG === "true") {
      console.error("Error creating export schedule:", errorMsg);
      console.error("Full error response:", error.response?.data);
    }

    throw new Error(`Failed to create export schedule: ${errorMsg}`);
  }
}

module.exports = createExportSchedule;