# Render Demo Deployment

This deploys the app as a password-protected demo. The Render URL is reachable from the internet, but the app and all API routes require HTTP Basic Authentication over Render's HTTPS connection. Share the credentials only with demo viewers.

## Deploy

1. Rotate the IBM Bob API key that was present in the local `src/.env` before using it anywhere else. The container deliberately does not copy `.env`, `data/`, or local virtual environments.
2. In Render, create a new **Blueprint** from this repository and select `render.yaml`.
3. When prompted, set `APP_AUTH_USERNAME`, `APP_AUTH_PASSWORD`, and `BOB_API_KEY`. Enter your IBM Bob API key securely into Render's environment variable prompt so it remains completely hidden and never committed to version control. Set a unique, randomly generated password for basic auth (e.g. generate one locally with `openssl rand -hex 32`).
4. Deploy. Render builds the frontend and Python service from the `Dockerfile`; the `/_health` endpoint is used for health checks.
5. Open the service URL. The browser's Basic Auth prompt should appear before the app loads.

Production mode fails closed: if either authentication variable is missing, the app returns `503` instead of serving the UI or API. Do not remove the auth variables to make the demo easier to access.

## IBM Bob and X API
 
`BOB_API_KEY` is configured as a protected secret in Render (`sync: false` in `render.yaml`), ensuring no credentials are ever exposed in Git repositories or client bundles. The application supports upload, forensic coordination analysis, network graph visualization, timeline clustering, and all cached Bob assessments.

If X search is needed, add `X_BEARER_TOKEN` as a secret environment variable in Render. Never add API keys to `render.yaml`, the Docker image, frontend build variables, or committed files.

## Pre-Loaded Demonstration Data

The container image bundles production-ready forensic case-study datasets in `demo_data/runs/`:
- **Delhi Riots 2020: False-Context Rumour Network** (1,532 posts across 1,444 accounts; CIB ring, physical gathering detection, and Section 63 BSA legal brief).
- **Palghar Incident: Astroturfed Disinformation Ring** (3,271 posts across 1,342 accounts; coordinated botnet burst network and statutory BNS/IT Act suggestions).

On service startup, the engine detects if the ephemeral runtime store (`data/runs`) is empty and automatically seeds these pre-loaded datasets in under 100 milliseconds. Visitors immediately see rich, interactive network topologies, temporal curves, and threat briefs without manual uploads.

## Alternative Zero-Cost Hosting: Hugging Face Spaces (16 GB Free RAM)

If higher memory is required for larger network graphs without cold-start sleep delays:
1. Create a new Space on [Hugging Face Spaces](https://huggingface.co/spaces) selecting **Docker** SDK.
2. Push or sync this repository to the Hugging Face Space.
3. Hugging Face Spaces provides **16 GB RAM and 2 vCPUs** completely free with zero credit card required.

## Demo Data Limits

The free Render service has ephemeral storage and may sleep when idle. While runtime uploads are ephemeral, the pre-loaded demonstration datasets are guaranteed to persist across restarts. Do not upload confidential investigations or non-public casework to shared demo instances.