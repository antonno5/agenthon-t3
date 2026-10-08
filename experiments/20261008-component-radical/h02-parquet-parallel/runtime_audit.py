"""Executive summary: preserve the exact pinned runtime and native extension binary before measurements."""
import hashlib
import json
import platform
from pathlib import Path
import shutil
import sys
sys.path.insert(0,'/opt/abides_fork')
import _t3engine
import numpy
import pandas
import pyarrow
import scipy
versions={'python':platform.python_version(),'numpy':numpy.__version__,'pandas':pandas.__version__,'arrow':pyarrow.__version__,'scipy':scipy.__version__}
assert versions=={'python':'3.11.17','numpy':'1.26.4','pandas':'1.5.3','arrow':'15.0.2','scipy':'1.17.1'},versions
source=Path(_t3engine.__file__);out=Path('/audit');out.mkdir(exist_ok=True)
shutil.copy2(source,out/source.name)
record={'executive_summary':'Pinned versions and the exact loaded native extension are preserved before the primary series.',
        'versions':versions,'module_path':str(source),'native_extension_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'numpy_log_dispatch':_t3engine.numpy_log_dispatch()}
(out/'runtime.json').write_text(json.dumps(record,indent=2)+'\n')
