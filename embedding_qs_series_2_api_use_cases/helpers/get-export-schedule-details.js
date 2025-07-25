require("dotenv").config();
const axios = require("axios");
const getBearerToken = require("./get-access-token");

const baseURL = process.env.BASE_URL;

/**
 * Get detailed export schedule information including recipients
 * @param {string} scheduleId - The schedule notification ID
 * @returns {Promise<Object>} The detailed schedule data including recipients
 */
async function getExportScheduleDetails(scheduleId) {
  if (!scheduleId) {
    throw new Error('Schedule ID is required');
  }

  if (process.env.DEBUG === "true") {
    console.log(`Fetching detailed schedule information for ID: ${scheduleId}`);
  }

  const bearerToken = await getBearerToken();
  if (!bearerToken) {
    throw new Error("Failed to obtain bearer token");
  }

  try {
    const response = await axios.get(
      `${baseURL}/schedules/${scheduleId}`,
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

    const schedule = response.data;
    
    if (process.env.DEBUG === "true") {
      console.log(`Successfully fetched schedule details for: ${schedule.configV2?.title || scheduleId}`);
      
      // Log recipient information if available
      if (schedule.target && schedule.target.length > 0) {
        console.log(`Found ${schedule.target.length} recipients:`, schedule.target.map(t => t.email));
      } else {
        console.log('No recipients found in schedule details');
      }
    }

    return schedule;
  } catch (error) {
    const errorMsg = error.response?.data?.message || 
                    error.response?.data?.error || 
                    error.message;

    if (process.env.DEBUG === "true") {
      console.error(`Error fetching schedule details for ${scheduleId}:`, errorMsg);
    }

    throw new Error(`Failed to get schedule details: ${errorMsg}`);
  }
}

module.exports = getExportScheduleDetails;