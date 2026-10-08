"""Executive summary: compare base and candidate on only the frozen H3 public inputs.

Prepare and compile host/pinned engine checks, isolated queue tests, and separate
component diagnostics. This script never launches Docker or a timing campaign.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path

AREA = Path(__file__).resolve().parent
ROOT = AREA.parents[2]
BASE = '33027d74553e9a318d66557fe0f7b7bed84cfa38'
FIELDS = 'seed start_time mkt_open mkt_close stop_time oracle_close default_delay r_bar kappa fund_vol megashock_lambda_a megashock_mean megashock_var pipeline_delay computation_delay stp lat_model lat_mu lat_sigma lat_min lat_max lat_alpha lat_mean'.split()
FLAGS = ['-std=c++17','-O2','-fno-fast-math','-ffp-contract=off','-fno-strict-aliasing','-Wall','-Wno-unused-function']

def dump(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def base_source(path):
    return subprocess.check_output(['git','show',f'{BASE}:{path}'],cwd=ROOT)

def prepare_baseline(out):
    base = out/'base'; base.mkdir(parents=True,exist_ok=True)
    hashes={}
    for name in ['engine.cpp','engine.hpp','book.hpp','rng.hpp']:
        data=base_source('baselines/native/'+name)
        (base/name).write_bytes(data); hashes[name]=hashlib.sha256(data).hexdigest()
    # Identical output structs; only add an optional diagnostic API to the baseline header.
    (base/'engine.hpp').write_bytes((ROOT/'baselines/native/engine.hpp').read_bytes())
    original=(base/'engine.cpp').read_text()
    (base/'original-engine.cpp').write_text(original)
    # Instrument an experiment-only baseline, never the baseline production checkout.
    s=original.replace('explicit Sim(Params p, MessageSink* sink) : P(std::move(p)), message_sink(sink) {}',
      'explicit Sim(Params p, MessageSink* sink, ProtocolCounts* out, bool finalize) : P(std::move(p)), message_sink(sink), counts_out(out), finalize_trace(finalize) {}')
    s=s.replace('  MessageSink* message_sink;', '  MessageSink* message_sink;\n  ProtocolCounts* counts_out;\n  bool finalize_trace;\n  ProtocolCounts counts{};')
    s=s.replace('  int32_t new_msg(uint8_t type) {', '  int32_t new_msg(uint8_t type) {\n#ifdef T3_PROTOCOL_DIAGNOSTICS\n    ++counts.pool_allocations;\n#endif')
    s=s.replace('    heap.push_back(e);', '#ifdef T3_PROTOCOL_DIAGNOSTICS\n    ++counts.heap_pushes;\n#endif\n    heap.push_back(e);')
    s=s.replace('    std::pop_heap(heap.begin()', '#ifdef T3_PROTOCOL_DIAGNOSTICS\n    ++counts.heap_pops;\n#endif\n    std::pop_heap(heap.begin()')
    s=s.replace('      heap_push(re);','#ifdef T3_PROTOCOL_DIAGNOSTICS\n      ++counts.requeues;\n#endif\n      heap_push(re);')
    s=s.replace('    agent_times[r] = current_time;', '#ifdef T3_PROTOCOL_DIAGNOSTICS\n    ++counts.deliveries;\n#endif\n    agent_times[r] = current_time;')
    s=s.replace('  return extract();', '''  if (counts_out) *counts_out = counts;
  if (!finalize_trace) {
    Result res; res.messages = std::move(mcols); res.n_messages = n_messages; return res;
  }
  return extract();''')
    s=s.replace('  Sim sim(std::move(params), sink);','  Sim sim(std::move(params), sink, nullptr, true);')
    s=s.replace('\n}  // namespace t3','''
Result run_component(Params params, ProtocolCounts* counts) {
  Sim sim(std::move(params), nullptr, counts, false); return sim.run();
}
}  // namespace t3''')
    (base/'engine.cpp').write_text(s)
    dump(out/'baseline-adaptation.json',{'executive_summary':'Experiment-only baseline adds counters and a trace-finalization-free entry point, without changing event logic.','base_commit':BASE,'original_source_hashes':hashes,'adapted_engine_sha256':sha(base/'engine.cpp'),'production_flags':FLAGS})

def prepare_inputs(out, plan, corpus):
    sys.path.insert(0,str(ROOT/'baselines'))
    from abides_fork import native
    if native._t3engine is None:
        # Exercise the mapper's existing NumPy fallback when no native extension is built.
        # Pinned preparation uses the installed NumPy 1.26.4; host numeric identity is local.
        from types import SimpleNamespace
        native._t3engine = SimpleNamespace(numpy_log=lambda x: None)
    _build = native._build
    exp=next(x for x in plan['experiments'] if x['slug']=='h03-protocol-fusion')
    inputs=[]; configdir=out/'inputs'; configdir.mkdir(exist_ok=True)
    for unit in exp['units']+exp['correctness_only_units']:
        folder=corpus/unit
        sources=[folder/'scenario.json'] if (folder/'scenario.json').exists() else sorted((folder/'scenarios').glob('*.json'))
        for source in sources:
            cfg=_build(json.loads(source.read_text())); assert cfg is not None,source
            name=unit+'--'+source.stem
            target=configdir/(name+'.txt')
            parts=[str(cfg[k]) for k in FIELDS]+[str(len(cfg['jumps']))]
            for jump in cfg['jumps']: parts.extend(map(str,jump))
            parts.append(str(len(cfg['agents'])))
            for agent in cfg['agents']: parts.extend(map(str,agent))
            target.write_text('\n'.join(parts)+'\n')
            inputs.append(dict(name=name,unit=unit,timing=unit in exp['units'],scenario_sha256=sha(source),mapped_sha256=sha(target),path=str(target)))
    dump(out/'inputs.json',{'executive_summary':'Inputs use the unchanged mapping for the frozen public H3 scenarios only.','inputs':inputs})

def compile_all(out, compiler, sanitize):
    build=out/'bin'; build.mkdir(exist_ok=True)
    commands=[]
    for side, src in [('base',out/'base'),('candidate',ROOT/'baselines/native')]:
        for mode in ['full','component','diagnostic']:
            engine = src/'original-engine.cpp' if side=='base' and mode=='full' else src/'engine.cpp'
            args=[compiler,*FLAGS,'-I'+str(src),str(engine),str(AREA/'driver.cpp'),'-o',str(build/(side+'-'+mode))]
            if mode!='full': args.insert(1,'-DT3_COMPONENT_DRIVER')
            if mode=='diagnostic': args.insert(1,'-DT3_PROTOCOL_DIAGNOSTICS')
            subprocess.run(args,check=True); commands.append(args)
    args=[compiler,*FLAGS,'-I'+str(ROOT/'baselines/native'),str(AREA/'queue_test.cpp'),'-o',str(build/'queue')]
    subprocess.run(args,check=True); commands.append(args)
    if sanitize:
        san=['-g','-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer']
        if sys.platform == 'linux':
            san += ['-static-libasan', '-static-libubsan']  # runtime image has no compiler sanitizer DSOs
        args=[compiler,*FLAGS,*san,'-I'+str(ROOT/'baselines/native'),str(ROOT/'baselines/native/engine.cpp'),str(AREA/'driver.cpp'),'-o',str(build/'candidate-sanitized')]
        subprocess.run(args,check=True); commands.append(args)
        args=[compiler,*FLAGS,*san,'-I'+str(ROOT/'baselines/native'),str(AREA/'queue_test.cpp'),'-o',str(build/'queue-sanitized')]
        subprocess.run(args,check=True); commands.append(args)
    dump(out/'compile-commands.json',{'executive_summary':'Both sides use the same IEEE floating-point flags; component counters are disabled in timed binaries.','commands':commands})

def exact_files(left,right):
    with left.open('rb') as a,right.open('rb') as b:
        while True:
            x,y=a.read(1024*1024),b.read(1024*1024)
            if x!=y: raise AssertionError('output columns differ')
            if not x: return

def driver(out,side,inp,path):
    return json.loads(subprocess.check_output([str(out/'bin'/side),inp,str(path)],text=True))

def checks(out, sanitized):
    leaks = 0 if sys.platform == 'darwin' else 1
    env=dict(os.environ,ASAN_OPTIONS=f'detect_leaks={leaks}:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    subprocess.run([str(out/'bin/queue')],check=True,env=env)
    if sanitized: subprocess.run([str(out/'bin/queue-sanitized')],check=True,env=env)
    records=[]
    for item in json.loads((out/'inputs.json').read_text())['inputs']:
        l,r=out/'base-columns.bin',out/'candidate-columns.bin'
        a=driver(out,'base-full',item['path'],l); b=driver(out,'candidate-full',item['path'],r)
        exact_files(l,r); assert a['messages']==b['messages'] and a['trace_rows']==b['trace_rows']
        rec={**item,'byte_equal_all_output_columns':True,'sha256':sha(l),'messages':a['messages'],'trace_rows':a['trace_rows']}
        if sanitized:
            subprocess.run([str(out/'bin/candidate-sanitized'),item['path'],str(r)],check=True,env=env,stdout=subprocess.DEVNULL)
            exact_files(l,r); rec['asan_ubsan_exact']=True
        l.unlink(); r.unlink(); records.append(rec)
        dump(out/'correctness.json',{'executive_summary':'Host/pinned C++ output column checks compare the unchanged base with the candidate; full Parquet and shared gates remain a separate requirement.','isolated_queue_pass':True,'sanitized':sanitized,'leak_detection_enabled':bool(leaks),'complete':len(records)==len(json.loads((out/'inputs.json').read_text())['inputs']),'records':records})
        print(item['name'],a['messages'],'exact',flush=True)

def diagnostics(out):
    records=[]
    for item in json.loads((out/'inputs.json').read_text())['inputs']:
        a=driver(out,'base-diagnostic',item['path'],'-'); b=driver(out,'candidate-diagnostic',item['path'],'-')
        assert a['messages']==b['messages']==a['deliveries']==b['deliveries']
        for data in [a,b]: data.pop('engine_seconds')
        records.append({**item,'base':a,'candidate':b,'fast_delivery_fraction':b['inline_deliveries']/b['deliveries'],'heap_push_reduction':1-b['heap_pushes']/a['heap_pushes'],'heap_pop_reduction':1-b['heap_pops']/a['heap_pops'],'pool_allocation_reduction':1-b['pool_allocations']/a['pool_allocations']})
    dump(out/'structural.json',{'executive_summary':'Diagnostic counters measure inline delivery and heap/pool reductions separately from performance.','records':records})

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=AREA/'artifacts/host'); ap.add_argument('--plan',type=Path,required=True)
    ap.add_argument('--corpus',type=Path,required=True); ap.add_argument('--compiler',default='c++')
    ap.add_argument('--phase',choices=['prepare','remap','build','check','diagnostic','all'],default='all'); ap.add_argument('--sanitize',action='store_true')
    args=ap.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    plan=json.loads(args.plan.read_text())
    if args.phase in ['prepare','all']: prepare_baseline(args.out)
    if args.phase in ['prepare','remap','all']: prepare_inputs(args.out,plan,args.corpus)
    if args.phase in ['build','all']: compile_all(args.out,args.compiler,args.sanitize)
    if args.phase in ['check','all']: checks(args.out,args.sanitize)
    if args.phase in ['diagnostic','all']: diagnostics(args.out)
