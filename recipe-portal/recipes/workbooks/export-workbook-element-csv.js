// Title: Export Workbook Element CSV
// Description: This script triggers an export to CSV job with date range parameters, and downloads the export once ready.
//
// PREREQUISITES:
// - Workbook must contain the target element (table/chart) to export
// - For date filtering: Workbook must have a page control with ID "API-Date-Filter"
//   (Control ID can be found in workbook edit mode > select control > Properties panel)
// - Element must be compatible with CSV export format (tables work best)

console.log('CSV Export script loaded');

// Environment variables are provided dynamically by the UI - no .env file needed

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
const elementId = process.env.ELEMENT_ID; // Element ID within the workbook to target for export
const startDate = process.env.START_DATE; // Start date for export range (YYYY-MM-DD format)
const endDate = process.env.END_DATE; // End date for export range (YYYY-MM-DD format)
const rowLimit = process.env.LIMIT ? parseInt(process.env.LIMIT) : 100000; // Row limit for export (default: 100K)
const exportFilename = process.env.EXPORT_FILENAME || 'export.csv'; // Custom filename for exported file

// Validate row limit
if (rowLimit > 1000000) {
    console.log('ERROR: Row limit exceeds maximum allowed (1,000,000)');
    process.exit(1);
}

console.log('Configuration:');
console.log('  Workbook ID: ' + workbookId);
console.log('  Element ID: ' + elementId);
console.log('  Date range: ' + (startDate && endDate ? startDate + ' to ' + endDate : 'All data'));
console.log('  Row limit: ' + rowLimit.toLocaleString() + ' rows');
console.log('  Output filename: ' + exportFilename);

async function initiateExport(accessToken) {
    // Prepare the options for the export request with correct format and filters
    const exportOptions = {
        elementId: elementId,
        format: { type: 'csv' }, // Define the export format
        runAsynchronously: true // Request the export to run asynchronously
    };

    // Add date range parameters if provided
    if (startDate && endDate) {
        exportOptions.parameters = {
            "DateFilter": `min:${startDate},max:${endDate}`
        };
        console.log('Date range applied: ' + startDate + ' to ' + endDate);
    } else if (startDate || endDate) {
        console.warn('Both START_DATE and END_DATE required for date filtering - skipping filter');
    }

    try {
        const response = await axios.post(
            `${baseURL}/workbooks/${workbookId}/export`,
            exportOptions,
            { headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' } }
        );
        const queryId = response.data.queryId;
        console.log('Export initiated - QueryID: ' + queryId);
        return queryId;
    } catch (error) {
        console.error('Failed to initiate export:', error);
        return null;
    }
}

async function checkExportReady(queryId, accessToken) {
    // Continuously check if the export is ready for download
    console.log('Checking export readiness for queryId: ' + queryId);
    while (true) {
        try {
            const downloadUrl = baseURL + '/query/' + queryId + '/download';
            console.log('Download URL: ' + downloadUrl);
            
            const response = await axios.get(downloadUrl, { 
                headers: { Authorization: 'Bearer ' + accessToken }, 
                responseType: 'stream' 
            });

            if (response.status === 200) { // Check if the export is ready
                console.log('Export is ready for download.');
                return response.data;
            } else {
                console.log('Received unexpected status code: ' + response.status + ' (expected 200 or 204)');
                await new Promise(resolve => setTimeout(resolve, 3000)); // Wait before retry
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
                console.log('Export downloaded successfully to: ' + filePath);
                resolve(true);
            }
        });
    });
}

async function exportWorkflow() {
    try {
        console.log('Authenticating...');
        const accessToken = await getBearerToken();
        if (!accessToken) {
            console.log('ERROR: Authentication failed');
            return;
        }
        console.log('Initiating CSV export...');
        const exportOptions = {
            elementId: elementId,
            format: { type: 'csv' },
            runAsynchronously: true
        };
        
        // Add row limit (always included now)
        exportOptions.rowLimit = rowLimit;
        
        // Add date range parameters if provided (requires workbook control with ID: API-Date-Filter)
        if (startDate && endDate) {
            exportOptions.parameters = {
                "API-Date-Filter": "min:" + startDate + ",max:" + endDate
            };
        }

        console.log('Final export options being sent to API:');
        console.log(JSON.stringify(exportOptions, null, 2));

        const response = await axios.post(
            baseURL + '/workbooks/' + workbookId + '/export',
            exportOptions,
            { headers: { Authorization: 'Bearer ' + accessToken, 'Content-Type': 'application/json' } }
        );
        
        const queryId = response.data.queryId;
        if (!queryId) {
            console.log('ERROR: No queryId received from export API');
            return;
        }
        
        console.log('Export initiated - QueryID: ' + queryId);

        console.log('Waiting for export to complete...');
        const downloadUrl = baseURL + '/query/' + queryId + '/download';
        
        let attempts = 0;
        let lastStatus = null;
        const loadingChars = ['|', '/', '-', '\\'];
        
        while (attempts < 20) {
            attempts++;
            
            try {
                const statusResponse = await axios.get(downloadUrl, {
                    headers: { Authorization: 'Bearer ' + accessToken },
                    responseType: 'stream'
                });
                
                if (statusResponse.status === 200) {
                    console.log('Export ready! Downloading...');
                    
                    // Capture the CSV data as chunks
                    let csvChunks = [];
                    let chunkCount = 0;
                    
                    statusResponse.data.on('data', (chunk) => {
                        chunkCount++;
                        csvChunks.push(chunk);
                        if (chunkCount % 50 === 0) {
                            console.log('Received chunk #' + chunkCount + ', total bytes so far: ' + Buffer.concat(csvChunks).length);
                        }
                    });
                    
                    statusResponse.data.on('end', () => {
                        // Combine all chunks into a single buffer
                        const csvBuffer = Buffer.concat(csvChunks);
                        const sizeKB = Math.round(csvBuffer.length / 1024);
                        const csvText = csvBuffer.toString('utf8');
                        const lineCount = csvText.split('\n').filter(line => line.trim()).length - 1; // -1 for header
                        console.log('CSV export completed (' + sizeKB + 'KB, ' + chunkCount + ' chunks, ~' + lineCount + ' rows)');
                        
                        // Save file locally to project folder for verification
                        const projectSaveFilename = exportFilename || 'export.csv';
                        const projectSavePath = path.join(__dirname, '../../', 'downloaded-files', projectSaveFilename);
                        
                        // Create directory if it doesn't exist
                        const downloadDir = path.dirname(projectSavePath);
                        if (!fs.existsSync(downloadDir)) {
                            fs.mkdirSync(downloadDir, { recursive: true });
                        }
                        
                        // Save the raw CSV data to project folder
                        fs.writeFileSync(projectSavePath, csvBuffer);
                        console.log('File saved locally to: ' + projectSavePath);
                        
                        // Convert to base64 and output for UI capture
                        const base64Data = csvBuffer.toString('base64');
                        
                        console.log('DOWNLOAD_RESULT_START');
                        console.log('FILENAME:' + projectSaveFilename);
                        console.log('CONTENT:' + base64Data);
                        console.log('DOWNLOAD_RESULT_END');
                        
                        // Brief delay before exit to allow UI to process the completion
                        setTimeout(() => {
                            process.exit(0);
                        }, 1000);
                    });
                    
                    statusResponse.data.on('error', (err) => {
                        console.log('ERROR: Download error: ' + err.message);
                        setTimeout(() => {
                            process.exit(1);
                        }, 1000);
                    });
                    
                    // Set a timeout in case the stream never ends
                    setTimeout(() => {
                        console.log('ERROR: Download timeout');
                        process.exit(1);
                    }, 30000);
                    
                    return;
                }
                
            } catch (error) {
                if (error.response && error.response.status === 204) {
                    // Show animated loading indicator
                    const spinner = loadingChars[(attempts - 1) % loadingChars.length];
                    const elapsed = attempts * 3; // 3 seconds per attempt
                    
                    if (lastStatus !== 204) {
                        console.log('Export processing...');
                        lastStatus = 204;
                    } else if (attempts % 5 === 0) {
                        console.log('Still processing (' + elapsed + 's elapsed)');
                    }
                } else {
                    console.log('ERROR: Status check failed: ' + error.message);
                    if (error.response) {
                        console.log('ERROR: HTTP Status: ' + error.response.status);
                    }
                }
            }
            
            await new Promise(resolve => setTimeout(resolve, 3000));
        }
        
        console.log('ERROR: Export timed out after ' + attempts + ' attempts');
        
    } catch (error) {
        console.log('FATAL ERROR: ' + error.message);
    }
}

exportWorkflow();