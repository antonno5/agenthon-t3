import hashlib,json,pathlib,subprocess,sys
repo=pathlib.Path('/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public')
area=repo/'experiments/20261008-component-radical'
docker=['docker','--context','colima-agenthon']
assert not subprocess.check_output(docker+['ps','-q'],text=True).strip(),'another container is running'
base='track3-ledger-arena:286ae97'; builder='track3-ledger-arena-builder:286ae97'
bid=subprocess.check_output(docker+['image','inspect','--format','{{.Id}}',base],text=True).strip()
cid=subprocess.check_output(docker+['image','inspect','--format','{{.Id}}',builder],text=True).strip()
plan=json.loads((area/'plan.json').read_text());assert bid==plan['baseline_image']
files=[p for p in (repo/'baselines/native').iterdir() if p.suffix in ['.cpp','.hpp']]+[repo/'baselines/build_native.py']
local={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
probe="import pathlib,json,hashlib; root=pathlib.Path('/src/native'); d={'baselines/native/'+p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.suffix in ['.cpp','.hpp']}; d['baselines/build_native.py']=hashlib.sha256(pathlib.Path('/src/native_build.py').read_bytes()).hexdigest(); print(json.dumps(d))"
remote=json.loads(subprocess.check_output(docker+['run','--rm','--platform','linux/amd64','--cpus','4','--memory','16g','--memory-swap','16g','--network','none',cid,'python','-c',probe],text=True))
assert local==remote,[(k,local.get(k),remote.get(k)) for k in set(local)|set(remote) if local.get(k)!=remote.get(k)]
probe="import pathlib,json,hashlib,sys,importlib.metadata as m; p=next(pathlib.Path('/opt/abides_fork').glob('_t3engine*.so')); print(json.dumps({'python':sys.version.split()[0],'packages':{n:m.version(n) for n in ['numpy','pandas','pyarrow','scipy']},'native_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
runtime=json.loads(subprocess.check_output(docker+['run','--rm','--platform','linux/amd64','--cpus','4','--memory','16g','--memory-swap','16g','--network','none',bid,'python','-c',probe],text=True))
assert runtime['packages']=={'numpy':'1.26.4','pandas':'1.5.3','pyarrow':'15.0.2','scipy':'1.17.1'}
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
assert head==plan['base_commit']
record=dict(executive_summary='The current develop native/build sources exactly match the cached baseline builder. The baseline runtime and compiler image IDs are pinned for fresh paired runs.',accepted=True,base_commit=head,baseline_image=bid,builder_image=cid,source_hashes=local,runtime=runtime,rankable=False)
(area/'baseline-audit.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
