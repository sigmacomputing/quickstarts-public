 import * as React from 'react';
  import { ISigmaEmbedProps } from './ISigmaEmbedProps';

  interface ISigmaEmbedState {
    embedUrl: string | undefined;
    loading: boolean;
    error: string | undefined;
  }

  export default class SigmaEmbed extends React.Component<ISigmaEmbedProps, ISigmaEmbedState> {

    constructor(props: ISigmaEmbedProps) {
      super(props);

      this.state = {
        embedUrl: undefined,
        loading: true,
        error: undefined
      };
    }

    public async componentDidMount(): Promise<void> {
      await this.loadSigmaEmbed();
    }

    private async loadSigmaEmbed(): Promise<void> {
      try {
        // Get current user email (or use the userDisplayName from props)
        const userEmail = this.props.context.pageContext.user.email || 'test@example.com';

        // Your Azure Function URL
        const functionUrl = `https://YOUR_FUNCTION_NAME.azurewebsites.net/api/HttpTrigger1?code=YOUR_FUNCTION_KEY&user=${encodeURIComponent(userEmail)}`;
        const response = await fetch(functionUrl);
        const data = await response.json();

        if (data.ok && data.embedUrl) {
          this.setState({
            embedUrl: data.embedUrl,
            loading: false
          });
        } else {
          this.setState({
            error: 'Failed to get embed URL',
            loading: false
          });
        }
      } catch (error) {
        this.setState({
          error: `Error: ${error.message}`,
          loading: false
        });
      }
    }

    public render(): React.ReactElement<ISigmaEmbedProps> {
      const { loading, embedUrl, error } = this.state;

      if (loading) {
        return <div>Loading Sigma workbook...</div>;
      }

      if (error) {
        return <div style={{color: 'red'}}>Error: {error}</div>;
      }

      if (embedUrl) {
        return (
          <div>
            <h3>Sigma Workbook for {this.props.userDisplayName}</h3>
            <iframe 
              src={embedUrl}
              width="100%"
              height="600px"
              style={{border: 'none'}}
              title="Sigma Workbook"
            />
          </div>
        );
      }

      return <div>No embed URL available</div>;
    }
  }
