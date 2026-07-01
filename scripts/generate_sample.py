from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from city_modeler.pipeline import generate_sample

if __name__ == "__main__":
    out = ROOT / "data" / "outputs" / "sample"
    summary = generate_sample(out)
    files = summary["files"]
    print("Generated built-in offline test model:")
    print(f"  3MF: {out / files['3mf']}")
    print(f"  GLB: {out / files['glb']}")
    print(f"  STL: {out / files['stl']}")
    print(f"  Project JSON: {out / files['project']}")
    print(f"  Attribution: {out / 'ATTRIBUTION.txt'}")
    print(f"  Objects: {summary['validation_3mf']['objects']}")
    print(f"  Triangles: {summary['validation_3mf']['triangles']}")
