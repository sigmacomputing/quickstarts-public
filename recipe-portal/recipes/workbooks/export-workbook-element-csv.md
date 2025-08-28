# Export Workbook Element CSV

## IMPORTANT USAGE NOTE:
In order for the data filtering to work, the workbook MUST have a date range page control with an ID of `API-Date-Filter`. 

Date filtering will not work without this!

## API Endpoints Used

- `POST /v2/workbooks/{workbookId}/export` → [Export Workbook](https://help.sigmacomputing.com/reference/exportworkbook)
- `GET /v2/query/{queryId}/download` → [Download Exported File](https://help.sigmacomputing.com/reference/downloadquery)

## Output Location

- CSV file saved to `recipe-portal/downloaded-files/{filename given}`
- Filename based on workbook and element being exported

## Expected Output

- Export job initiation confirmation with date range parameters
- Progress monitoring during export processing  
- CSV file download when export completes

## Use Cases

- Extract specific table or chart data for analysis
- Generate CSV exports for external systems
- Create data extracts with custom date filtering
- Automate data export workflows

## Important Notes

- Exports specific workbook element (table/chart) rather than entire workbook
- Supports date range parameters for filtered exports
- Requires valid WORKBOOK_ID and ELEMENT_ID in environment variables

## ⚠️ Important Usage Notes

**This is a learning tool** designed to help you understand common Sigma API patterns. It is **not intended for production use**.

## Export Limitations & Recommendations

**Row Limits**:
- **Default**: 100,000 rows (recommended for reliable downloads)
- **Maximum**: 1,000,000 rows (Sigma API limit)
- **Portal Limit**: Single request only - no batching implemented

**Download Reliability**:
- Large downloads may timeout due to network limitations
- Files >100K rows may experience reliability issues
- For production use, implement proper batching patterns

**Batching Not Implemented**: This portal demonstrates single-request exports only. Production applications should implement batch processing for large datasets using:
- Multiple requests with `rowLimit` and `offset` parameters
- Proper error handling and retry logic
- Progress tracking across multiple API calls

**For Production Use**: 
- Implement proper batching for datasets >100K rows
- Add timeout handling and retry mechanisms  
- Use Sigma's web interface for large operational exports
- Consider data consistency implications during multi-request exports