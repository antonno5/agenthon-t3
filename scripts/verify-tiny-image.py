"""Checks for the minimal (FROM scratch) image variant; runs no market simulations.

The Python probe of verify-image.py cannot run in an image without Python. This checks the
contract-level properties instead: linux/amd64, the interface label, no VOLUME/ENTRYPOINT, the
exact file list, that the native sources baked into the build match
provenance/selected-build-input.json, and that both verbs start offline under the platform flags.
"""

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

EXPECTED_FILES = {
    'etc/group', 'etc/passwd', 'opt/licenses/native-abides-LICENSE',
    'opt/licenses/native-json-LICENSE', 'opt/licenses/native-numpy-LICENSE',
    'usr/local/bin/simulate', 'usr/local/bin/simulate-batch', 'usr/local/bin/t3-native',
}
FLAGS = ['--network', 'none', '--read-only', '--user', '65534:65534', '--cap-drop=ALL',
         '--security-opt', 'no-new-privileges', '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=64m']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    inspect = json.loads(subprocess.check_output(['docker', 'image', 'inspect', args.image], text=True))[0]
    config = inspect['Config']
    problems = []
    if (inspect['Os'], inspect['Architecture']) != ('linux', 'amd64'):
        problems.append('expected linux/amd64')
    if (config.get('Labels') or {}).get('qfbench2.interface_version') != '2.0':
        problems.append('missing interface label 2.0')
    if config.get('Volumes'):
        problems.append('image declares a VOLUME')
    if config.get('Entrypoint'):
        problems.append('image declares an ENTRYPOINT')
    if config.get('WorkingDir') != '/tmp':
        problems.append('WorkingDir is not /tmp')
    container = subprocess.check_output(['docker', 'create', args.image], text=True).strip()
    try:
        tar = tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['docker', 'export', container])))
        files = {m.name for m in tar.getmembers() if m.isfile() or m.issym()}
        # entries Docker itself creates in every container
        files -= {'.dockerenv', 'dev/console', 'etc/hostname', 'etc/hosts', 'etc/mtab', 'etc/resolv.conf'}
        if files != EXPECTED_FILES:
            problems.append(f'file list differs: extra {sorted(files - EXPECTED_FILES)} missing {sorted(EXPECTED_FILES - files)}')
        for verb in ('simulate', 'simulate-batch'):
            link = tar.getmember(f'usr/local/bin/{verb}')
            if not link.issym() or link.linkname != 't3-native':
                problems.append(f'{verb} is not a symlink to t3-native')
        binary = tar.extractfile('usr/local/bin/t3-native').read()
        if binary[:4] != b'\x7fELF' or int.from_bytes(binary[18:20], 'little') != 62:
            problems.append('t3-native is not an x86-64 ELF')
    finally:
        subprocess.run(['docker', 'rm', container], check=True, stdout=subprocess.DEVNULL)
    selected = json.loads((root / 'provenance/selected-build-input.json').read_text())['build_ingredients_sha256']
    for name, digest in selected.items():
        if name.startswith('native/') or name == 'build_executable.py':
            path = root / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                problems.append(f'{name} differs from provenance/selected-build-input.json')
    for verb in ('simulate', 'simulate-batch'):
        r = subprocess.run(['docker', 'run', '--rm', *FLAGS, args.image, verb, '--help'], capture_output=True, text=True)
        if r.returncode != 0:
            problems.append(f'{verb} --help exited {r.returncode}: {r.stderr.strip()}')
    if problems:
        raise SystemExit('Tiny image check failed:\n  ' + '\n  '.join(problems))
    print(f'Tiny image OK: {len(files)} files, static x86-64 t3-native ({len(binary)} bytes), both verbs start offline under platform flags; native sources match provenance.')


if __name__ == '__main__':
    main()
