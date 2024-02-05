import React from 'react';
import Highcharts from 'highcharts/highstock';
import HighchartsReact from 'highcharts-react-official';

const App = () => {
  // Hardcoded sample data
  const sampleData = [
    [Date.UTC(2023, 0, 1), 7.0, 7.5, 6.5, 7.2],
    [Date.UTC(2023, 0, 2), 7.2, 7.8, 7.1, 7.7],
    [Date.UTC(2023, 0, 3), 7.7, 8.3, 7.7, 8.0],
    [Date.UTC(2023, 0, 4), 8.0, 8.6, 7.9, 8.4],
    [Date.UTC(2023, 0, 5), 8.4, 9.0, 8.3, 8.9],
  ];

  // Highchart configuration
  const options = {
    chart: {
      type: 'candlestick'
    },
    rangeSelector: {
      selected: 1
    },
    title: {
      text: 'Hardcoded Stock Prices - Highchart.js Candlestick'
    },
    series: [{
      name: 'Stock Price',
      data: sampleData,
      tooltip: {
        valueDecimals: 2
      }
    }]
  };

  return (
    <HighchartsReact
      highcharts={Highcharts}
      constructorType={'stockChart'}
      options={options}
    />
  );
}

export default App;
