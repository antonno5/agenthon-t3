"""Compare an image with the measured runtime; never execute simulation tasks."""

import argparse
import json
import subprocess
from pathlib import Path


PROBE = r'''
import hashlib, importlib.metadata, importlib.util, json, platform
from pathlib import Path
files = {}
for prefix, module in [('core', 'abides_core'), ('markets', 'abides_markets'), ('adapter', 'abides_fork')]:
    root = Path(importlib.util.find_spec(module).origin).parent
    for path in sorted(root.rglob('*.py')):
        files[prefix + '/' + path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
extra = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in ['/opt/_abides_python_control.py', '/usr/local/bin/simulate', '/usr/local/bin/simulate-batch']}
from abides_markets import order_book, price_level
from abides_markets.matching import facade
from abides_markets.matching.price_level import PriceLevel
runtime = {'python': platform.python_version(), 'packages': dict(sorted((d.metadata['Name'].lower(), d.version) for d in importlib.metadata.distributions()))}
identity = {'order_book': order_book.OrderBook.__module__, 'price_level': price_level.PriceLevel.__module__, 'facade_same_class': facade.OrderBook is order_book.OrderBook, 'level_same_class': PriceLevel is price_level.PriceLevel, 'logger_same_object': facade.logger is order_book.logger}
native_sources = {}
for path in sorted(Path('/opt/native-source').rglob('*')):
    if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
        native_sources['native/' + path.relative_to('/opt/native-source').as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
native_sources['build_native.py'] = hashlib.sha256(Path('/opt/native_build.py').read_bytes()).hexdigest()
from abides_fork import _t3engine
native_api = {name: callable(getattr(_t3engine, name, None)) for name in ['run', 'run_write', 'numpy_log']}
print(json.dumps({'files': files, 'runtime': runtime, 'extra_files': extra, 'identity': identity, 'native_sources': native_sources, 'native_api': native_api}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context')
    parser.add_argument('image')
    args = parser.parse_args()
    docker = ['docker'] + (['--context', args.context] if args.context else [])
    inspect = json.loads(subprocess.check_output(docker + ['image', 'inspect', args.image], text=True))[0]
    if (inspect['Os'], inspect['Architecture']) != ('linux', 'amd64'):
        raise SystemExit('Expected linux/amd64 image.')
    if inspect['Config'].get('Labels', {}).get('qfbench2.interface_version') != '2.0':
        raise SystemExit('Expected interface version 2.0.')
    result = subprocess.run(docker + ['run', '--rm', '--platform', 'linux/amd64', '--network', 'none', '--read-only', args.image, 'python', '-c', PROBE], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(result.stderr)
    actual = json.loads(result.stdout)
    actual['docker_config'] = {key: inspect['Config'].get(key) for key in ['WorkingDir', 'Entrypoint', 'Cmd', 'Env', 'User', 'Volumes']}
    expected = json.loads((Path(__file__).resolve().parents[1] / 'provenance/expected-runtime.json').read_text())
    differences = [key for key in expected if actual.get(key) != expected[key]]
    if differences:
        for key in differences:
            print(json.dumps({'section': key, 'expected': expected[key], 'actual': actual.get(key)}, indent=2))
        raise SystemExit('Runtime differs from the measured image: ' + ', '.join(differences))
    for verb in ['simulate', 'simulate-batch']:
        subprocess.run(docker + ['run', '--rm', '--platform', 'linux/amd64', '--network', 'none', '--read-only', args.image, verb, '--help'], check=True, stdout=subprocess.DEVNULL)
    print(f'Exact runtime match: {len(actual["files"])} Python sources, CLI/control, native sources/API, package versions and Docker config; both verbs start offline. No scenarios executed.')


if __name__ == '__main__':
    main()
