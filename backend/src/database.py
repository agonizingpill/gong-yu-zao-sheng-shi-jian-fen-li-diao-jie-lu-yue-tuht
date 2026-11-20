import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase,sessionmaker
engine=create_engine(os.getenv('DATABASE_URL','mysql+pymysql://quiet:quiet-demo@db:3306/quiet'),pool_pre_ping=True,isolation_level='READ COMMITTED')
class Base(DeclarativeBase): pass
Session=sessionmaker(engine,expire_on_commit=False)
def session():
    with Session() as db:
        try: yield db
        except Exception:
            db.rollback()
            raise
