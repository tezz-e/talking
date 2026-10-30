import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    print("Starting Talking Autopilot Dashboard...")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
