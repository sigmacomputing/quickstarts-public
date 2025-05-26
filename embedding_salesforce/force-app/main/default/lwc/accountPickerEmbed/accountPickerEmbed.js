import { LightningElement, track } from 'lwc';
import getAccountNames from '@salesforce/apex/SigmaJWTController.getAccountNames';
import getSignedJWT from '@salesforce/apex/SigmaJWTController.getSignedJWT';

export default class AccountPickerEmbed extends LightningElement {
    @track accountOptions = [];
    @track selectedAccount;
    @track iframeUrl;
    jwt;

connectedCallback() {
    getAccountNames()
        .then(result => {
            this.accountOptions = result.map(name => ({
                label: name,
                value: name
            }));
            console.log('Account options loaded:', this.accountOptions);
        })
        .catch(error => {
            console.error('Account load failed:', error);
        });

    getSignedJWT()
        .then(jwt => {
            console.log('JWT received:', jwt);
            this.jwt = jwt;
        })
        .catch(error => {
            console.error('JWT fetch failed:', error);
        });
}

handleChange(event) {
    this.selectedAccount = event.detail.value;

    const baseUrl = 'https://app.sigmacomputing.com/{YOUR_ORG_SLUG}/workbook';
    const workbookSlug = 'Use-Case-Embed-into-Salesforce-QuickStart-{YOUR_WORKBOOK_ID}';
    const controlParam = '&SF_AccountName=' + encodeURIComponent(this.selectedAccount);
    const cacheBuster = '&_ts=' + Date.now();

    // Important: :embed=true and :jwt must come immediately after ?
    this.iframeUrl = `${baseUrl}/${workbookSlug}?:embed=true&:jwt=${this.jwt}${controlParam}${cacheBuster}`;
    console.log('Final iframe URL:', this.iframeUrl);
}
}

