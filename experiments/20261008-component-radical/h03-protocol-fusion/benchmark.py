"""Executive summary: measure the engine alone in one fixed pinned paired campaign.

The timer excludes input parsing, trace finalization and Parquet output. It
includes engine initialization, event ordering, all ledger column appends,
agent lifecycle/quote logs, handlers, RNG and destruction of the Sim state.
Result column destruction occurs after the timer on both sides.
"""
import argparse, hashlib, json, os, platform, statistics, subprocess
from pathlib import Path

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--artifacts',type=Path,required=True); ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    assert platform.system()=='Linux' and platform.machine()=='x86_64', 'Pinned linux/amd64 runtime required'
    assert os.environ.get('T3_COMPONENT_BENCH_AUTHORIZED')=='1', 'Requires coordinator phase-2 dispatch'
    import numpy, pandas, pyarrow, scipy
    versions={'numpy':numpy.__version__,'pandas':pandas.__version__,'pyarrow':pyarrow.__version__,'scipy':scipy.__version__,'python':platform.python_version()}
    assert versions==dict(numpy='1.26.4',pandas='1.5.3',pyarrow='15.0.2',scipy='1.17.1',python='3.11.17'),versions
    assert not args.out.exists(), 'Never overwrite/repeat a viewed campaign'
    binaries={side:args.artifacts/'bin'/(side+'-component') for side in ['base','candidate']}
    inputs=json.loads((args.artifacts/'inputs.json').read_text())['inputs']
    records=[]
    result={'executive_summary':'Uninstrumented engine-only measurements on frozen H3 timing inputs; every pair and outlier is retained.','versions':versions,'rankable':False,'warmups_per_side':1,'pairs':5,'order':['AB','BA','AB','BA','AB'],'timer_boundary':__doc__.strip(),'binary_sha256':{s:digest(p) for s,p in binaries.items()},'records':records,'complete':False}
    def save(): args.out.write_text(json.dumps(result,indent=2)+'\n')
    def run(side,item):
        return json.loads(subprocess.check_output([str(binaries[side]),item['path'],'-'],text=True))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    for item in inputs:
        if not item['timing']: continue
        record={**item,'warmup':{},'pairs':[]};records.append(record)
        for side in ['base','candidate']: record['warmup'][side]=run(side,item); save()
        for order in result['order']:
            pair={'order':order}
            for side in (['base','candidate'] if order=='AB' else ['candidate','base']): pair[side]=run(side,item)
            assert pair['base']['messages']==pair['candidate']['messages']
            record['pairs'].append(pair);save()
        ratios=[p['base']['engine_seconds']/p['candidate']['engine_seconds'] for p in record['pairs']]
        reductions=[100*(1-p['candidate']['engine_seconds']/p['base']['engine_seconds']) for p in record['pairs']]
        record['median_speedup']=statistics.median(ratios)
        record['median_time_reduction_percent']=statistics.median(reductions);save()
    result['complete']=True;save()
if __name__=='__main__':main()
