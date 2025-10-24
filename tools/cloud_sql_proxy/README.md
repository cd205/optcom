# Cloud SQL Auth Proxy Helper

This folder contains the Cloud SQL Auth Proxy binary and helper script for connecting to the
`optcom-postgres` Cloud SQL instance from WSL/WSL2.

## Files

- `cloud-sql-proxy` – downloaded proxy binary (v1).
- `start_proxy.sh` – wrapper script that launches the proxy with sensible defaults.
- `proxy.env.example` – optional environment overrides; copy to `proxy.env` to customize values.

## Prerequisites

1. The Google Cloud SDK (`gcloud`) installed inside WSL.
2. You are authenticated (`gcloud auth login`) _or_ you have a service account key JSON file and set
   `GOOGLE_APPLICATION_CREDENTIALS` to its path.
3. Cloud SQL Admin API is enabled and the `optcom-postgres` instance exists.

## Usage

```bash
# From the project root
cd tools/cloud_sql_proxy
./start_proxy.sh
```

By default the script:
- Connects to `crafty-water-453519-d7:europe-west4:optcom-postgres`.
- Listens on `127.0.0.1:5433`.
- Uses the active gcloud account for authentication.

To override any of these values, copy `proxy.env.example` to `proxy.env` and edit the file. You can
also pass variables inline:

```bash
INSTANCE_CONNECTION_NAME="my-project:region:instance" PROXY_PORT=5434 ./start_proxy.sh
```

Once the proxy is running, point applications (and the notebook) at `host=127.0.0.1`,
`port=5433` (or your chosen port). Leave the script running in its terminal window while you work.

To stop the proxy, press `Ctrl+C`.
