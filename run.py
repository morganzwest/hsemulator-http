import asyncio
import sys
from app.main import app
import uvicorn


def main():
    if sys.platform.startswith("win"):
        runner = asyncio.Runner(loop_factory=asyncio.ProactorEventLoop)
        with runner:
            uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
