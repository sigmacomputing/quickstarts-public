import React, { 
  useState, 
  useEffect } from 'react';

// Highcharts packages
import Highcharts, { dateFormat } from 'highcharts/highcharts-gantt';
import HighchartsReact from 'highcharts-react-official';

// Sigma packages
import { client, useConfig, useElementData } from "@sigmacomputing/plugin";

// configure this for sigma
client.config.configureEditorPanel([
  { name: "source", type: "element" },
  { name: "work orders", type: "column", source: "source", allowMultiple: false },
  { name: "operations", type: "column", source: "source", allowMultiple: false },
  { name: "operation start dates", type: "column", source: "source", allowMultiple: false },
  { name: "operation end dates", type: "column", source: "source", allowMultiple: false },
]);

const sigmaObjectBuilder = (wos, ops, starts, ends) => {
  // sort all of the input arrays the same way
  // loop through any of these by length, push to a temp array an objeect of wo, op, start, end
  let list = [];
  for (let i = 0; i < wos.length; i++) {
    list.push({
      start: starts[i],
      end: ends[i],
      wono: wos[i],
      op: ops[i]
    })
  }

  // sort it based on start time
  list.sort((a, b) => a.start - b.start);

  // separate and assign these values back to their original arrays
  for (let i = 0; i < list.length; i++) {
    starts[i] = list[i].start;
    ends[i] = list[i].end;
    wos[i] = list[i].wono;
    ops[i] = list[i].op;
  }

  // obj = { wono, operation, start_time, end_time}. each being an array.
  let obj = {
    wono: wos,
    operation: ops,
    start_time: starts,
    end_time: ends 
  }
  
  return obj;
}

const sigmaSeriesBuilder = (wos, ops, starts, ends) => {
  
  // first, get the object built and sorted properly
  const obj = sigmaObjectBuilder(wos, ops, starts, ends);


  // second, create the series array from this
  let arr = [];
  let i = 0;

  // declare prev_wono and newObj outside
  let prev_wono;
  let newObj;
  
  while (i < obj.wono.length) {

    // base case for the first wono
    if (!prev_wono) {
      prev_wono = obj.wono[i];
      newObj = {
        name: prev_wono,
        data: [],
      }

      // Push the first item into the data array
      newObj.data.push({
        name: 'Total Duration',
        pointWidth: 3,
        start: obj.start_time[0],
        end: obj.end_time.reduce((a, b) => a > b ? a : b) // get the greatest max
      })
    }
    
    // Create data object that will be pushed to data array
    let dataObj = {
      name: obj.operation[i],
      start: obj.start_time[i],
      end: obj.end_time[i],
      y: i + 1
    }
    // add the new data object to the array
    newObj.data.push(dataObj);
    i++;
  }

  // push last newObj to the arr
  arr.push(newObj)
  return arr;
}

const getGanttPayload = (config, sigmaData) => {
  // destructure config and rename the values
  const {
    source,
    'work orders': key_work_orders,
    'operations': key_operations,
    'operation start dates': key_ops_start,
    'operation end dates': key_ops_end
  } = config;

  if (!source || !key_work_orders || !key_operations || !key_ops_start || !key_ops_end || Object.keys(sigmaData).length === 0) return null;
  
  // build the series that will feed into the Gantt chart
  const series = sigmaSeriesBuilder(sigmaData[key_work_orders], sigmaData[key_operations], sigmaData[key_ops_start], sigmaData[key_ops_end]);

  if (series) {
    var newOptions = {
      series: series,
      tooltip: {
        pointFormat: '<span>Operation: {point.name}</span><br/><span>From: {point.start:%b %e, %I:%M %P}</span><br/><span>To: {point.end:%b %e, %I:%M %P}</span>'
      },
      navigator: {
        enabled: true,
      },
      scrollbar: {
        enabled: true
      },
      rangeSelector: {
        enabled: true,
      },
      yAxis: {
        type: 'category',
        grid: {
          columns: [{
            title: {
              text: 'Operation'
            },
            categories: series[0].data.map((s) => {
              return s.name;
            })
          }, {
            title: {
              text: 'Operation Start'
            }, 
            categories: series[0].data.map((s) => {
              return dateFormat('%b %e, %I:%M %P', s.start);
            })
          }, {
            title: {
              text: 'Operation End'
            },
            categories: series[0].data.map((s) => {
              return dateFormat('%b %e, %I:%M %P', s.end);
            })
          }]
        }
      },
    }

    return newOptions;
  }

  // else, return null
  return null;
}

// Function to check if the config file returned back data
const allDimensions = (config) => { 
  if (!config['operations'] || !config['work orders'] || !config['operation start dates'] || !config['operation end dates']) {
    return false;
  }
  return true;
}

// Refer to https://github.com/ja2z/sigma-sample-plugins/blob/main/narrativescience-quill/src/App.js
const useGetGanttData = () => {
  const config = useConfig();
  const sigmaData = useElementData(config.source);
  const [res, setRes] = useState(null);

  useEffect(() => {
    if (!allDimensions(config)) return null;

    setRes(getGanttPayload(config, sigmaData));

  }, [config, sigmaData]);

  return res;
}

// This will be the new app declaration
const App = () => {
  const res = useGetGanttData();
  return (
    res && <HighchartsReact highcharts={Highcharts} constructorType={"ganttChart"} options={res}/>
  );
}
export default App;