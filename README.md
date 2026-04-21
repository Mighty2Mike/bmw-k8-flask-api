# Flask K8s Assessment — Local HA Deployment on Minikube

A production-grade Flask REST API deployed onto a local Minikube cluster using
Terraform (IaC) and Helm, demonstrating horizontal & vertical autoscaling,
secrets management, and flood-test-driven scale validation.

---

## Architecture

```
Windows (Local Dev)
└── Minikube (local K8s cluster)
      └── Namespace: bmw-k8-flask-api
            ├── ConfigMap          — non-sensitive app config
            ├── Secret             — sensitive credentials (base64-encoded)
            ├── Deployment         — Flask API pods (rolling update strategy)
            │     ├── Pod 1 (flask-api container)
            │     ├── Pod 2 (flask-api container)
            │     └── Pod N (scaled by HPA)
            ├── Service            — NodePort, load-balances across pods
            ├── Ingress            — NGINX, routes external traffic
            ├── HPA                — scales pod COUNT on CPU/memory load
            ├── VPA                — recommends CPU/memory right-sizing
            └── PodDisruptionBudget — ensures min pods stay up during maintenance
```

### High Availability Design Decisions

| Concern | Solution |
|---|---|
| Pod failure | `minReplicas: 2` — always 2+ pods running |
| Rolling deploys | `maxUnavailable: 0` — zero downtime updates |
| Traffic to unhealthy pods | Readiness probes gate Service endpoint registration |
| Pod restart loops | Liveness probes trigger automatic restarts |
| Node maintenance | PodDisruptionBudget prevents all pods being evicted at once |
| Pod spread | `topologySpreadConstraints` spreads pods across nodes |
| CPU spikes | HPA scales out replicas automatically |
| Undersized pods | VPA recommends right-sized resource requests |

---

## Prerequisites

Install these on Windows before starting:

```powershell
# 1. Minikube
winget install Kubernetes.minikube

# 2. kubectl
winget install Kubernetes.kubectl

# 3. Helm
winget install Helm.Helm

# 4. Terraform
winget install Hashicorp.Terraform

# 5. Docker Desktop (required by Minikube)
winget install Docker.DockerDesktop

# 6. k6 (load testing)
winget install k6
```

---

## Step-by-Step Setup

### 1. Start Minikube

```powershell
# Start with enough resources to see scaling in action
minikube start --cpus=4 --memory=4096 --nodes=2

# Enable required addons
minikube addons enable metrics-server   # Required for HPA
# Required for NGINX ingress
helm repo add fairwinds-stable https://charts.fairwinds.com/stable
helm install my-vpa fairwinds-stable/vpa --version 1.3.1
# Verify cluster is healthy
kubectl get nodes
```

Expected output:
```
NAME           STATUS   ROLES           AGE   VERSION
minikube       Ready    control-plane   1m    v1.30.0
minikube-m02   Ready    <none>          1m    v1.30.0
```

### 2. Build the Flask Docker Image Inside Minikube

```powershell
# Point your shell's Docker client at Minikube's Docker daemon
# (PowerShell)
minikube docker-env | Invoke-Expression

# Build the image — it will be available inside the cluster
docker build -t flask-api:latest ./app

# Verify the image exists inside Minikube
minikube ssh -- docker images | grep flask-api
```

### 3. Configure Terraform Secrets

```powershell
cd terraform

# Copy the example and fill in values (never commit terraform.tfvars)
cp terraform.tfvars.example terraform.tfvars
notepad terraform.tfvars
```

For a quick dev setup, the defaults in the example file work fine.

### 4. Deploy with Terraform

```powershell
terraform init
terraform plan        # Review what will be created
terraform apply       # Type 'yes' to confirm
```

Terraform will create:
- Namespace `bmw-k8-flask-api`
- ConfigMap `flask-config`
- Secret `flask-secrets`
- Helm release (Deployment, Service, HPA, VPA, PDB, Ingress)

### 5. Access the Flask API

```powershell
# Get the local URL (opens browser automatically)
minikube service bmw-k8-flask-api -n bmw-k8-flask-api

# Or get just the URL to use in k6 / Postman
minikube service bmw-k8-flask-api -n bmw-k8-flask-api --url
```

Test the endpoints:
```powershell
$URL = $(minikube service flask-api -n bmw-k8-flask-api --url)

curl "$URL/health"          # Liveness check
curl "$URL/ready"           # Readiness check
curl "$URL/api/v1/data"     # Main API
curl "$URL/api/v1/stress"   # CPU-intensive (triggers HPA)
```

---

