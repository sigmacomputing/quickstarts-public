const jwt = require('jsonwebtoken');

// Your JWT token
const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IjFjOGNkMTFmOTAwZmYyNTg0ODkzMTFlYTQ0YTlmZmU2Y2U5ZDhhM2ZiYzNjM2M1NGI4ZGQyNTcxZWJkYmIxZTQifQ.eyJzdWIiOiJlbWJlZF91c2VyQHRlc3QuY29tIiwianRpIjoiZjc1NmEzODQtZDQ2NC00MjIxLThmZDAtZjg5ODZiOWMzZGU4IiwiaWF0IjoxNzIzNzU1MjY5LCJleHAiOjE3MjM3NTg4NjksImFjY291bnRfdHlwZSI6ImxpdGUiLCJ0ZWFtcyI6WyJTYWxlc19QZW9wbGUiXX0.-mYuRbihObehdoA1KOmMUnMVSMiZy9mTfrJWA3spaU8';

// Decode the JWT without verifying the signature
const decoded = jwt.decode(token, { complete: true });

console.log(decoded);