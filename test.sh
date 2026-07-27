
rep=1
conc=4
ids="TC-005 TC-003 TC-015 TC-017 TC-029 TC-027"

cmd="python -u -m tests.evaluation.cli run --repeat $rep --concurrency $conc --ids $ids"

$cmd  2>&1 | tee HDCno.log

$cmd --with-hdc --verbose-hdc --hdc-namespace incomplete 2>&1 | tee HDCinc.log
$cmd --with-hdc --verbose-hdc --hdc-namespace complete 2>&1 | tee HDC.log
$cmd --with-hdc --verbose-hdc --hdc-namespace overcomplete 2>&1 | tee HDCover.log