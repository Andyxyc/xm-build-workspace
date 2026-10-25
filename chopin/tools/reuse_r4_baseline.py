"""Reuse exact previously compiled baseline bytes, then retain their provenance."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

workspace = Path(os.environ['GITHUB_WORKSPACE'])
source = workspace / 'r4-reference/release-evidence'
target = workspace / 'release-evidence'
expected = {
    'Image.vendor-baseline': 'ed86ec138f936e2bf9af24d274ed583d4c71cc07ff7407414ccc4601cfff5d56',
    'vendor-baseline.Module.symvers': 'bea9625ba452555e6210ac934e660ebf25f0db44d18a9c30e55920169d714051',
    'vendor-baseline.config': '99e8e393cc370ba1e96b5709c0b61df7296604921295c431bd15f472d66bc2c4',
    'vendor-baseline.System.map': '64391c377cd577b1d791220d3372e11d621abddd45504599739ce5e2c1839f6e',
    'clang-commit.txt': 'da79d3846cca111deca159a5d05a7264aefc3bdf31e9542d0d887cba1db62c46',
    'stock-profile-application.json': '482bec55c0f7d226311df622d4d635941399e7d3570920cd463381de9c6ae3dc',
    'module-validation-restoration.json': '3265963168c33bcdd3f1db0686cc3bfa1e37b94943c9b592104ebba0741af091',
}
for name, sha in expected.items():
    assert hashlib.sha256((source / name).read_bytes()).hexdigest() == sha, name
root = Path(os.environ['WORKSPACE'])
compiler = subprocess.check_output(['git', '-C', str(root / 'clang'), 'rev-parse', 'HEAD'], text=True).strip()
assert compiler == (source / 'clang-commit.txt').read_text().strip(), compiler
for name in ['stock-profile-application.json', 'module-validation-restoration.json']:
    assert (target / name).read_bytes() == (source / name).read_bytes(), name
for name in expected:
    if name.startswith('vendor-baseline') or name == 'Image.vendor-baseline':
        shutil.copyfile(source / name, target / name)
record = {'source_run': 40176463381, 'source_commit': 'b342b4ea1fb5c634ab13c5a106e1b0bb61822079',
          'artifact_id': 12592951726, 'hashes': expected,
          'status': 'EXACT_R4_BASELINE_REUSED_NOT_RECOMPILED', 'hardware_validated': False}
(target / 'vendor-baseline-reference.json').write_text(json.dumps(record, indent=2))
print(record['status'])
