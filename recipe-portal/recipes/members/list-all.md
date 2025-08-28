# List All Members

## API Endpoints Used

- `GET /v2/members` → [List Members](https://help.sigmacomputing.com/reference/listmembers)

## Expected Output

- **Console Response Display**: Clean, structured member information in Response tab
- **Member Details**: Name, email, type, member ID, creation/update dates, status
- **Pagination Support**: Handles multiple pages automatically  
- **Summary**: Total count of members retrieved

## Parameters

- **LIMIT**: Number of results per page (max 1,000 per request)
- **MAX_PAGES**: Maximum number of pages to fetch (0 = all pages)

## Use Cases

- Generate complete organization user roster with pagination control
- Audit user accounts and permissions across large organizations
- Export member data for external systems with memory-efficient processing
- Get member IDs for other automation scripts

## Pagination Pattern

1. **First request**: Include `limit` parameter, no `page` parameter
2. **Subsequent requests**: Include both `limit` and `page` parameters  
3. **Page tokens**: Use `nextPage` value from response for next request
4. **Completion**: Stop when `hasMore` is false or no `nextPage` token

## Important Notes

- Uses Sigma's standard pagination pattern with `limit` and `page` parameters
- Page tokens are handled automatically by the script
- Maximum of 1,000 results per page enforced by Sigma API
- Includes both active and inactive members
- Member IDs are only accessible via API, not visible in Sigma UI
- Results displayed in clean console format for easy viewing

## ⚠️ Important Usage Notes

**This is a learning tool** designed to help you understand common Sigma API patterns. It is **not intended for production use**.

## Export Limitations & Recommendations

**Row Limits**:
- **Default**: 100,000 members (recommended for reliable downloads)
- **Maximum**: 1,000,000 members (Sigma API limit)
- **Portal Limit**: Single request only - no batching implemented

**Download Reliability**:
- Large downloads may timeout due to network limitations
- Organizations with >100K members may experience reliability issues
- For production use, implement proper batching patterns

**Batching Not Implemented**: This portal demonstrates single-request exports only. Production applications should implement batch processing for large datasets using:
- Multiple requests with proper pagination handling
- Proper error handling and retry logic
- Progress tracking across multiple API calls

**For Production Use**: 
- Implement proper batching for datasets >100K members
- Add timeout handling and retry mechanisms  
- Use proper pagination patterns for large organizations
- Consider data consistency implications during multi-request exports