"""允许 python -m research_pipeline 运行。"""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
