// This file is part of the Salesforce Lightning Web Component (LWC) framework.
import { LightningElement, track } from 'lwc';

// Importing the Apex method to get the signed JWT
import getSignedJWT from '@salesforce/apex/SigmaJWTController.getSignedJWT';

// This component is responsible for embedding a Sigma workbook in an iframe
export default class SigmaEmbed extends LightningElement {
    @track iframeUrl;

// This method is called when the component is inserted into the DOM
connectedCallback() {
    getSignedJWT()
        .then(jwt => {
            const baseUrl = 'https://app.sigmacomputing.com/{YOUR_ORG_SLUG}/workbook';
            const workbookSlug = 'Use-Case-Embed-into-Salesforce-QuickStart-{YOUR_WORKBOOK_ID}';
            const cacheBuster = `&_ts=${Date.now()}`;
            this.iframeUrl = `${baseUrl}/${workbookSlug}?:embed=true&:jwt=${jwt}${cacheBuster}`;
        })
        .catch(error => {
            console.error('Failed to fetch JWT:', error);
        });
 }
}

