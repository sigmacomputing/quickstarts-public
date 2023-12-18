import React, {
  useState,
  useEffect,
  useMemo
} from 'react';

// Sigma Packages
import { client, useConfig, useElementData } from '@sigmacomputing/plugin';

// Highcharts Packages
import Highcharts from 'highcharts/highstock';
import HighchartsReact from 'highcharts-react-official';

// -------------------------------------------------------

// Set up Sigma Client Config
client.config.configureEditorPanel([
  { name: "source", type: "element"},
  { name: "open", type: "column", source: "source", allowMultiple: false},
  { name: "high", type: "column", source: "source", allowMultiple: false},
  { name: "low", type: "column", source: "source", allowMultiple: false},
  { name: "close", type: "column", source: "source", allowMultiple: false},
  { name: "date", type: "column", source: "source", allowMultiple: false},
  { name: "volume", type: "column", source: "source", allowMultiple: false},
  { name: "symbol", type: "column", source: "source", allowMultiple: false}
]);

/**
 * Data Processing:
 * allData - conditional check to make sure all the necessary data has been received from Sigma.
 * getData - creates the data series for Highcharts and returns the required data object.
 * dateAscendingAlert - returns a console log error if the source table date column isn't sorted 
 * in ascending order.
*/

const allData = (config, sigmaData) => {
  if (!sigmaData[config['open']] 
  && !sigmaData[config['high']] 
  && !sigmaData[config['low']] 
  && !sigmaData[config['close']] 
  && !sigmaData[config['date']] 
  && !sigmaData[config['volume']] 
  && !sigmaData[config['symbol']]) {
    return false;
  }
  return true;
}

const datesAscendingAlert = (config, sigmaData) => {
  if (sigmaData[config['date']][0] > sigmaData[config['date']][1]) {
    console.log('ERROR:\nDate column is not sorted in ascending order!\nSort the Date column in ascending order to correct output.');
  }
}  

const getData = (config, sigmaData) => {

  // Conditional to see if we have the config and element data from Sigma.
  // If we have both, proceed with creating the output object
  if (allData(config, sigmaData)) {

    // Conditional to make sure that the input data is sorted by date in ascending order
    // If graph looks off, check console
    datesAscendingAlert(config, sigmaData);
    // Create the series array in the format: date, open, high, low, close
    const series = sigmaData[config['date']].map((val, i) => {
      return [
        val, 
        sigmaData[config['open']][i], 
        sigmaData[config['high']][i], 
        sigmaData[config['low']][i], 
        sigmaData[config['close']][i]
      ]
    });

    // Create the output object for the candlestick chart
    return {
      chart: {
        animation: false,
        type: 'candlestick'
      },
      rangeSelector: {
        enabled: true,
        animation: false
      },
      navigator: {
        enabled: true
      },
      scrollbar: {
        enabled: true,
      },
      series: [{
        step: 'center',
        name: sigmaData[config['symbol']][0],
        data: series,
        type: "candlestick",
      }],
    }
  } 
}


/** 
 *Main Function Wrapper 
*/

const useMain = () => {
  
  // Receive config and element data objects from Sigma
  const config = useConfig();
  const sigmaData = useElementData(config.source);

  // Process the data from Sigma and memoize result
  const payload = useMemo(() => getData(config, sigmaData), [config, sigmaData]);

  // Result object that will be used in Highcharts
  const [res, setRes] = useState(null);

  // call useEffect hook to re-render when the payload has changed depending on input data
  useEffect(() => {
    setRes(payload);  
  }, [payload])

  return res;
}

const App = () => {
  const options = useMain();
  return (
    options && <HighchartsReact highcharts={Highcharts} constructorType={"stockChart"} options={options} />
  );
}

export default App;
