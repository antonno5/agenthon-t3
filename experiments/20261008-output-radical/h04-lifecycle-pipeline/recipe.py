"""Executive summary: build and validate the frozen candidate in the shared serial Docker slot.

Phase 1 prepares this recipe only. It may be run after coordinator scheduling.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path,required=True)
p.add_argument('--build',action='store_true');p.add_argument('--bindings',action='store_true')
p.add_argument('--controls',action='store_true');p.add_argument('--timing',action='store_true')
p.add_argument('--out',type=Path,required=True)
a=p.parse_args();area=Path(__file__).resolve().parent;root=area.parents[2]
a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True);campaign=a.campaign.resolve()
plan=json.loads((campaign/'plan.json').read_text());ready=json.loads((campaign/'BASELINE_READY.json').read_text())
assert ready['accepted'] and ready['base_commit']=='ff2c1d6d3eaf4829c95c39a6032585fa9b49b7b5'
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
tag='track3-output-h04:'+commit[:12];docker=['docker','--context','colima-agenthon']

def slot(args,label):
    command=[sys.executable,str(campaign/'docker_slot.py'),'--',*args]
    (a.out/(label+'-command.json')).write_text(json.dumps(command,indent=2)+'\n')
    with (a.out/(label+'.log')).open('w') as log:subprocess.run(command,check=True,cwd=root,stdout=log,stderr=subprocess.STDOUT)

if a.build:
    # All identity inspection is also a complete Docker subprocess under the slot.
    for side,image,expected in [('runtime','track3-output-base:ff2c1d6',ready['runtime_image']),
                                ('builder','track3-output-base-builder:ff2c1d6',ready['builder_image'])]:
        slot(docker+['image','inspect','--format','{{.Id}}',image],'identity-'+side)
        assert (a.out/('identity-'+side+'.log')).read_text().strip()==expected
    slot(docker+['build','--platform=linux/amd64','--network=none',
         '--build-arg','BASE_IMAGE=track3-output-base:ff2c1d6','--build-arg','BUILDER_IMAGE=track3-output-base-builder:ff2c1d6',
         '-f',str(area/'Dockerfile'),'-t',tag,str(root)],'build')
    slot(docker+['image','inspect',tag],'candidate-image')
if a.bindings:
    target=a.out/'bindings';target.mkdir(exist_ok=True)
    slot(docker+['run','--rm','--platform=linux/amd64','--network=none','--cpus=4','--memory=16g','--memory-swap=16g',
         '-v',str(plan['corpus'])+':/corpus:ro','-v',str(target)+':/evidence',
         '--entrypoint','python',tag,'/opt/h04-tests/run_bindings.py','--pinned','--root','/opt',
         '--corpus','/corpus','--out','/evidence'],'bindings')
if a.controls or a.timing:
    if a.controls and a.timing:raise SystemExit('Run controls and timing as separate recorded invocations.')
    args=[sys.executable,str(campaign/'run_focused.py'),'--slug','h04-lifecycle-pipeline',
          '--candidate-image',tag,'--candidate-commit',commit,'--out',str(a.out/'focused')]
    if a.controls:args.append('--controls-only')
    slot(args,'focused-controls' if a.controls else 'fixed-timing')
