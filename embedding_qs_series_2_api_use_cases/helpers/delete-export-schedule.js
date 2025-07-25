// File: embedding_qs_series_2_api_use_cases/helpers/delete-export-schedule.js

require("dotenv").config();
const axios = require("axios");
const getBearerToken = require("./get-access-token");

const baseURL = process.env.BASE_URL;

/**
 * Deletes an export schedule using the Sigma API
 * 
 * @param {string} workbookId - Sigma workbook ID
 * @param {string} scheduleId - Export schedule ID to delete
 * @returns {Promise<boolean>} True if deletion was successful
 */
async function deleteExportSchedule(workbookId, scheduleId) {
  if (!workbookId || !scheduleId) {
    throw new Error("Missing required fields: workbookId and scheduleId");
  }

  const bearerToken = await getBearerToken();
  if (!bearerToken) {
    throw new Error("Failed to obtain bearer token");
  }

  try {
    await axios.delete(
      `${baseURL}/workbooks/${workbookId}/schedules/${scheduleId}`,
      {
        headers: {
          "Authorization": `Bearer ${bearerToken}`,
          "Content-Type": "application/json"
        }
      }
    );

    if (process.env.DEBUG === "true") {
      console.log(`Export schedule ${scheduleId} deleted successfully`);
    }

    return true;

  } catch (error) {
    const errorMsg = error.response?.data?.message || 
                    error.response?.data?.error || 
                    error.message;

    if (process.env.DEBUG === "true") {
      console.error("Error deleting export schedule:", errorMsg);
    }

    throw new Error(`Failed to delete export schedule: ${errorMsg}`);
  }
}

module.exports = deleteExportSchedule;