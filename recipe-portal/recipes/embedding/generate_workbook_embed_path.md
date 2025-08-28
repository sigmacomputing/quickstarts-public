# Generate Workbook Embed Path

## API Endpoints Used

- `POST /v2/workbooks/{workbookId}/embed` → [Create Workbook Embed](https://help.sigmacomputing.com/reference/createworkbookembed)

## Expected Output

- Generated embed URL for the specified workbook
- URL parameters for member-specific embedding
- Embed path ready for integration into applications

## Use Cases

- Generate secure embed URLs for external applications
- Create member-specific embedded analytics experiences
- Integrate Sigma workbooks into custom applications
- Build embedded analytics solutions with user context

## Important Notes

- Requires valid MEMBERID for user-specific embedding
- Generated URLs include security parameters for authentication
- Embed URLs are time-limited for security purposes
- Essential for embedded analytics implementations