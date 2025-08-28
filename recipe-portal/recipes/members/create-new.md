# Create New Member

## API Endpoints Used

- `GET /v2/members?search={email}` → [List Members](https://help.sigmacomputing.com/reference/listmembers)
- `GET /v2/accountTypes` → [List Account Types](https://help.sigmacomputing.com/reference/listaccounttypes)
- `POST /v2/members` → [Create Member](https://help.sigmacomputing.com/reference/createmember)

## Expected Output

- Email verification check results
- New member creation confirmation with generated memberId
- Complete user profile of newly created member

## Use Cases

- Onboard new employees to Sigma
- Programmatically create user accounts
- Bulk user provisioning workflows
- Integration with HR systems

## Important Notes

- Script first verifies email doesn't already exist to prevent duplicates
- Member type dropdown dynamically loads available account types from your Sigma organization
- Requires complete user information: email, first name, last name, account type
- Email is automatically generated with timestamp to ensure uniqueness
- Returns the new memberId for use in subsequent operations