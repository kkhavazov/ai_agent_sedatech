# GA4 client

Enable the Google Analytics Data API in your Google Cloud project and grant
your service account **Viewer** access to the GA4 property. Use the numeric
property ID, not the website's `G-...` measurement ID.

Install `backend/requirements.txt`. From the `backend` directory, configure:

```powershell
$env:GA4_PROPERTY_ID = "123456789"
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\secure\ga4-service-account.json"
```

Keep credentials outside the repository and Docker build context. For Docker,
mount the credentials read-only and set these variables in the calling service;
the credentials path must refer to the mounted file inside the container.
Application Default Credentials are also supported. The client does not load
`.env` files itself; the application may load them before constructing it.

```python
from analytics.ga4_client import GA4Client

client = GA4Client()
report = client.run_report(
    start_date="28daysAgo",
    end_date="yesterday",
    dimensions=["date"],
    metrics=["sessions", "activeUsers"],
)
print(report)
```

Reports preserve SDK response fields, including headers, rows, metadata, and
property quota. Metric values remain strings as returned by Google. Dates are
inclusive; relative dates use the property timezone. `next_offset` identifies
another page, or is `None` when finished. Pass it as `offset` with the same report
arguments to continue. There is no automatic unbounded pagination or retry loop.
SDK errors propagate to the caller; failures are never represented as zero traffic.

The internal Streamlit assistant exposes `query_website_traffic`; customer ticket
reply generation does not receive this tool. Restart the assistant after installing
dependencies. In the same terminal where your GA4 environment and ADC login work,
run `streamlit run app.py` from `backend`. Try:

- Show website sessions by day for the last 28 days as a chart.
- Which channels brought visitors last week?
- Compare website active users for September 2026 and August 2026.

The tool supports overview, daily, channel, source/medium, landing page, device,
and country reports. It returns one bounded page and labels partial results.
Overview requests get period totals directly from GA4. There is no report cache
or scheduled reporting yet. Local ADC credentials are not automatically available
inside Docker: mount your ADC credential file read-only and set
`GOOGLE_APPLICATION_CREDENTIALS` to its container path, along with
`GA4_PROPERTY_ID`, in the `support-agent` service. Do not use the OAuth client
registration JSON as an ADC credential file.

For local Windows Docker development with your saved `gcloud` login, run from
the repository root:

```powershell
docker compose -f docker-compose.yml -f docker-compose.ga4.yml up -d --build support-agent
```

This override mounts `%APPDATA%/gcloud/application_default_credentials.json`
read-only. The base Compose file passes `GA4_PROPERTY_ID` from the root `.env`.
Use the same two Compose files on subsequent recreations to retain the mount.

API reference: https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport
