#!/usr/bin/env python3
"""Reuse a successful baseline step for the same pinned vendor/compiler profile."""
import json,os,sys,time,urllib.request
from pathlib import Path

run_id=int(sys.argv[1])
assert run_id==40132880594,'Only the audited stock-aligned baseline source/compiler profile is accepted'
url=f'https://api.github.com/repos/Andyxyc/xm-build-workspace/actions/runs/{run_id}/jobs'
deadline=time.monotonic()+3600
last=None
while time.monotonic()<deadline:
    req=urllib.request.Request(url,headers={'User-Agent':'chopin-baseline-reuse','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=30) as response:
        data=json.load(response)
    assert len(data['jobs'])==1
    job=data['jobs'][0]
    steps=[s for s in job['steps'] if s['name']=='Compile unmodified vendor baseline before root integration']
    assert len(steps)==1
    step=steps[0]
    state=(step['status'],step.get('conclusion'))
    if state!=last:
        print('Audited baseline step:',state,flush=True)
        last=state
    if step['status']=='completed':
        assert step['conclusion']=='success',step
        evidence={'run_id':run_id,'job_id':job['id'],'step':step,
                  'vendor':'0647a49c9557faa92b90c4ae188587787226be9e',
                  'profile':'Proton Clang 13; chopin_user_defconfig plus stock-profile.json from 8284e43',
                  'url':f'https://github.com/Andyxyc/xm-build-workspace/actions/runs/{run_id}'}
        out=Path(os.environ['GITHUB_WORKSPACE'])/'release-evidence/vendor-baseline-reference.json'
        out.write_text(json.dumps(evidence,indent=2))
        break
    if job['status']=='completed':
        raise SystemExit('Reference job ended before a successful vendor baseline')
    time.sleep(30)
else:
    raise SystemExit('Reference baseline did not complete within the bounded wait')
