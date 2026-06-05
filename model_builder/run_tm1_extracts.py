#!/usr/bin/env python3
import subprocess
from pathlib import Path

# Scripts are directly in the root (no attachments/ folder)
scripts = [
    "extract_rules.py",
    "extract_dimensions.py",
    "extract_cubes.py",
    "extract_subsets.py",
    "extract_ti.py",
    "extract_views.py",
]

print("🚀 Starting TM1 Extraction\n")

base_dir = Path.cwd()

for script in scripts:
    script_path = base_dir / script
    if not script_path.exists():
        print(f"❌ Script not found: {script}")
        continue
    
    print(f"▶ Running {script} ...")
    try:
        result = subprocess.run(
            ["python3", str(script_path)],
            cwd=base_dir,
            check=False
        )
        if result.returncode == 0:
            print(f"   ✅ Completed\n")
        else:
            print(f"   ⚠️  Finished with warnings/errors (code {result.returncode})\n")
    except Exception as e:
        print(f"   ❌ Failed: {e}\n")

print("🎉 All extractions finished!")
print(f"📁 Output folder: {base_dir}/tm1_objects/")
