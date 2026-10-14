"""CLI and daemon entrypoint for Karoo2Garmin service."""

import argparse
import locale
import logging
import signal
import sys
import time
from datetime import datetime

from src import __version__
from src.config import Config
from src.garmin_client import format_local_datetime
from src.sync_engine import SyncEngine

try:
    locale.setlocale(locale.LC_TIME, "")
except Exception:
    pass


def setup_logging(log_level: str = "INFO") -> None:
    """Configure console logging format."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=log_format, stream=sys.stdout)


def parse_args() -> argparse.ArgumentParser:
    """Configure command line arguments."""
    parser = argparse.ArgumentParser(
        prog="Karoo2Garmin",
        description="Sync Hammerhead Karoo activities to Garmin Connect with FIT device enhancement.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program's version number and exit.",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously in background daemon mode polling periodically.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        metavar="MINUTES",
        help="Interval between sync cycles in minutes (default from config or 60m).",
    )
    parser.add_argument(
        "--sync-latest",
        action="store_true",
        help="Synchronize only the single latest activity.",
    )
    parser.add_argument(
        "--batch",
        type=int,
        metavar="COUNT",
        help="Number of recent activities to inspect (overrides SYNC_BATCH_SIZE).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without modifying Garmin Connect or persisting state.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display recent sync history and statistics from the database.",
    )
    return parser


def main() -> int:
    """Main execution entry point."""
    args = parse_args().parse_args()

    stop_requested = False

    def handle_signal(sig, frame):
        nonlocal stop_requested
        logging.info("Received termination signal (%s). Shutting down cleanly...", sig)
        stop_requested = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        config = Config.from_env()
    except Exception as exc:
        print(f"Configuration Error: {exc}", file=sys.stderr)
        return 1

    setup_logging(config.log_level)
    logger = logging.getLogger("Karoo2Garmin")
    logger.info("Initializing Karoo2Garmin service v%s...", __version__)

    engine = SyncEngine(config=config)

    # 1. Status command
    if args.status:
        recent = engine.store.get_recent_synced(limit=15)
        stats = engine.store.get_stats()
        print("\n================ Karoo2Garmin Status ================")
        print(
            f"Total Processed: {stats['total']} | Uploaded: {stats['uploaded']} | "
            f"Skipped: {stats['skipped_duplicate']} | Failed: {stats['failed']}"
        )
        print("-----------------------------------------------------")
        if not recent:
            print("No recorded activities in sync store.")
        else:
            for item in recent:
                formatted_date = format_local_datetime(item['activity_date'])
                print(
                    f"[{item['synced_at'][:19]}] {item['name']} "
                    f"(Karoo ID: {item['karoo_id']}, Date: {formatted_date}) -> {item['garmin_status']}"
                )
        print("=====================================================\n")
        return 0

    # 2. One-shot sync (Default if not daemon)
    if not args.daemon:
        logger.info("Executing one-shot sync...")
        engine.run_sync(
            limit=args.batch,
            dry_run=args.dry_run,
            sync_latest=args.sync_latest,
        )
        return 0

    # 3. Daemon mode
    interval_minutes = args.interval or config.sync_interval_minutes
    interval_seconds = interval_minutes * 60
    logger.info(
        "Starting daemon loop (polling every %d minutes / %d seconds)...",
        interval_minutes,
        interval_seconds,
    )

    while not stop_requested:
        start_time = time.time()
        try:
            engine.run_sync(
                limit=args.batch,
                dry_run=args.dry_run,
                sync_latest=args.sync_latest,
            )
        except Exception as exc:
            logger.exception("Unexpected error occurred during daemon sync cycle: %s", exc)

        logger.info(
            "Sync cycle finished. Sleeping for %d minutes until next run...",
            interval_minutes,
        )

        # Sleep in small increments to respond quickly to shutdown signals
        while not stop_requested and (time.time() - start_time) < interval_seconds:
            time.sleep(1.0)

    logger.info("Karoo2Garmin daemon terminated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
