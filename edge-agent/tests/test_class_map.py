"""场景类别号和检测模型类别号对不上时，按名字改到模型的号。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from algorithms.class_map import align_class_ids, apply_model_class_ids


class _Rule:
    def __init__(self, class_ids):
        self.id = 'glasses'
        self.class_ids = class_ids


class _Runtime:
    def __init__(self, names):
        self.model = type('Model', (), {'names': names})()


class _Log:
    def __init__(self):
        self.warnings = []

    def warning(self, message, *args, **_kwargs):
        self.warnings.append(message % args if args else str(message))


class AlignClassIdsTest(unittest.TestCase):
    def test_exact_name_moves_to_the_model_id(self):
        aligned, notes = align_class_ids(
            [3],
            {3: 'glasses'},
            {0: 'person', 2: 'glasses'},
        )
        self.assertEqual(aligned, [2])
        self.assertIn('改到 2', notes[0])

    def test_chinese_label_keeps_an_id_the_model_has(self):
        aligned, notes = align_class_ids(
            [2],
            {2: '眼镜'},
            {0: 'person', 2: 'glasses'},
        )
        self.assertEqual(aligned, [2])
        self.assertEqual(notes, [])

    def test_missing_chinese_id_uses_the_english_alias(self):
        aligned, notes = align_class_ids(
            [9],
            {9: '眼镜'},
            {0: 'person', 2: 'glasses'},
        )
        self.assertEqual(aligned, [2])
        self.assertIn('改到 2', notes[0])

    def test_unknown_id_lists_model_classes(self):
        aligned, notes = align_class_ids(
            [9],
            {9: '火焰'},
            {0: 'person', 1: 'phone'},
        )
        self.assertEqual(aligned, [9])
        self.assertIn('不在检测模型里', notes[0])
        self.assertIn('0:person', notes[0])

    def test_runtime_without_names_is_a_noop(self):
        rule = _Rule([3])
        spec = {'id': 'watch', 'type': 'smart_watch', 'class_ids': [4]}
        apply_model_class_ids([rule], [spec], object(), {3: '眼镜'}, _Log())
        self.assertEqual(rule.class_ids, [3])
        self.assertEqual(spec['class_ids'], [4])
        self.assertFalse(hasattr(rule, '_class_note'))

    def test_apply_rewrites_rules_and_fusions(self):
        rule = _Rule([9])
        spec = {'id': 'watch', 'type': 'smart_watch', 'class_ids': [8]}
        log = _Log()
        runtime = _Runtime({2: 'glasses', 3: 'watch'})
        apply_model_class_ids(
            [rule],
            [spec],
            runtime,
            [{'id': 9, 'name': '眼镜'}, {'id': 8, 'name': '手表'}],
            log,
        )
        self.assertEqual(rule.class_ids, [2])
        self.assertEqual(spec['class_ids'], [3])
        self.assertIn('改到 2', rule._class_note)
        self.assertIn('改到 3', spec['_class_note'])
        self.assertEqual(len(log.warnings), 2)
