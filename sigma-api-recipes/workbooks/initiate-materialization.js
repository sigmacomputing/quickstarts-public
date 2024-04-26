// This script starts a materialization job for a specified workbook and retrieves its status

// 1: Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: 'sigma-api-recipes/.env' });

// 2: Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// 3: Import Axios for making HTTP requests
const axios = require('axios');

// 4: Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Your base URL
const workbookId = process.env.WORKBOOK_ID; // Workbook ID for materialization

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
        const materializationSchedules = response.data.entries;
        if (materializationSchedules.length === 0) {
            console.error('No materialization schedules found for the specified workbook.');
            return;
        }

        const sheetId = materializationSchedules[0].sheetId;
        console.log(`Starting materialization job for workbook ${workbookId} and sheet ${sheetId}...`);

        const materializationsURL = `${baseURL}/workbooks/${workbookId}/materializations`;
        console.log(`URL sent to Sigma: ${materializationsURL}`);
        const startResponse = await axios.post(materializationsURL, {
            sheetId: sheetId
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

        // Check if the materialization status is "ready"
        if (response.data.status === 'ready') {
            console.log('Materialization job completed successfully.');
            return; // Stop the script execution
        }

        // Check status periodically until it's either completed or failed
        if (response.data.status !== 'COMPLETE' && response.data.status !== 'FAILED') {
            await new Promise(resolve => setTimeout(resolve, 5000)); // Wait for 5 seconds
            await checkMaterializationStatus(materializationId, accessToken, materializationsURL);
        }
    } catch (error) {
        console.error('Error checking materialization status:', error.response ? error.response.data : error);
    }
}

// Execute the script
startMaterialization();
