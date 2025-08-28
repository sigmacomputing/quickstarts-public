# List All Workbooks with Details

## API Endpoints Used

- `GET /v2/workbooks` → [List Workbooks](https://help.sigmacomputing.com/reference/listworkbooks)

## Expected Output

- **Console Response Display**: Clean, structured workbook information in Response tab
- **Workbook Details**: Name, URL, URL ID, path, version, creation/update dates, owner ID
- **Pagination Support**: Handles multiple pages automatically
- **Summary**: Total count of workbooks retrieved

## Use Cases

- Generate complete workbook inventory
- Audit all analytical content in organization
- Export workbook metadata for reporting
- Get workbook IDs for other automation scripts

## Important Notes

- Returns all workbooks visible to the authenticated user
- Includes both active and archived workbooks
- URL ID can be used to construct direct workbook links

## ⚠️ Important Usage Notes

**This is a learning tool** designed to help you understand common Sigma API patterns. It is **not intended for production use**.

## Export Limitations & Recommendations

**Row Limits**:
- **Default**: 100,000 workbooks (recommended for reliable downloads)
- **Maximum**: 1,000,000 workbooks (Sigma API limit)
- **Portal Limit**: Single request only - no batching implemented

**Download Reliability**:
- Large downloads may timeout due to network limitations
- Organizations with >100K workbooks may experience reliability issues
- For production use, implement proper batching patterns

**Batching Not Implemented**: This portal demonstrates single-request exports only. Production applications should implement batch processing for large datasets using:
- Multiple requests with proper pagination handling
- Proper error handling and retry logic
- Progress tracking across multiple API calls

**For Production Use**: 
- Implement proper batching for datasets >100K workbooks
- Add timeout handling and retry mechanisms  
- Use proper pagination patterns for large organizations
- Consider data consistency implications during multi-request exports