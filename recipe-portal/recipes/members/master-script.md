# Master Script

## API Endpoints Used
This script orchestrates multiple member management operations by calling other scripts in sequence.

## Expected Output

- Sequential execution results from each called script
- Comprehensive member onboarding workflow completion
- Status updates for each step in the process

## Use Cases

- Complete new member onboarding workflow
- Automated user provisioning with full setup
- Consistent multi-step user configuration
- Template for complex member management operations

## Important Notes

- ⚠️ Requires manual creation of new member first using create-new.js
- Must update .env with returned memberId before running this script
- Executes multiple scripts in predetermined order
- Each step depends on successful completion of previous steps