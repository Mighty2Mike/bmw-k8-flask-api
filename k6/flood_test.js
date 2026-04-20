/**
 * k6 Flood Test — Flask API on Minikube
 *
 * Install k6:  https://k6.io/docs/getting-started/installation/
 *
 * Run:
 *   k6 run k6/flood_test.js
 *
 * With env override (e.g. different base URL):
 *   k6 run -e BASE_URL=http://127.0.0.1:52345 k6/flood_test.js
 *
 * Output HTML report:
 *   k6 run --out json=results.json k6/flood_test.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

// ---------------------------------------------------------------------------
// Custom metrics
// ---------------------------------------------------------------------------
const errorRate   = new Rate("error_rate");
const apiDuration = new Trend("api_duration", true);
const stressHits  = new Counter("stress_endpoint_hits");

// ---------------------------------------------------------------------------
// Base URL — get from minikube service flask-api -n bmw-k8-flask-api --url
// ---------------------------------------------------------------------------
const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:16599";

// ---------------------------------------------------------------------------
// Load profile — simulates a realistic flood scenario in stages:
//
//  Stage 1 (warmup):    ramp from 0 → 10 VUs over 1 min
//  Stage 2 (sustained): hold 10 VUs for 2 min
//  Stage 3 (spike):     ramp to 50 VUs over 1 min  ← triggers HPA scale-up
//  Stage 4 (flood):     hold 50 VUs for 3 min      ← sustained pressure
//  Stage 5 (peak):      ramp to 100 VUs over 1 min ← maximum load
//  Stage 6 (hold):      hold 100 VUs for 2 min
//  Stage 7 (cooldown):  ramp down to 0 over 2 min  ← watch HPA scale-down
// ---------------------------------------------------------------------------
export const options = {
  stages: [
    { duration: "1m",  target: 10  }, // 1. Warmup
    { duration: "2m",  target: 10  }, // 2. Sustained baseline
    { duration: "1m",  target: 50  }, // 3. Spike — HPA should kick in
    { duration: "3m",  target: 50  }, // 4. Flood
    { duration: "1m",  target: 100 }, // 5. Peak load
    { duration: "2m",  target: 100 }, // 6. Hold peak
    { duration: "2m",  target: 0   }, // 7. Cooldown — watch scale-down
  ],
  thresholds: {
    // 95th percentile response time must be under 1s
    http_req_duration: ["p(95)<1000"],
    // Error rate must stay below 5%
    error_rate: ["rate<0.05"],
    // 99th percentile must be under 2s
    //"http_req_duration{percentile:99}": ["value<2000"],
    'http_req_duration': ['p(99)<2000']
  },
};

// ---------------------------------------------------------------------------
// Main test function — called once per VU per iteration
// ---------------------------------------------------------------------------
export default function () {
  const params = {
    headers: { "Content-Type": "application/json" },
    timeout: "10s",
  };

  // 70% of requests hit the normal data endpoint
  if (Math.random() < 0.7) {
    const res = http.get(`${BASE_URL}/api/v1/data`, params);

    const success = check(res, {
      "data endpoint: status 200":         (r) => r.status === 200,
      "data endpoint: has message field":  (r) => JSON.parse(r.body).message === "Success",
      "data endpoint: response < 500ms":   (r) => r.timings.duration < 500,
    });

    errorRate.add(!success);
    apiDuration.add(res.timings.duration);

  } else {
    // 30% hit the CPU-intensive stress endpoint — this drives CPU up
    // and triggers HPA horizontal scale-out
    const res = http.get(`${BASE_URL}/api/v1/stress`, params);

    const success = check(res, {
      "stress endpoint: status 200": (r) => r.status === 200,
    });

    errorRate.add(!success);
    stressHits.add(1);
  }

  // Health check on every iteration
  const health = http.get(`${BASE_URL}/health`, params);
  check(health, {
    "health: always 200": (r) => r.status === 200,
  });

  // Think time between requests (realistic user pacing)
  sleep(Math.random() * 0.5 + 0.1); // 0.1–0.6 seconds
}

// ---------------------------------------------------------------------------
// Summary — printed at end of test run
// ---------------------------------------------------------------------------
export function handleSummary(data) {
  return {
    stdout: JSON.stringify(
      {
        total_requests:    data.metrics.http_reqs.values.count,
        failed_requests:   data.metrics.http_req_failed.values.passes,
        error_rate_pct:    (data.metrics.error_rate?.values.rate * 100).toFixed(2) + "%",
        avg_duration_ms:   data.metrics.http_req_duration.values.avg.toFixed(2),
        p95_duration_ms:   data.metrics.http_req_duration.values["p(95)"].toFixed(2),
        p99_duration_ms:   data.metrics.http_req_duration.values["p(99)"].toFixed(2),
        peak_rps:          data.metrics.http_reqs.values.rate.toFixed(2),
      },
      null,
      2
    ),
  };
}
