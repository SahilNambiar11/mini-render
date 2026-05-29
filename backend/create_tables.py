from database import engine, Base
from models import Deployment

Base.metadata.create_all(bind=engine)

print("Tables created!")