## Secrets & Environment Variables — How It Works

```
┌─────────────────────────────────────────────────────────┐
│  terraform.tfvars  (git-ignored, local only)            │
│  secret_key = "my-secret"                               │
└────────────────────┬────────────────────────────────────┘
                     │ terraform apply
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Kubernetes Secret  (base64-encoded at rest)            │
│  Name: flask-secrets                                    │
│  Data: SECRET_KEY, DATABASE_URL, API_KEY, ...           │
└────────────────────┬────────────────────────────────────┘
                     │ envFrom.secretRef
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Pod Environment Variables                              │
│  SECRET_KEY=my-secret  ← available as os.environ       │
└────────────────────┬────────────────────────────────────┘
                     │ os.environ.get("SECRET_KEY")
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Flask config.py                                        │
│  SECRET_KEY = os.environ.get("SECRET_KEY", "fallback") │
└─────────────────────────────────────────────────────────┘
```

Non-sensitive config follows the same flow but uses a **ConfigMap** instead of a Secret.

### Viewing Secrets Safely

```powershell
# List secrets (values not shown)
kubectl get secrets -n bmw-k8-flask-api

# Describe — shows keys but NOT values
kubectl describe secret flask-secrets -n bmw-k8-flask-api

# Decode a specific secret value (for debugging only)
kubectl get secret flask-secrets -n bmw-k8-flask-api \
  -o jsonpath="{.data.SECRET_KEY}" | base64 --decode
```

---

## Scaling — How It Works

### Horizontal Scaling (HPA) — More Pods

HPA watches CPU/memory metrics and adds or removes pod replicas.

```
Low load:   [Pod1] [Pod2]                          ← minReplicas=2
Medium load:[Pod1] [Pod2] [Pod3] [Pod4]            ← HPA scaled up
High load:  [Pod1] [Pod2] ... [Pod10]              ← maxReplicas=10
```

### Vertical Scaling (VPA) — Bigger Pods

VPA watches actual resource usage and recommends (or applies) better
`requests` and `limits` values per container.

```
Before VPA: requests: cpu=100m, memory=128Mi
VPA sees:   actual usage cpu=350m, memory=200Mi
After VPA:  requests: cpu=350m, memory=220Mi  (right-sized)
```

In this project VPA is set to `updateMode: "Off"` — it only makes
recommendations. This is safest for an assessment environment.

---

## kubectl Commands to Verify Scaling

### Watch Pods Scale in Real Time

```powershell
# Live watch — run this in a separate terminal while k6 runs
kubectl get pods -n bmw-k8-flask-api -w

# You will see new pods appear as HPA adds them:
# NAME                         READY   STATUS    RESTARTS
# flask-api-7d9f8b-xk2pq      1/1     Running   0
# flask-api-7d9f8b-mn4rt      1/1     Running   0
# flask-api-7d9f8b-zp9wq      0/1     Pending   0   ← scaling up
# flask-api-7d9f8b-zp9wq      1/1     Running   0   ← now ready
```

### Monitor the HPA

```powershell
# Snapshot — shows current replicas and CPU target vs actual
kubectl get hpa -n bmw-k8-flask-api

# Output during load test:
# NAME            REFERENCE              TARGETS         MINPODS   MAXPODS   REPLICAS
# flask-api-hpa   Deployment/flask-api   85%/60%         2         10        6

# Live watch HPA decisions
kubectl get hpa flask-api-hpa -n bmw-k8-flask-api -w

# Full detail — shows scale up/down events and conditions
kubectl describe hpa flask-api-hpa -n bmw-k8-flask-api
```

### Check VPA Recommendations

```powershell
# View VPA recommendations (after running load for a few minutes)
kubectl describe vpa flask-api-vpa -n bmw-k8-flask-api

# Look for the "Recommendation" section:
# Recommendation:
#   Container Recommendations:
#     Container Name: flask-api
#       Lower Bound:   cpu: 80m,  memory: 150Mi
#       Target:        cpu: 320m, memory: 210Mi   ← VPA suggested value
#       Upper Bound:   cpu: 1,    memory: 500Mi
```

### Monitor Resource Usage

```powershell
# CPU and memory per pod (requires metrics-server addon)
kubectl top pods -n bmw-k8-flask-api

# CPU and memory per node
kubectl top nodes

# Continuously refresh every 3 seconds
while ($true) { kubectl top pods -n bmw-k8-flask-api; Start-Sleep 3; Clear-Host }
```

### Check Deployment Rollout & Events

