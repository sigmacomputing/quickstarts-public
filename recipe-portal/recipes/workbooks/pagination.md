# Pagination

## API Endpoints Used

- `GET /v2/workbooks` → [List Workbooks](https://help.sigmacomputing.com/reference/listworkbooks)

## Expected Output

- Paginated workbook results formatted as a table
- Each page shows workbook name, path, and latest version
- Navigation information showing current page, total results, and pagination status
- Next page tokens for continued pagination

## Parameters

- **LIMIT**: Number of results per page (max 1,000 per request)
- **MAX_PAGES**: Maximum number of pages to fetch (0 = all pages)

## Use Cases

- Handle large workbook datasets efficiently with controlled page sizes
- Build paginated user interfaces for workbook browsing
- Manage memory usage when processing many workbooks
- Create structured reports with controlled data volume
- Process large datasets with memory-efficient pagination

## Pagination Pattern

1. **First request**: Include `limit` parameter, no `page` parameter
2. **Subsequent requests**: Include both `limit` and `page` parameters
3. **Page tokens**: Use `nextPage` value from response for next request
4. **Completion**: Stop when `hasMore` is false or no `nextPage` token

## Important Notes

- Uses Sigma's standard pagination pattern with `limit` and `page` parameters
- Page tokens are handled automatically by the script
- Maximum of 1,000 results per page enforced by Sigma API
- Results include pagination metadata displayed in console output