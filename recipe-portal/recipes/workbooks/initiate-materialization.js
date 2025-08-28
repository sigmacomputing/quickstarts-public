// Title: Initiate Materialization
// Description: This script starts a materialization job for a specified workbook and retrieves its status.

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('./get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const workbookId = process.env.WORKBOOK_ID; // Workbook ID for materialization
const sheetId = process.env.SHEET_ID; // Optional: specific sheet ID to materialize

// Function to start a materialization job
async function startMaterialization() {
    try {
        const accessToken = await getBearerToken();
        if (!accessToken) {
            console.error('Failed to obtain Bearer token.');
            return;
        }

        // Fetch materialization schedules to get the correct sheet ID
        const materializationSchedulesURL = `${baseURL}/workbooks/${workbookId}/materialization-schedules`;
        console.log(`URL sent to Sigma: ${materializationSchedulesURL}`);
        const response = await axios.get(materializationSchedulesURL, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });

        // Parse the sheet ID from the response if schedules are available
        const materializationSchedules = response.data.entries || response.data || [];
        if (materializationSchedules.length === 0) {
            console.error('No materialization schedules found for the specified workbook.');
            return;
        }
        
        console.log(`Found ${materializationSchedules.length} materialization schedule(s):`);
        materializationSchedules.forEach((schedule, index) => {
            console.log(`  ${index}: "${schedule.elementName}" (${schedule.schedule.cronSpec} ${schedule.schedule.timezone}${schedule.paused ? ' - PAUSED' : ''})`);
        });
        
        // Determine which schedule to use
        let selectedSchedule;
        
        if (sheetId) {
            // Find schedule by sheet ID
            selectedSchedule = materializationSchedules.find(schedule => 
                schedule.sheetId === sheetId
            );
            if (!selectedSchedule) {
                console.error(`No materialization schedule found for sheet ID: "${sheetId}"`);
                console.error('Available element names:', materializationSchedules.map(s => `"${s.elementName}"`).join(', '));
                console.error('Available sheet IDs:', materializationSchedules.map(s => s.sheetId).join(', '));
                return;
            }
            console.log(`Selected schedule by sheet ID: "${selectedSchedule.elementName}" (${selectedSchedule.sheetId})`);
        } else if (materializationSchedules.length === 1) {
            // Only one schedule, use it
            selectedSchedule = materializationSchedules[0];
            console.log(`Using the only available schedule: "${selectedSchedule.elementName}"`);
        } else {
            // Multiple schedules, use the first one but warn user
            selectedSchedule = materializationSchedules[0];
            console.log(`Multiple schedules available. Using first one: "${selectedSchedule.elementName}"`);
            console.log('Tip: Use SHEET_ID to specify which schedule to run.');
        }

        const targetSheetId = selectedSchedule.sheetId;
        console.log(`Starting materialization job for workbook ${workbookId}, element "${selectedSchedule.elementName}", sheet ${targetSheetId}...`);

        const materializationsURL = `${baseURL}/workbooks/${workbookId}/materializations`;
        console.log(`URL sent to Sigma: ${materializationsURL}`);
        const startResponse = await axios.post(materializationsURL, {
            sheetId: targetSheetId
        }, {
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json'
            }
        });

        console.log('Materialization job started successfully:', startResponse.data);

        // Retrieve materialization status
        const materializationId = startResponse.data.materializationId; // Correctly extract the materialization ID
        await checkMaterializationStatus(materializationId, accessToken, materializationsURL);
    } catch (error) {
        console.error('Error starting materialization job:', error.response ? error.response.data : error);
    }
}

// Function to check materialization status
async function checkMaterializationStatus(materializationId, accessToken, materializationsURL) {
    try {
        const materializationStatusURL = `${materializationsURL}/${materializationId}`;
        console.log(`URL sent to Sigma: ${materializationStatusURL}`);
        console.log(`Checking materialization status for materialization ID: ${materializationId}`);

        const response = await axios.get(materializationStatusURL, {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        });

        console.log('Materialization status:', response.data.status);

        // Check if the materialization is complete (ready or failed)
        if (response.data.status === 'ready') {
            console.log('Materialization job completed successfully.');
            return; // Stop the script execution
        }
        
        if (response.data.status === 'failed' || response.data.status === 'FAILED') {
            console.log('Materialization job failed.');
            return; // Stop the script execution
        }

        // Continue polling if still in progress
        if (response.data.status === 'pending' || response.data.status === 'building') {
            await new Promise(resolve => setTimeout(resolve, 5000)); // Wait for 5 seconds
            await checkMaterializationStatus(materializationId, accessToken, materializationsURL);
        } else {
            console.log(`Unexpected materialization status: ${response.data.status}`);
        }
    } catch (error) {
        console.error('Error checking materialization status:', error.response ? error.response.data : error);
    }
}

// Execute the script
startMaterialization();
