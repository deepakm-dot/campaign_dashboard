# Campaign Analytics Intelligence Platform

An automated Campaign Analytics & Attribution Dashboard designed for multi-store retail intelligence. Reconciles Google Sheets marketing campaigns and customer audience files with ClickHouse cloud POS databases and live MyG POS ERP reports.

## Features

- **Automated Multi-Source Sync**:
  - Live continuous synchronization with Google Sheets master schedules.
  - Automated customer audience detection from Google Drive and local directories (`Downloads`, `Desktop`).
  - High-performance, low-memory streaming (`openpyxl` `read_only=True`) supporting millions of customer records across multi-sheet workbooks.
- **Accurate Inverted Sales Attribution**:
  - Sub-second ClickHouse attribution connecting campaign customer phone numbers with store invoice data.
  - Automated New vs. Returning customer segmentation.
  - Category and brand-level revenue and unit breakdown.
  - POS ERP reconciliation matching Daily Sales Reports (`futurepos.mygoal.biz`).
- **Interactive Web Interface**:
  - Real-time campaign summary cards with target audience, revenue, conversion rate, and ROI.
  - Store-level sales intelligence overlay with walk-in vs. campaign-attributed revenue splits.
  - Live sync status indicator and automatic refresh.

## Project Structure

```
├── backend/
│   ├── main.py              # Core FastAPI/Bottle server and background sync worker
│   ├── directsync.py        # Streaming customer file ingestion (Drive & local)
│   ├── fixkpi.py            # ClickHouse POS sales attribution & KPI calculation
│   ├── requirements.txt     # Python dependencies
│   └── app/                 # Modular API routers and database configuration
├── frontend/
│   ├── index.html           # Main dashboard interface
│   ├── store-sales.html     # Store sales intelligence interface
│   ├── package.json         # Frontend configuration
│   └── src/                 # React / Tailwind source components
└── .gitignore
```

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js & npm (for frontend asset builds)

### Backend Setup
1. Install Python requirements:
   ```bash
   pip install -r backend/requirements.txt
   ```
2. Start the backend server:
   ```bash
   python backend/main.py
   ```
   The dashboard runs at `http://localhost:8000`.

## Data storage (ClickHouse only)

The dashboard no longer uses any local database. All of its state lives in four ClickHouse tables,
accessed through `backend/ch_db.py`:

| Table | Contents |
|---|---|
| `campaign_dashboard_campaigns` | campaigns and their KPIs |
| `campaign_dashboard_campaign_customers` | audience (mobile numbers) per campaign |
| `campaign_dashboard_billing` | billing rows (archived) |
| `campaign_dashboard_config` | dashboard-wide values such as `total_audience_reached` |

Every row has a `source_db` column; the live dashboard reads and writes only `source_db = 'root'`.
Connection settings come from the `CH_URL`, `CH_USER` and `CH_PASS` environment variables.
`backend/migrate_to_clickhouse.py` is the one-off script that copied the old SQLite data into these tables.
