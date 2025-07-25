// File: embedding_qs_series_2_api_use_cases/helpers/list-export-schedules.js

require("dotenv").config();
const axios = require("axios");
const getBearerToken = require("./get-access-token");

const baseURL = process.env.BASE_URL;

/**
 * Lists all export schedules for a workbook using the Sigma API
 * 
 * @param {string} workbookId - Sigma workbook ID
 * @returns {Promise<Array|null>} Array of export schedules or null if request fails
 */
async function listExportSchedules(workbookId) {
  if (!workbookId) {
    throw new Error("Missing required field: workbookId");
  }

  const bearerToken = await getBearerToken();
  if (!bearerToken) {
    throw new Error("Failed to obtain bearer token");
  }

  try {
    const response = await axios.get(
      `${baseURL}/workbooks/${workbookId}/schedules`,
      {
        headers: {
          "Authorization": `Bearer ${bearerToken}`,
          "Content-Type": "application/json"
        }
      }
    );

    if (process.env.DEBUG === "true") {
      console.log("Export schedules retrieved:", response.data);
      console.log("First schedule structure:", JSON.stringify(response.data.entries?.[0], null, 2));
    }

    return response.data.entries || [];

  } catch (error) {
    const errorMsg = error.response?.data?.message || 
                    error.response?.data?.error || 
                    error.message;

    if (process.env.DEBUG === "true") {
      console.error("Error listing export schedules:", errorMsg);
    }

    throw new Error(`Failed to list export schedules: ${errorMsg}`);
  }
}

module.exports = listExportSchedules;