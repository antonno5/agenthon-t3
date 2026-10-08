"""Executive summary: summarize three completed, independently audited experiments."""
import json
from pathlib import Path

CAMPAIGN = Path(__file__).resolve().parent
PLAN = json.loads((CAMPAIGN / 'plan.json').read_text())
AREA = Path(PLAN['report_directory'])


def main():
    audit = json.loads((AREA / 'independent-audit.json').read_text())
    assert audit['accepted'] and audit['production_unchanged']
    summary = {
        'executive_summary': 'Three isolated native optimizations were tested on only their frozen scenarios. Complete-container percentages and component diagnostics are separate; no production adoption occurred.',
        'accepted': True, 'rankable': False, 'adopted': False,
        'baseline_checkout': PLAN['base_commit'],
        'baseline_image_source_commit': PLAN['baseline_image_source_commit'],
        'baseline_image': PLAN['baseline_image'],
        'policy': PLAN['policy'], 'hypotheses': [],
    }
    lines = [summary['executive_summary'], '',
             'Percentages below mean reduction in elapsed time: `100 * (1 - candidate_median / baseline_median)`. Positive is faster; negative is slower. They are not percentages of throughput increase.', '',
             'Each scenario has one excluded warmup per side and five fixed AB/BA pairs. Every sample is retained. Runs use Docker start-to-finish wall time, four CPUs, 16GiB memory and swap cap, network none, pinned Python 3.11.17 / Arrow 15.0.2, and mandatory native execution. All campaigns ran sequentially under a shared lock.', '',
             'These are local measurements on an ARM64 Mac running emulated Linux amd64, not official timing hardware. No scenario outside the assigned subset was timed.', '',
             '| Hypothesis | Scenario | Baseline, s | Candidate, s | Time reduction | Faster pairs |',
             '|---|---|---:|---:|---:|---:|']
    for exp, checked in zip(PLAN['experiments'], audit['hypotheses']):
        assert exp['slug'] == checked['slug']
        done = json.loads((AREA / ('DONE-' + exp['slug'] + '.json')).read_text())
        result = json.loads((AREA / exp['slug'] / 'primary-result.json').read_text())
        item = {'slug': exp['slug'], 'title': exp['title'], 'branch': exp['branch'],
                'worktree': exp['worktree'], 'thread_id': exp['thread_id'],
                'final_commit': done['final_commit'],
                'measured_commit': result['candidate_implementation_commit'],
                'rows': checked['rows'], 'component_rows': checked['component_rows'], 'report': str(AREA / exp['slug'] / 'README.md')}
        summary['hypotheses'].append(item)
        for row in checked['rows']:
            lines.append(f"| [{exp['slug']}]({exp['slug']}/README.md) | `{row['unit']}` | {row['baseline_ms']/1000:.4f} | {row['candidate_ms']/1000:.4f} | {row['time_reduction_pct']:+.2f}% | {row['candidate_faster_pairs']}/5 |")
    all_rows = [r for h in summary['hypotheses'] for r in h['rows']]
    summary['any_full_run_at_least_2x'] = any(r['speedup_factor'] >= 2 for r in all_rows)
    lines += ['', ('At least one measured full run reached 2x.' if summary['any_full_run_at_least_2x'] else 'None of the tested changes accelerated a complete scenario by 2x. The per-scenario results above are the outcome of this campaign.'), '',
              'The component table uses different, explicitly bounded workloads for each hypothesis. Its percentages do not imply the same reduction in complete-container wall time.', '',
              '| Hypothesis / timed component | Scenario | Time reduction | Speed factor |',
              '|---|---|---:|---:|']
    for h in summary['hypotheses']:
        label = {'h01-trace-stream':'H1 capture + finalization', 'h02-parquet-parallel':'H2 overlapping memory encoders', 'h03-protocol-fusion':'H3 engine excluding finalization/writer'}[h['slug']]
        for row in h['component_rows']:
            if h['slug']=='h02-parquet-parallel' and (row['mode']!='overlap' or row['clock']!='wall_seconds'):
                continue
            lines.append(f"| {label} | `{row['unit']}` | {row['time_reduction_pct']:+.2f}% | {row['speedup_factor']:.3f}x |")
    lines += ['', 'Component measurements use narrower boundaries and do not replace the table above. See each hypothesis report for all samples, boundaries, component percentages and structural counters.', '',
              'Both journals passed exact byte/schema/ordered-value checks and the unchanged shared gates. Assigned correctness-only cases, host checks, Linux ASan/UBSan and isolated boundary/error tests are retained in the individual archives. [Independent audit](independent-audit.json) recomputes percentages, checks output hashes, scenario scope, unchanged sources and nonoverlapping timing launches.', '',
              'Implementations remain isolated in these branches; the main production code was not changed:', '']
    for h in summary['hypotheses']:
        lines.append(f"- `{h['branch']}`; final commit `{h['final_commit']}`; worktree `{h['worktree']}`; chat `{h['thread_id']}`.")
    lines += ['', 'The cached baseline image was built at `286ae974`; its production sources were independently verified identical to the comparison checkout `33027d74`. The runner legacy `baseline_image_source_commit` field records the comparison checkout; the precise image origin is preserved in the frozen plan, baseline audit and summary.json here.', '',
              'Reproduction and provenance: [frozen plan](plan.json), [baseline audit](baseline-audit.json), [corpus preflight](corpus-preflight.json), [primary runner](run_focused.py). Full raw evidence is preserved below each hypothesis directory; large closed journal payloads are hardlinked to save disk space. Text reports and tools are copied independently.', '']
    (AREA / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    (AREA / 'README.md').write_text('\n'.join(lines))
    print(json.dumps({'accepted': True, 'any_full_run_at_least_2x': summary['any_full_run_at_least_2x'], 'hypotheses': summary['hypotheses']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
