import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const createLatency = new Trend('create_book_latency');
const getLatency = new Trend('get_book_latency');
const updateLatency = new Trend('update_book_latency');
const deleteLatency = new Trend('delete_book_latency');

const SERVICE_NAME = __ENV.SERVICE_NAME || 'bookcatalog-nd-app';
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080/api/books';
const VUS = parseInt(__ENV.VUS || '1');
const DURATION = __ENV.DURATION || '30s';
const WARMUP_ITERATIONS = parseInt(__ENV.WARMUP_ITERATIONS || '0');
const DATABASE_TYPE = __ENV.DATABASE_TYPE || 'sqlite';

export const options = {
  scenarios: {
    test: {
      executor: 'constant-vus',
      vus: VUS,
      duration: DURATION,
    },
  },
  thresholds: {
    'http_req_failed': ['rate<0.01'],
    'http_req_duration': ['p(95)<2000'],
  },
};

export function setup() {
  console.log(`Starting warm-up with ${WARMUP_ITERATIONS} iterations`);
  
  const headers = {
    'XDN': SERVICE_NAME,
    'Content-Type': 'application/json',
  };
  
  for (let i = 0; i < WARMUP_ITERATIONS; i++) {
    console.log(`Warm-up progress: ${i}/${WARMUP_ITERATIONS}`);
    
    const book = {
      title: `Warmup Book ${i}`,
      author: `Warmup Author ${i}`
    };
    
    const postResult = http.post(
      BASE_URL,
      JSON.stringify(book),
      { headers: headers }
    );
    
    check(postResult, {
      'Warm-up POST status is 200': (r) => r.status === 200,
    });
    
    const bookId = postResult.json('id');
    if (bookId) {
      sleep(0.1);
      
      const getResult = http.get(
        `${BASE_URL}/${bookId}`,
        { headers: headers }
      );
      
      check(getResult, {
        'Warm-up GET status is 200': (r) => r.status === 200,
      });
      
      sleep(0.1);
      
      const updatedBook = {
        title: `Updated Warmup Book ${i}`,
        author: `Updated Warmup Author ${i}`
      };
      
      const putResult = http.put(
        `${BASE_URL}/${bookId}`,
        JSON.stringify(updatedBook),
        { headers: headers }
      );
      
      check(putResult, {
        'Warm-up PUT status is 200': (r) => r.status === 200,
      });
      
      sleep(0.1);
      
      const deleteResult = http.del(
        `${BASE_URL}/${bookId}`,
        null,
        { headers: headers }
      );
      
      check(deleteResult, {
        'Warm-up DELETE status is 200': (r) => r.status === 200,
      });
      
      sleep(0.1);
    }
  }
  
  console.log('Warm-up complete. Starting actual test.');
  return {};
}

export default function () {
  const book = {
    title: `Test Book ${__VU}_${__ITER}`,
    author: `Test Author ${__VU}_${__ITER}`
  };

  const headers = {
    'XDN': SERVICE_NAME,
    'Content-Type': 'application/json',
  };

  const postResponse = http.post(
    BASE_URL,
    JSON.stringify(book),
    { headers: headers }
  );
  createLatency.add(postResponse.timings.duration);
  
  check(postResponse, {
    'POST status is 200': (r) => r.status === 200,
    'POST response has ID': (r) => r.json('id') !== null,
  });
  
  const bookId = postResponse.json('id');
  if (bookId) {
    sleep(0.1);

    const getResponse = http.get(
      `${BASE_URL}/${bookId}`,
      { headers: headers }
    );
    getLatency.add(getResponse.timings.duration);
    
    check(getResponse, {
      'GET status is 200': (r) => r.status === 200,
    });
    
    sleep(0.1);

    const updatedBook = {
      title: `Updated Test Book ${__VU}_${__ITER}`,
      author: `Updated Test Author ${__VU}_${__ITER}`
    };

    const putResponse = http.put(
      `${BASE_URL}/${bookId}`,
      JSON.stringify(updatedBook),
      { headers: headers }
    );
    updateLatency.add(putResponse.timings.duration);
    
    check(putResponse, {
      'PUT status is 200': (r) => r.status === 200,
    });
    
    sleep(0.1);

    const deleteResponse = http.del(
      `${BASE_URL}/${bookId}`,
      null,
      { headers: headers }
    );
    deleteLatency.add(deleteResponse.timings.duration);
    
    check(deleteResponse, {
      'DELETE status is 200': (r) => r.status === 200,
    });
    
    sleep(0.1);
  }
}

export function handleSummary(data) {
  let avgGetLatency = 0;
  let avgCreateLatency = 0;
  let avgUpdateLatency = 0;
  let avgDeleteLatency = 0;
  
  if (data.metrics.get_book_latency && data.metrics.get_book_latency.values) {
    avgGetLatency = data.metrics.get_book_latency.values.avg;
  } else {
    console.log("Warning: GET latency metrics not available");
  }
  
  if (data.metrics.create_book_latency && data.metrics.create_book_latency.values) {
    avgCreateLatency = data.metrics.create_book_latency.values.avg;
  } else {
    console.log("Warning: CREATE latency metrics not available");
  }
  
  if (data.metrics.update_book_latency && data.metrics.update_book_latency.values) {
    avgUpdateLatency = data.metrics.update_book_latency.values.avg;
  } else {
    console.log("Warning: UPDATE latency metrics not available");
  }
  
  if (data.metrics.delete_book_latency && data.metrics.delete_book_latency.values) {
    avgDeleteLatency = data.metrics.delete_book_latency.values.avg;
  } else {
    console.log("Warning: DELETE latency metrics not available");
  }
  
  const overallLatency = (avgGetLatency + avgCreateLatency + avgUpdateLatency + avgDeleteLatency) / 4;
  
  const csvHeader = "get_latency,create_latency,update_latency,delete_latency,overall_latency\n";
  const csvRow = `${avgGetLatency.toFixed(2)},${avgCreateLatency.toFixed(2)},${avgUpdateLatency.toFixed(2)},${avgDeleteLatency.toFixed(2)},${overallLatency.toFixed(2)}\n`;
  
  console.log(`\n=== BookCatalog Benchmark Results ===`);
  console.log(`GET avg: ${avgGetLatency.toFixed(2)}ms`);
  console.log(`CREATE avg: ${avgCreateLatency.toFixed(2)}ms`);
  console.log(`UPDATE avg: ${avgUpdateLatency.toFixed(2)}ms`);
  console.log(`DELETE avg: ${avgDeleteLatency.toFixed(2)}ms`);
  console.log(`Overall: ${overallLatency.toFixed(2)}ms`);
  
  const filename = `bookcatalog_results_${DATABASE_TYPE}_${Date.now()}.csv`;
  
  return {
    'stdout': `BookCatalog benchmark complete`,
    [filename]: csvHeader + csvRow,
  };
}
