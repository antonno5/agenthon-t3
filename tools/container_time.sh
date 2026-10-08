#!/bin/bash
# usage: container_time.sh IMAGE SCENARIO.json [repeats]  -> per-run events/sec from the Docker
# daemon's own StartedAt..FinishedAt window (the official Final timing definition).
IMG=$1; SC=$2; N=${3:-3}
O=$(mktemp -d /tmp/claude-1001/ct.XXXX); chmod 777 $O
for i in $(seq $N); do
  cid=$(docker create --network none -v $(dirname $SC):/input:ro -v $O:/output $IMG simulate --config /input/$(basename $SC) --out /output/trace.parquet)
  docker start -a $cid >/dev/null
  s=$(docker inspect -f '{{.State.StartedAt}} {{.State.FinishedAt}}' $cid); docker rm $cid >/dev/null
  n=$(python3 -c "import json;print(json.load(open('$O/events.json'))['n_events'])")
  python3 -c "
from datetime import datetime
a,b='$s'.split()
f=lambda x: datetime.fromisoformat(x[:26].rstrip('Z'))
w=(f(b)-f(a)).total_seconds(); print(f'{w:.3f}s', round($n/w), 'ev/s', $n)"
done
rm -rf $O
