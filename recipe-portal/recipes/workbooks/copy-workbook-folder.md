# Copy Workbook Folder

## API Endpoints Used

- `POST /v2/workbooks/{workbookId}/copy` → [Copy Workbook](https://help.sigmacomputing.com/reference/copyworkbook)
- `GET /v2/members/{memberId}` → [Get Member Details](https://help.sigmacomputing.com/reference/getmember)

## Expected Output

- Confirmation of successful workbook folder copy operation
- Details of source and destination folder locations
- New folder ID and path information

## Use Cases

- Duplicate workbook folders for different environments
- Create backup copies of important workbook collections
- Set up template folders for new projects or teams
- Organize content across different workspace structures

## Important Notes

- Copies entire folder structure including all contained workbooks
- Requires valid WORKBOOK_ID (folder) and MEMBERID (destination owner)
- Preserves folder hierarchy and workbook relationships
- New owner gets full control over copied content