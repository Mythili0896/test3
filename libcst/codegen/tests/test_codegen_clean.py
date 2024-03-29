# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

# pyre-strict
import os
import os.path

import libcst.codegen.gen_visitor_functions as visitor_codegen
from libcst.codegen.generate import format_file
from libcst.testing.utils import UnitTest


class TestCodegenClean(UnitTest):
    def test_codegen_clean_visitor_functions(self) -> None:
        """
        Verifies that codegen of visitor functions would not result in a
        changed file. If this test fails, please run 'tox -e codegen' to
        generate new files.
        """
        new_code = "\n".join(visitor_codegen.generated_code)
        new_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "visitor_codegen.py.deleteme"
        )
        with open(new_file, "w") as fp:
            fp.write(new_code)
        try:
            format_file(new_file)
        except Exception:
            # We failed to format, but this is probably due to invalid code that
            # black doesn't like. This test will still fail and report to run codegen.
            pass
        with open(new_file, "r") as fp:
            new_code = fp.read()
        os.remove(new_file)
        with open(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "../../_typed_visitor.py"
            ),
            "r",
        ) as fp:
            old_code = fp.read()

        # Now that we've done simple codegen, verify that it matches.
        self.assertTrue(
            old_code == new_code, "libcst._typed_visitor needs new codegen!"
        )
