// This script triggers an export to PDF job with date range parameters, and downloads the export once ready.
// The export will be the entire workbook in PDF format.

// Load environment variables from a specific .env file for configuration
require('dotenv').config({ path: './.env' });

// Import the function to obtain a bearer token from the authenticate-bearer module
const getBearerToken = require('../get-access-token');

// Import Axios for making HTTP requests
const axios = require('axios');

// Load necessary modules for file handling
const fs = require('fs');
const path = require('path');

// Load use-case specific variables from environment variables
const baseURL = process.env.baseURL; // Base URL for the Sigma API
const workbookId = process.env.WORKBOOK_ID; // Workbook ID from which to export data

async function initiateExport(accessToken) {
    // Prepare the options for the export request with correct format and filters
    const exportOptions = {
       workbookId: workbookId,
       format: { type: 'pdf', layout: 'portrait' }, // Export as PDF in portrait layout
    };

    console.log('Final export options:', JSON.stringify(exportOptions, null, 2));

    try {
        const response = await axios.post(
            `${baseURL}/workbooks/${workbookId}/export`,
            exportOptions,
            { headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' } }
        );
        console.log('Export initiated successfully, response:', response.data);
        return response.data.queryId; // Extract and return the query ID from the response
    } catch (error) {
        console.error('Failed to initiate export:', error);
        return null;
    }
}

async function checkExportReady(queryId, accessToken) {
    // Continuously check if the export is ready for download
    console.log(`Checking export readiness for queryId: ${queryId}`);
    while (true) {
        try {
            const response = await axios.get(
                `${baseURL}/query/${queryId}/download`,
                { headers: { Authorization: `Bearer ${accessToken}` }, responseType: 'stream' }
            );

            if (response.status === 200) { // Check if the export is ready
                console.log('Export is ready for download.');
                return response.data;
            } else {
                console.log(`Received unexpected status code: ${response.status}`);
            }
        } catch (error) {
            if (error.response && error.response.status === 204) {
                // Export not ready yet, wait before retrying
                console.log('Export is not ready yet. Waiting to retry...');
                await new Promise(resolve => setTimeout(resolve, 10000));
            } else {
                console.error('Failed to check export status:', error);
                return null;
            }
        }
    }
}

async function downloadExport(data, filename) {
    // Handle the download of the export file
    const filePath = path.join(__dirname, filename);
    const writer = fs.createWriteStream(filePath);

    return new Promise((resolve, reject) => {
        data.pipe(writer);
        let error = null;

        writer.on('error', err => {
            error = err;
            writer.close();
            reject(err);
        });

        writer.on('finish', () => {
            if (!error) {
                console.log(`Export downloaded successfully to: ${filePath}`);
                resolve(true);
            }
        });
    });
}

async function exportWorkflow() {
    // Main workflow to manage the export process
    const accessToken = await getBearerToken();
    if (!accessToken) {
        console.error('Failed to obtain bearer token.');
        return;
    }

    const queryId = await initiateExport(accessToken);
    if (!queryId) {
        console.error('Failed to initiate export or obtain queryId.');
        return;
    }

    const data = await checkExportReady(queryId, accessToken);
    if (data) {
        await downloadExport(data, 'PlugsSalesPerformanceDashboard.pdf');
    } else {
        console.error('Failed to prepare the export for download.');
    }

    // Forcibly exit the process if the script is still hanging
    process.exit(0);
}

exportWorkflow();