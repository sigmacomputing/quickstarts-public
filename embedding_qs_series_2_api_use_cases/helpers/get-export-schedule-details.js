require("dotenv").config();
const axios = require("axios");
const getBearerToken = require("./get-access-token");
const baseURL = process.env.BASE_URL;

/**
 * Get detailed export schedule information including recipients
 * @param {string} workbookId - The workbook ID
 * @param {string} scheduleId - The schedule notification ID (optional - used to filter results)
 * @returns {Promise<Object>} The detailed schedule data including recipients
 */
async function getExportScheduleDetails(workbookId, scheduleId = null) {
  if (!workbookId) {
    throw new Error('Workbook ID is required');
  }

  if (process.env.DEBUG === "true") {
    console.log(`Fetching schedule information for workbook: ${workbookId}`);
  }

  const bearerToken = await getBearerToken();
  if (!bearerToken) {
    throw new Error("Failed to obtain bearer token");
  }

  try {
    const response = await axios.get(
      `${baseURL}/v2/workbooks/${workbookId}/schedules`,
      {
        headers: {
          "Authorization": `Bearer ${bearerToken}`,
          "Content-Type": "application/json"
        }
      }
    );
    
    if (!response || !response.data) {
      throw new Error('No schedule data returned from API');
    }

    let schedule = response.data;
    
    // If scheduleId is provided, filter to find the specific schedule
    if (scheduleId) {
      if (Array.isArray(schedule)) {
        schedule = schedule.find(s => s.scheduleId === scheduleId || s.id === scheduleId);
        if (!schedule) {
          throw new Error(`Schedule with ID ${scheduleId} not found in workbook ${workbookId}`);
        }
      }
    }
    
    if (process.env.DEBUG === "true") {
      if (Array.isArray(schedule)) {
        console.log(`Successfully fetched ${schedule.length} schedules for workbook`);
      } else {
        console.log(`Successfully fetched schedule details for: ${schedule.configV2?.title || scheduleId}`);
        
        // Log recipient information if available
        if (schedule.target && schedule.target.length > 0) {
          console.log(`Found ${schedule.target.length} recipients:`, schedule.target.map(t => t.email));
        } else {
          console.log('No recipients found in schedule details');
        }
      }
    }

    return schedule;
  } catch (error) {
    const errorMsg = error.response?.data?.message || 
                    error.response?.data?.error || 
                    error.message;
    if (process.env.DEBUG === "true") {
      console.error(`Error fetching schedule details for workbook ${workbookId}:`, errorMsg);
    }
    throw new Error(`Failed to get schedule details: ${errorMsg}`);
  }
}

module.exports = getExportScheduleDetails;
