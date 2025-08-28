# Recent Workbooks

## API Endpoints Used

- `GET /v2/workbooks` → [List Workbooks](https://help.sigmacomputing.com/reference/listworkbooks)

## Expected Output

- List of workbooks accessible to the specified member
- Workbooks sorted by most recent access/modification
- Workbook details including name, ID, owner, and last updated timestamp

## Use Cases

- Track user activity and recently accessed content
- Audit individual user workbook access
- Generate user activity reports
- Monitor content usage patterns

## Important Notes

- Results are filtered to show only workbooks accessible to the specified MEMBERID
- Sorting is by most recent activity (access or modification)
- Includes both owned and shared workbooks