"""Lo script anti-fingerprinting vero, eseguito in Node con un canvas finto."""

import json
import shutil
import subprocess
import unittest

from devtox import utils

HARNESS = r"""
const results = [];
for (let s = 0; s < 64; s++) {
  globalThis.location = { hostname: "site" + s + ".example" };
  class Ctx { getImageData(x, y, w, h) { return { data: new Uint8ClampedArray(w * h * 4) }; } }
  globalThis.CanvasRenderingContext2D = Ctx;
  globalThis.HTMLCanvasElement = class { toDataURL() {} toBlob() {} };
  globalThis.Navigator = class {};
  globalThis.window = globalThis;
  eval(SOURCE);
  const data = new Ctx().getImageData(0, 0, 16, 16).data;
  results.push(data.some((v) => v !== 0));
}
console.log(JSON.stringify(results));
"""


@unittest.skipIf(shutil.which("node") is None, "serve node")
class FingerprintNoiseTest(unittest.TestCase):
    def test_small_canvas_always_changes(self):
        source = utils.render_template("fingerprint.js", seed="abc", off_hosts="[]")
        script = "const SOURCE = " + json.dumps(source) + ";\n" + HARNESS
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        changed = json.loads(out.stdout)
        self.assertTrue(all(changed), f"{changed.count(False)} siti su 64 senza rumore")


if __name__ == "__main__":
    unittest.main()
