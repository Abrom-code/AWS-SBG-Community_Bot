import os
import pytest

# Ensure all tests run in an isolated test database, preserving the live bot database
TEST_DB_PATH = "test_bot_sandbox.db"
os.environ["SQLITE_DB_PATH"] = TEST_DB_PATH

import app.db as db
db.SQLITE_DB_PATH = TEST_DB_PATH


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Points the application DB to the test sandbox database and cleans it up after."""
    yield
    # Cleanup test sandbox database file after test suite finishes
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass
