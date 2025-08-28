# Export Workbook PDF

## API Endpoints Used

- `POST /v2/workbooks/{workbookId}/export` → [Export Workbook](https://help.sigmacomputing.com/reference/exportworkbook)
- `GET /v2/query/{queryId}/download` → [Download Exported File](https://help.sigmacomputing.com/reference/downloadquery)

## Output Location

- **Local File**: Also saved to recipe-portal/downloaded-files/export.pdf

## Expected Output

- Export job initiation confirmation
- Progress monitoring during export processing
- PDF file download when export completes

## Use Cases

- Generate presentation-ready reports for stakeholders
- Create offline copies of dashboard data
- Schedule automated report distribution
- Archive workbook snapshots

## Important Notes

- Export includes entire workbook in portrait layout
- Process may take time depending on workbook complexity
- Requires valid WORKBOOK_ID in environment variables

## ⚠️ Important Usage Notes

**This is a learning tool** designed to help you understand common Sigma API patterns. It is **not intended for production use**.

## Export Limitations & Recommendations

**File Size Limits**:
- **Recommended**: Workbooks under 10MB for reliable downloads
- **Large Files**: May experience reliability issues or timeout
- **Portal Limit**: Single request only - no batching implemented

**Download Reliability**:
- Large PDF exports may timeout due to network limitations
- Complex workbooks with many pages may experience reliability issues
- For production use, implement proper timeout handling and retry logic

**For Production Use**: 
- Implement proper error handling and retry mechanisms  
- Use Sigma's web interface for large operational exports
- Consider breaking large workbooks into smaller sections
- Add timeout handling for network reliability