# List Workbooks by Owner

## API Endpoints Used

- `GET /v2/workbooks?ownerId={memberId}` → [List Workbooks](https://help.sigmacomputing.com/reference/listworkbooks)

## Expected Output

- Table display of all workbooks owned by the specified member
- Workbook details including name, path, creation date, modification date, and version
- Summary count of total workbooks found

## Parameters

- **MEMBERID**: ID of the member whose workbooks to list

## Use Cases

- Audit workbooks owned by specific users
- Inventory management for user offboarding
- Track content creation by team members
- Generate ownership reports for compliance

## Important Notes

- Requires valid MEMBERID to specify the workbook owner
- Fetches all workbooks in a single request (no pagination needed)
- Returns comprehensive workbook metadata including dates and versions
- Filters results to show only workbooks owned by the specified member
- Generally returns small result sets since filtered by single owner