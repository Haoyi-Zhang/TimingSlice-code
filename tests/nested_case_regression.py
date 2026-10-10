"""Owned nested-case source-semantics checks; no public RTL or experiments."""
from pathlib import Path
import itertools
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import rtl_frontend as front, rtl_translation_checker as validation


def value(node, env):
    """Tiny test-local evaluator for the Boolean IR used by this fixture."""
    op, *args = node
    if op == 'const':
        return args[1]
    if op == 'var':
        return env[args[0]]
    if op == 'not':
        return 1 - value(args[0], env)
    if op == 'mux':
        return value(args[1] if value(args[0], env) else args[2], env)
    a, b = (value(child, env) for child in args)
    if op == 'and':
        return a & b
    if op == 'or':
        return a | b
    if op == 'eq':
        return int(a == b)
    raise AssertionError(op)


class NestedCaseTests(unittest.TestCase):
    def test_default_orders_and_distinct_register_targets(self):
        for outer_first, inner_first in itertools.product((False, True), repeat=2):
            inner = ["2'd0: q <= 1'b1;", "default: r <= 1'b1;"]
            if inner_first:
                inner.reverse()
            outer = ["2'd0: p <= 1'b1;",
                     'default: begin case (b) ' + ' '.join(inner) + ' endcase end']
            if outer_first:
                outer.reverse()
            source = ('module owned(input clk, input [1:0] a, input [1:0] b, '
                      'output reg p, output reg q, output reg r); '
                      'always @(posedge clk) case (a) ' + ' '.join(outer) +
                      ' endcase endmodule')
            raw, _ = front.translate(source, module_name='owned', model_id='owned',
                clock='clk', done_expression='q', horizon=1,
                domains={'a': [0, 1, 2, 3], 'b': [0, 1, 2, 3]},
                initial_state={'p': 0, 'q': 0, 'r': 0}, cuttable=set())
            parsed = validation._parse_source(source, 'owned')
            widths = {name: signal.width for name, signal in parsed.signals.items()}
            next_expr = {name: ('var', name) for name in ('p', 'q', 'r')}
            for update in parsed.updates:
                guard, _, _ = validation._compile_source(update.condition, widths)
                rhs, _, _ = validation._compile_source(update.value, widths, 1)
                next_expr[update.target] = ('mux', guard, rhs, next_expr[update.target])
            implementations = ({reg['name']: reg['next'] for reg in raw['registers']},
                               next_expr)
            for a, b, p, q, r in itertools.product(range(4), range(4), (0, 1), (0, 1), (0, 1)):
                env = dict(a=a, b=b, p=p, q=q, r=r)
                # Direct source dispatch: only the selected outer item runs.
                expected = {'p': 1 if a == 0 else p,
                            'q': 1 if a != 0 and b == 0 else q,
                            'r': 1 if a != 0 and b != 0 else r}
                for index, expressions in enumerate(implementations):
                    with self.subTest(outer_first=outer_first, inner_first=inner_first,
                                      parser=index, env=env):
                        self.assertEqual({name: value(expr, env)
                                          for name, expr in expressions.items()}, expected)


if __name__ == '__main__':
    unittest.main()
