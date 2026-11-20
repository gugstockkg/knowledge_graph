# EC2 OpenDART batch implementation plan

Goal: deploy daily disclosure collection and resumable date-range backfill to the existing fintos-dev-cpu, using gugstockkg/knowledge_graph.

Architecture: standard-library module reusing DartClient; SQLite receipts/dates/quota plus a process lock; atomic ZIP/JSONL files partitioned by rcept_dt; verified S3 uploads under raw/opendart/. systemd daily timer (06:30 Asia/Seoul, Persistent=true) and backfill template share state. Store API key only in root-controlled service configuration. No Neo4j/IAM/network changes.

Constraints: Python 3.11, only dates through yesterday; refresh last three days and catch up from watermark. Different computers' API usage is not included in local quota accounting. EC2 must run for timers; no promise of automatic EC2 startup or 24/7 operation within the original 320-hour budget. Preserve existing uncommitted work; use a clean clone because original Git recursive reads stalled. GitHub branch: codex/ec2-opendart-batch.

Review focus: missing/corrupt ZIP or S3 failure must not complete a date; 020 pauses all modes until next KST day; budgets persist across restarts; refreshed indexes find late filings; invalid IDs/dates must not become paths; secrets never appear in Git, command arguments or logs.

- [ ] Tests RED: pagination, receipt-date mapping, resume, refresh, corruption, quota cooldown, persistent/per-run budget, missing document expiry, transient error, S3 retry, daily gaps, lock, input validation.
- [ ] Implement batch.py, systemd units, operator runbook. Run full unit suite.
- [ ] Independent final review; fix important issues with regression tests. Scan and push only new batch files.
- [ ] Pull reviewed revision on EC2; install service account/secret/timer. Real bounded OpenDART/S3 test, resume test, timer and permissions verification.

Ruling: user explicitly requested direct implementation/deployment; continue without a second design approval. GitHub default branch is not changed automatically. Backfill capability is installed and tested on a bounded actual date, rather than silently redownloading the entire existing 2026 history.
