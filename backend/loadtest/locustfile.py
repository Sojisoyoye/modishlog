"""Locust load test for task #243 -- realistic launch-scale concurrency.

Scripts real user journeys (not a single-endpoint hammer): login, dashboard
load, paginated product/sales browsing, a P&L report, and -- the
highest-risk path found in the scalability audit -- a bulk sales CSV import
polled to completion. Each simulated user is a distinct seeded business
(see loadtest_seed.py), so this also exercises the business_id-isolation
query paths under real concurrency, not one tenant's data reused N times.

Usage (against docker-compose.loadtest.yml, see that file's header comment
for how to bring the stack up and seed it first):

    backend/.venv/bin/locust -f backend/loadtest/locustfile.py \\
        --host http://localhost:8010 \\
        --users 200 --spawn-rate 5 --run-time 5m --headless \\
        --csv backend/loadtest/results/run1
"""

import csv
import io
import json
import os
import random
import time

from locust import HttpUser, between, events, task

_CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "loadtest_users.json")
with open(_CREDENTIALS_PATH) as f:
    _ALL_CREDENTIALS = json.load(f)

# Each Locust worker process gets its own copy of this list; assign
# credentials round-robin per spawned user so concurrent users never share
# a login (that would understate real per-tenant concurrency).
_next_credential_index = 0


def _next_credentials() -> dict:
    global _next_credential_index
    creds = _ALL_CREDENTIALS[_next_credential_index % len(_ALL_CREDENTIALS)]
    _next_credential_index += 1
    return creds


def _make_bulk_upload_csv(product_ids: list[str], n_rows: int) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    # REQUIRED_CSV_HEADERS (backend/src/sales/service.py): product_id,
    # quantity, unit_price, sale_date, channel.
    writer.writerow(["product_id", "quantity", "unit_price", "sale_date", "channel"])
    for i in range(n_rows):
        writer.writerow(
            [
                random.choice(product_ids),
                random.randint(1, 3),
                random.randint(2000, 60000),
                "2026-08-01",
                "retail",
            ]
        )
    return buf.getvalue().encode()


class TraderUser(HttpUser):
    """Simulates one business owner's session: login once, then browse."""

    wait_time = between(1, 4)

    def on_start(self):
        creds = _next_credentials()
        self.business_name = creds["business_name"]
        self.product_ids = creds["product_ids"]
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": creds["email"], "password": creds["password"]},
            name="/auth/login",
        )
        if resp.status_code != 200:
            self.access_token = None
            return
        self.access_token = resp.json()["access_token"]
        self.client.headers.update({"Authorization": f"Bearer {self.access_token}"})

    @task(10)
    def view_dashboard(self):
        if not self.access_token:
            return
        self.client.get("/api/v1/dashboard/summary", name="/dashboard/summary")

    @task(15)
    def browse_products(self):
        if not self.access_token:
            return
        page = random.randint(1, 10)
        self.client.get(f"/api/v1/products?page={page}&page_size=20", name="/products [paginated]")

    @task(15)
    def browse_sales(self):
        if not self.access_token:
            return
        page = random.randint(1, 20)
        self.client.get(f"/api/v1/sales?page={page}&page_size=20", name="/sales [paginated]")

    @task(3)
    def profit_loss_report(self):
        if not self.access_token:
            return
        self.client.get(
            "/api/v1/reports/profit-loss?date_from=2026-01-01&date_to=2026-09-15",
            name="/reports/profit-loss",
        )

    @task(1)
    def bulk_sales_import(self):
        """The highest-risk path (task 215): upload a CSV, then poll the
        background job until it finishes, and record total wall-clock time
        from upload to completion -- not just the initial 202 response."""
        if not self.access_token:
            return
        csv_bytes = _make_bulk_upload_csv(self.product_ids, 500)
        resp = self.client.post(
            "/api/v1/sales/upload",
            files={"file": ("loadtest_sales.csv", csv_bytes, "text/csv")},
            name="/sales/upload [submit]",
        )
        if resp.status_code != 202:
            return
        job_id = resp.json()["job_id"]

        start = time.monotonic()
        final_status = None
        for _ in range(60):  # up to ~60 poll attempts
            status_resp = self.client.get(
                f"/api/v1/sales/upload/{job_id}/status",
                name="/sales/upload/status [poll]",
            )
            if status_resp.status_code == 200 and status_resp.json().get("status") in (
                "completed",
                "failed",
            ):
                final_status = status_resp.json()["status"]
                break
            time.sleep(1)
        elapsed = time.monotonic() - start
        # Distinguish "reached a terminal status within the poll budget"
        # from "gave up waiting" -- firing both cases as an unconditional
        # success would conflate a real completion time with a job that
        # never actually finished, hiding exactly the kind of worst-case
        # tail this scenario exists to measure.
        exception = None if final_status is not None else TimeoutError(
            f"job {job_id} did not reach a terminal status within 60 poll attempts"
        )
        events.request.fire(
            request_type="JOB",
            name="/sales/upload [end-to-end]",
            response_time=elapsed * 1000,
            response_length=0,
            exception=exception,
            context={},
        )
