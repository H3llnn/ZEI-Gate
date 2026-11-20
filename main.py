"""ZΞI Gate entry point."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv('config.env')
if os.environ.get('ZEI_MODE') == 'worker':
    from subgate.worker import main
else:
    from subgate.app import main

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
