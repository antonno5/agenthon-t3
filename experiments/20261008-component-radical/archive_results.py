"""Executive summary: archive completed experiment artifacts without production adoption.

Closed files are hardlinked when possible to preserve retained raw evidence at
both paths without duplicating large journal payloads. Worktrees remain intact.
"""
import argparse
import json
import os
import shutil
from pathlib import Path

CAMPAIGN = Path(__file__).resolve().parent
PLAN = json.loads((CAMPAIGN / 'plan.json').read_text())
DEST = Path(PLAN['report_directory'])


def closed_copy(source, target):
    path = Path(source)
    # Text reports and tools get separate inodes, so later edits in a worktree
    # cannot silently change the historical report in the main checkout.
    payload = path.suffix in {'.parquet', '.arrow', '.ipc', '.so'}
    if payload:
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
    else:
        shutil.copy2(source, target)
    return str(target)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--slug', required=True)
    ap.add_argument('--finish-metadata', action='store_true', help='Finish metadata after a successful tree copy; never overwrite evidence')
    args = ap.parse_args()
    exp = next(e for e in PLAN['experiments'] if e['slug'] == args.slug)
    marker = json.loads((CAMPAIGN / ('DONE-' + args.slug + '.json')).read_text())
    source = Path(exp['worktree']) / 'experiments/20261008-component-radical' / args.slug
    result = json.loads((source / 'result.json').read_text())
    assert result['complete'] and result['accepted'], 'No complete accepted timing result'
    primary_source = source / 'result.json'
    if 'evidence_directory' not in result:
        primary_source = source / 'focused-pinned/result.json'
        result = json.loads(primary_source.read_text())
    assert result['complete'] and result['accepted'] and 'evidence_directory' in result
    target = DEST / args.slug
    assert not any(p.is_symlink() for p in source.rglob('*')), 'Archive must contain regular files'
    if args.finish_metadata:
        assert target.exists(), 'Metadata recovery needs a completed tree copy'
    else:
        assert not target.exists(), 'Retain archives rather than overwriting them'
        shutil.copytree(source, target, copy_function=closed_copy)
    shutil.copy2(primary_source, target / 'primary-result.json')
    (DEST / ('DONE-' + args.slug + '.json')).write_text(json.dumps(marker, indent=2, ensure_ascii=False) + '\n')
    (target / 'archive.json').write_text(json.dumps({
        'executive_summary': 'Completed isolated experiment copied into the main experiments archive; production changes remain on its branch.',
        'source': str(source), 'archive': str(target), 'method': 'Copy reports/tools; hardlink closed Parquet/IPC/native-library payloads, copy on link failure',
        'original_evidence_directory': result['evidence_directory'],
        'primary_result_source': str(primary_source),
        'worktree': exp['worktree'], 'branch': exp['branch'], 'thread_id': exp['thread_id'],
    }, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'archived': args.slug, 'path': str(target)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
