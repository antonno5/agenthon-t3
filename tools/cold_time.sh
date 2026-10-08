#!/bin/bash
# usage: cold_time.sh IMAGE SCENARIO.json  -> one run after dropping the page cache:
# prints "window_s full_s" (Docker StartedAt..FinishedAt, and wall time of create+start+rm).
IMG=$1; SC=$2
O=$(mktemp -d /tmp/claude-1001/cold.XXXX); chmod 777 $O
docker run --rm --privileged alpine sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches' >/dev/null 2>&1
s=$(date +%s%N)
cid=$(docker create --network none --read-only --user 65534:65534 --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m --cpus 4 -v $(dirname $SC):/input:ro -v $O:/output $IMG simulate --config /input/$(basename $SC) --out /output/trace.parquet)
docker start -a $cid >/dev/null 2>&1
t=$(docker inspect -f '{{.State.StartedAt}} {{.State.FinishedAt}}' $cid); docker rm $cid >/dev/null
e=$(date +%s%N)
python3 -c "
from datetime import datetime
a,b='$t'.split(); f=lambda x: datetime.fromisoformat(x[:26].rstrip('Z'))
print(f'{(f(b)-f(a)).total_seconds():.3f} {($e-$s)/1e9:.3f}')"
rm -rf $O
