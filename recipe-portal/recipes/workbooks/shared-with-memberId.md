# Shared with Member ID

## API Endpoints Used

- `GET /v2/workbooks` → [List Workbooks](https://help.sigmacomputing.com/reference/listworkbooks)

## Expected Output

- List of workbook names, URLs, and version numbers
- Filtered to show only workbooks shared with the specified member
- Tabular format for easy reading and analysis

## Use Cases

- Audit content shared with specific users
- Generate personalized workbook lists for users
- Track workbook access and sharing patterns
- Create user-specific content inventories

## Important Notes

- Results filtered by MEMBERID in environment variables
- Shows both directly shared and team-shared workbooks
- Includes workbook version information for tracking changes
- Useful for access auditing and compliance reporting