```powershell
# Overall deployment status
kubectl rollout status deployment/flask-api -n bmw-k8-flask-api

# Detailed events — shows scale up/down reasons
kubectl describe deployment flask-api -n bmw-k8-flask-api

# All events in the namespace sorted by time
kubectl get events -n bmw-k8-flask-api --sort-by='.lastTimestamp'
```

### Check Pod Disruption Budget

```powershell
# Verify PDB is protecting minimum available pods
kubectl get pdb -n bmw-k8-flask-api

# Output:
# NAME           MIN AVAILABLE   MAX UNAVAILABLE   ALLOWED DISRUPTIONS
# flask-api-pdb  1               N/A               1
```

### Inspect Logs

```powershell
# Logs from all flask-api pods simultaneously
kubectl logs -l app=flask-api -n bmw-k8-flask-api --follow

# Logs from a specific pod
kubectl logs flask-api-7d9f8b-xk2pq -n bmw-k8-flask-api --follow

# Previous container logs (useful after a crash)
kubectl logs flask-api-7d9f8b-xk2pq -n bmw-k8-flask-api --previous
```

### Verify ConfigMap and Secret Injection

```powershell
# Confirm env vars are present inside a running pod
kubectl exec -it \
  $(kubectl get pod -l app=flask-api -n bmw-k8-flask-api -o jsonpath='{.items[0].metadata.name}') \
  -n bmw-k8-flask-api -- env | grep -E "ENVIRONMENT|APP_VERSION|LOG_LEVEL"

# SECRET_KEY will show *** in some shells — to confirm it's injected:
kubectl exec -it \
  $(kubectl get pod -l app=flask-api -n bmw-k8-flask-api -o jsonpath='{.items[0].metadata.name}') \
  -n bmw-k8-flask-api -- printenv SECRET_KEY
```

---

## Running the K6 Flood Test

```powershell
# 1. Get the Minikube service URL
$URL = $(minikube service flask-api -n bmw-k8-flask-api --url)

# 2. Open a separate terminal and watch pods scale
kubectl get pods -n bmw-k8-flask-api -w

# 3. Open another terminal and watch HPA
kubectl get hpa -n bmw-k8-flask-api -w

# 4. Run the flood test
k6 run -e BASE_URL=$URL k6/flood_test.js
```

### What to Expect During the Test

```
Time 0:00 — 1:00  (warmup)    : 10 VUs,  HPA holds at minReplicas=2
Time 1:00 — 3:00  (sustained) : 10 VUs,  stable at 2 pods
Time 3:00 — 4:00  (spike)     : ramp to 50 VUs, CPU rises above 60%
                                 → HPA adds pods (watch kubectl get pods -w)
Time 4:00 — 7:00  (flood)     : 50 VUs,  4–6 pods running
Time 7:00 — 8:00  (peak)      : ramp to 100 VUs, up to 8–10 pods
Time 8:00 — 10:00 (hold peak) : 100 VUs, HPA at or near maxReplicas
Time 10:00—12:00  (cooldown)  : ramp to 0, HPA begins scale-down after 120s window
```

---

## Tearing Down

```powershell
# Destroy all K8s resources managed by Terraform
cd terraform
terraform destroy

# Stop Minikube (preserves state)
minikube stop

# Delete Minikube entirely (clean slate)
minikube delete
```

---

## Project File Reference

```
flask-k8s-assessment/
├── app/
│   ├── Dockerfile              Multi-stage, non-root, gunicorn
│   ├── requirements.txt
│   └── src/
│       ├── main.py             Flask app with /health, /ready, /api/v1/data, /api/v1/stress
│       └── config.py           Env var config with production validation
├── terraform/
│   ├── providers.tf            Kubernetes + Helm providers pointing at Minikube
│   ├── variables.tf            All inputs incl. sensitive vars
│   ├── main.tf                 Namespace, ConfigMap, Secret
│   ├── helm.tf                 Helm release resource
│   ├── outputs.tf              Release status, resource names
│   └── terraform.tfvars.example  Copy → terraform.tfvars, fill in secrets
├── charts/flask-api/
│   ├── Chart.yaml
│   ├── values.yaml             All tunables with comments
│   └── templates/
│       ├── deployment.yaml     Pods, probes, rolling update, topology spread
│       ├── service.yaml        NodePort
│       ├── ingress.yaml        NGINX ingress
│       ├── hpa.yaml            CPU + memory autoscaling with scale behaviour
│       ├── vpa.yaml            Vertical right-sizing recommendations
│       └── pdb.yaml            Minimum available pods guarantee
├── k6/
│   └── flood_test.js           7-stage flood test with custom metrics & thresholds
└── README.md
```
