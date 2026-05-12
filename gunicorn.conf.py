import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Give workers 25 s to finish in-flight requests before a hard kill,
# staying safely under Heroku's 30 s SIGTERM deadline.
timeout = 25
graceful_timeout = 25


def worker_exit(server, worker):
    """Close the Firestore gRPC channel on worker shutdown to prevent R12."""
    try:
        from firebase_service import shutdown as firebase_shutdown
        firebase_shutdown()
    except Exception as e:
        print(f"[gunicorn] worker_exit Firebase cleanup failed: {e}")
