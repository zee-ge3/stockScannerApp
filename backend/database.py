from sqlmodel import SQLModel, create_engine, Session
import os

# 1. SETUP THE URL
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sqlite_file_name = os.path.join(BASE_DIR, "stocks.db")
sqlite_url = f"sqlite:///{sqlite_file_name}"

# 2. CREATE THE ENGINE
# We disable "check_same_thread" because FastAPI runs on multiple threads
connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)

# 3. HELPER TO CREATE TABLES
# We call this once at startup to ensure the file exists
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# 4. SESSION GENERATOR
# This is what main.py will use to get a temporary connection
def get_session():
    with Session(engine) as session:
        yield session