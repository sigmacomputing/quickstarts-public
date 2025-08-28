// Title: Export Workbook PDF
// Description: This script triggers an export to PDF job with date range parameters, and downloads the export once ready. The export will be the entire workbook in PDF format.
//
// PREREQUISITES:
// - Target workbook must exist and be accessible
// - For date filtering: Workbook must have a page control with ID "API-Date-Filter"
//   (Control ID can be found in workbook edit mode > select control > Properties panel)
// - Workbook pages must be compatible with PDF export format

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

async function initiateExport(accessToken) {
    const exportOptions = {
       workbookId: workbookId,
       format: { type: 'pdf', layout: 'portrait' },
    };


    try {
        const response = await axios.post(
            baseURL + '/workbooks/' + workbookId + '/export',
            exportOptions,
            { headers: { Authorization: 'Bearer ' + accessToken, 'Content-Type': 'application/json' } }
        );
        
        const queryId = response.data.queryId;
        if (!queryId) {
            console.log('ERROR: No queryId received from export API');
            return null;
        }
        
        // Direct output that bypasses all wrapper issues
        process.stderr.write('DIRECT_LOG: Export initiated - QueryID: ' + queryId + '\n');
        process.stderr.write('DIRECT_LOG: QueryID Type: ' + typeof queryId + '\n');
        process.stderr.write('DIRECT_LOG: QueryID Length: ' + (queryId ? queryId.length : 'null') + '\n');
        
        console.log('Export initiated - QueryID: ' + queryId);
        return queryId;
    } catch (error) {
        console.log('ERROR: Failed to initiate export: ' + error.message);
        return null;
    }
}

async function checkExportReady(queryId, accessToken) {
    console.log('Waiting for export to complete...');
    const downloadUrl = baseURL + '/query/' + queryId + '/download';
    
    let attempts = 0;
    let lastStatus = null;
    
    while (attempts < 20) {
        attempts++;
        
        try {
            const statusResponse = await axios.get(downloadUrl, {
                headers: { Authorization: 'Bearer ' + accessToken },
                responseType: 'stream'
            });
            
            if (statusResponse.status === 200) {
                console.log('Export ready! Downloading...');
                return statusResponse.data;
            }
            
        } catch (error) {
            if (error.response && error.response.status === 204) {
                // Show periodic progress updates without spinner complexity
                if (lastStatus !== 204) {
                    console.log('Export processing...');
                    lastStatus = 204;
                } else if (attempts % 5 === 0) {
                    console.log('Still processing... (' + (attempts * 3) + 's elapsed)');
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
    return null;
}

async function exportWorkflow() {
    try {
        console.log('Authenticating...');
        const accessToken = await getBearerToken();
        if (!accessToken) {
            console.log('ERROR: Authentication failed');
            return;
        }
        console.log('Authentication successful');

        console.log('Initiating PDF export...');
        const queryId = await initiateExport(accessToken);
        if (!queryId) {
            console.log('ERROR: Failed to initiate export or obtain queryId');
            return;
        }

        const data = await checkExportReady(queryId, accessToken);
        if (data) {
            // Capture the PDF data as binary chunks
            let pdfChunks = [];
            data.on('data', (chunk) => {
                pdfChunks.push(chunk);
            });
            
            data.on('end', () => {
                // Combine all chunks into a single buffer
                const pdfBuffer = Buffer.concat(pdfChunks);
                const sizeKB = Math.round(pdfBuffer.length / 1024);
                console.log('Downloaded PDF: ' + sizeKB + 'KB');
                
                // Save file locally to project folder for verification
                const projectSaveFilename = 'export.pdf';
                const projectSavePath = path.join(__dirname, '../../', 'downloaded-files', projectSaveFilename);
                
                // Create directory if it doesn't exist
                const downloadDir = path.dirname(projectSavePath);
                if (!fs.existsSync(downloadDir)) {
                    fs.mkdirSync(downloadDir, { recursive: true });
                }
                
                // Save the raw PDF data to project folder
                fs.writeFileSync(projectSavePath, pdfBuffer);
                console.log('File saved locally to: ' + projectSavePath);
                
                // Convert to base64 and output for UI capture
                const base64Data = pdfBuffer.toString('base64');
                const filename = 'export.pdf';
                
                console.log('DOWNLOAD_RESULT_START');
                console.log('FILENAME:' + filename);
                console.log('CONTENT:' + base64Data);
                console.log('DOWNLOAD_RESULT_END');
                console.log('Export completed successfully');
                
                // Brief delay before exit to allow UI to process the completion
                setTimeout(() => {
                    process.exit(0);
                }, 1000);
            });
            
            data.on('error', (err) => {
                console.log('ERROR: Download error: ' + err.message);
                setTimeout(() => {
                    process.exit(1);
                }, 1000);
            });
        } else {
            console.log('ERROR: Failed to prepare the export for download');
        }
        
    } catch (error) {
        console.log('FATAL ERROR: ' + error.message);
    }
}

exportWorkflow();