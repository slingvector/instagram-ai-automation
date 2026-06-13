# Elite Run V4: Cloud Readiness Strategy

To transition this discovery system from a local trial (MacBook Air) to a production-grade cloud environment, follow this roadmap.

## 1. Containerization (Docker)
Move from local `venv` to a Docker-based environment to ensure "run anywhere" stability.
- **Base Image**: `python:3.11-slim` (with Playwright dependencies).
- **Persistence**: Mount a volume for the `data/` directory to keep `elite_v4_dedup.db` and `elite_v4_manifest.yaml` between restarts.

## 2. Infrastructure as Code (IaC)
- **VPS Choice**: A 4GB+ RAM Linux instance (AWS EC2 t3.medium or GCP e2-standard-2) is recommended to handle multiple headless Chromium instances.
- **Self-Healing**: Use `Docker Compose` with `restart: always` to ensure the pipeline resumes if the process crashes.

## 3. Scraping Resilience (Critical)
Datacenter IPs are quickly flagged by Instagram. To reach 10,000 accounts:
- **Residential Proxies**: Integrate a proxy service (e.g., Bright Data, Oxylabs) into the Playwright browser context in `EliteV4Pipeline`.
- **Session Persistence**: Occasionally save and load browser cookies to maintain a "warm" session, though V4 is currently designed for headless/guest scraping.

## 4. Data Centralization
- **Database**: Move from SQLite (`elite_v4_dedup.db`) to a managed database like **GCP Firestore** or **PostgreSQL** if you plan to have multiple nodes scraping simultaneously.
- **Storage**: Maintain the current **Google Drive** integration or move to **GCS (Google Cloud Storage)** for raw video storage before final posting.

## 5. Monitoring & Alerting
- **Health Checks**: Implement a simple heartbeat (e.g., logging every 100 accounts to a centralized dashboard like **Sentry** or **DataDog**).
- **PID management**: Use a proper process manager like `PM2` or `systemd` instead of `nohup`.

## 6. Execution Command (Cloud)
Once Dockerized, simply run:
```bash
docker compose -f docker-compose.v4.yml up -d
```

---
**Cloud Ready Check**:
- [ ] GCP Service Account Key present?
- [ ] Drive OAuth Token valid?
- [ ] Residential Proxy configured?
- [ ] Volumes mounted for `.db` and `.yaml`?
