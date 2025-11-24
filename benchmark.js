import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.1/index.js';

function loadEnvFile(path = '.env') {
  try {
    const content = open(path);
    return content.split(/\r?\n/).reduce((acc, line) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) {
        return acc;
      }
      const idx = trimmed.indexOf('=');
      if (idx === -1) {
        return acc;
      }
      const key = trimmed.slice(0, idx).trim();
      const value = trimmed
        .slice(idx + 1)
        .trim()
        .replace(/^['"]|['"]$/g, '');
      if (key) {
        acc[key] = value;
      }
      return acc;
    }, {});
  } catch (e) {
    return {};
  }
}

const envFile = loadEnvFile();

const createLatency = new Trend('create_book_latency');
const getLatency = new Trend('get_book_latency');
const updateLatency = new Trend('update_book_latency');
const deleteLatency = new Trend('delete_book_latency');

const SERVICE_NAME = __ENV.SERVICE_NAME || envFile.SERVICE_NAME || 'bookcatalog-nd-app';
const BASE_URL = __ENV.BASE_URL || envFile.BASE_URL || 'http://localhost:8081/api/books'; 
const VUS = parseInt(__ENV.VUS || envFile.VUS || '1');
const DURATION = __ENV.DURATION || envFile.DURATION || '30s';
const WARMUP_ITERATIONS = parseInt(__ENV.WARMUP_ITERATIONS || envFile.WARMUP_ITERATIONS || '0');
const DATABASE_TYPE = __ENV.DATABASE_TYPE || envFile.DATABASE_TYPE || 'sqlite';

console.log(`Configured with VUS=${VUS}, DURATION=${DURATION}, WARMUP_ITERATIONS=${WARMUP_ITERATIONS}, DATABASE_TYPE=${DATABASE_TYPE}`);
console.log(`Target Service: ${SERVICE_NAME}`);
console.log(`Base URL: ${BASE_URL}`);

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
  const timestamp = Date.now();
  const csvFilename = `bookcatalog_results_${DATABASE_TYPE}_${timestamp}.csv`;
  
  console.log(`\n=== Starting Benchmark ===`);
  console.log(`Target Log File: ${csvFilename}`);
  
  if (WARMUP_ITERATIONS > 0) {
    console.log(`Starting warm-up with ${WARMUP_ITERATIONS} iterations...`);
    
    const headers = {
      'XDN': SERVICE_NAME,
      'Content-Type': 'application/json',
    };
    
    for (let i = 0; i < WARMUP_ITERATIONS; i++) {
      const book = {
        title: `Warmup Book ${i}`,
        author: `Warmup Author ${i}`
      };
      
      const postResult = http.post(BASE_URL, JSON.stringify(book), { headers: headers });
      const bookId = postResult.json('id');
      
      if (bookId) {
        http.get(`${BASE_URL}/${bookId}`, { headers: headers });
        
        const updatedBook = { title: `Warmup Update ${i}`, author: `Warmup Update ${i}` };
        http.put(`${BASE_URL}/${bookId}`, JSON.stringify(updatedBook), { headers: headers });
        
        http.del(`${BASE_URL}/${bookId}`, null, { headers: headers });
      }
    }
    console.log('Warm-up complete.');
  }

  return { filename: csvFilename };
}

export default function (data) {
  const book = {
    title: `Test Book ${__VU}_${__ITER}`,
    author: `Test Author ${__VU}_${__ITER}`
  };

  const headers = {
    'XDN': SERVICE_NAME,
    'Content-Type': 'application/json',
    'X-Log-Filename': data.filename, 
  };

  // CREATE (POST)
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

    // READ (GET)
    const getResponse = http.get(
      `${BASE_URL}/${bookId}`,
      { headers: headers }
    );
    getLatency.add(getResponse.timings.duration);
    
    check(getResponse, {
      'GET status is 200': (r) => r.status === 200,
    });
    
    sleep(0.1);

    // UPDATE (PUT)
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

    // DELETE (DEL)
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
  console.log(`\n=== BookCatalog Benchmark Summary ===`);
  console.log(`VUs: ${VUS}, Duration: ${DURATION}`);
  
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
  };
}
