@isTest
private class SigmaJWTControllerTest {

    @isTest
    static void testGetSignedJWT() {
        // Test the main JWT generation method
        Test.startTest();
        String jwt = SigmaJWTController.getSignedJWT();
        Test.stopTest();

        // Verify JWT structure (header.payload.signature)
        System.assertNotEquals(null, jwt, 'JWT should not be null');
        List<String> jwtParts = jwt.split('\\.');
        System.assertEquals(3, jwtParts.size(), 'JWT should have 3 parts (header.payload.signature)');

        // Verify each part is not empty
        System.assert(jwtParts[0].length() > 0, 'JWT header should not be empty');
        System.assert(jwtParts[1].length() > 0, 'JWT payload should not be empty');
        System.assert(jwtParts[2].length() > 0, 'JWT signature should not be empty');
    }

    @isTest
    static void testBase64UrlEncode() {
        // Test base64 URL encoding for strings
        Test.startTest();
        String testString = 'Test String';
        String encoded = SigmaJWTController.base64UrlEncode(testString);
        Test.stopTest();

        // Verify encoding doesn't contain URL-unsafe characters
        System.assertNotEquals(null, encoded, 'Encoded string should not be null');
        System.assert(!encoded.contains('+'), 'Encoded string should not contain +');
        System.assert(!encoded.contains('/'), 'Encoded string should not contain /');
        System.assert(!encoded.contains('='), 'Encoded string should not contain =');
    }

    @isTest
    static void testBase64UrlEncodeBlob() {
        // Test base64 URL encoding for blobs
        Test.startTest();
        Blob testBlob = Blob.valueOf('Test Blob Data');
        String encoded = SigmaJWTController.base64UrlEncodeBlob(testBlob);
        Test.stopTest();

        // Verify encoding doesn't contain URL-unsafe characters
        System.assertNotEquals(null, encoded, 'Encoded blob should not be null');
        System.assert(!encoded.contains('+'), 'Encoded blob should not contain +');
        System.assert(!encoded.contains('/'), 'Encoded blob should not contain /');
        System.assert(!encoded.contains('='), 'Encoded blob should not contain =');
    }

    @isTest
    static void testGenerateRandomString() {
        // Test random string generation
        Test.startTest();
        String randomString8 = SigmaJWTController.generateRandomString(8);
        String randomString16 = SigmaJWTController.generateRandomString(16);
        Test.stopTest();

        // Verify string lengths
        System.assertEquals(8, randomString8.length(), 'Random string should be 8 characters');
        System.assertEquals(16, randomString16.length(), 'Random string should be 16 characters');

        // Verify strings are different (extremely unlikely to be same)
        System.assertNotEquals(randomString8, randomString16.substring(0, 8),
            'Random strings should be different');
    }

    @isTest
    static void testGenerateUUID() {
        // Test UUID generation
        Test.startTest();
        String uuid1 = SigmaJWTController.generateUUID();
        String uuid2 = SigmaJWTController.generateUUID();
        Test.stopTest();

        // Verify UUID format (8-4-4-4-12)
        System.assertNotEquals(null, uuid1, 'UUID should not be null');
        List<String> parts = uuid1.split('-');
        System.assertEquals(5, parts.size(), 'UUID should have 5 parts separated by dashes');
        System.assertEquals(8, parts[0].length(), 'First UUID part should be 8 characters');
        System.assertEquals(4, parts[1].length(), 'Second UUID part should be 4 characters');
        System.assertEquals(4, parts[2].length(), 'Third UUID part should be 4 characters');
        System.assertEquals(4, parts[3].length(), 'Fourth UUID part should be 4 characters');
        System.assertEquals(12, parts[4].length(), 'Fifth UUID part should be 12 characters');

        // Verify UUIDs are unique
        System.assertNotEquals(uuid1, uuid2, 'Generated UUIDs should be unique');
    }

    @isTest
    static void testGetAccountNames() {
        // Create test account data
        Account testAccount = new Account(
            Name = 'Cooper Industries Test'
        );
        insert testAccount;

        // Test account name retrieval
        Test.startTest();
        List<String> accountNames = SigmaJWTController.getAccountNames();
        Test.stopTest();

        // Verify results
        System.assertNotEquals(null, accountNames, 'Account names list should not be null');
        System.assertEquals(1, accountNames.size(), 'Should return 1 account name');
        System.assertEquals('Cooper', accountNames[0], 'Account name should be trimmed to "Cooper"');
    }

    @isTest
    static void testGetAccountNamesNoMatches() {
        // Test when no matching accounts exist
        // Note: We don't create any accounts with 'Cooper' in the name

        Test.startTest();
        List<String> accountNames = SigmaJWTController.getAccountNames();
        Test.stopTest();

        // Verify empty list is returned
        System.assertNotEquals(null, accountNames, 'Account names list should not be null');
        System.assertEquals(0, accountNames.size(), 'Should return 0 account names when no matches');
    }
}
