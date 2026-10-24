import importlib.util
import unittest
from pathlib import Path


def _load(name):
    path = Path(__file__).resolve().parents[1] / 'app' / 'utils' / f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


catalog = _load('algorithm_catalog')
exam_task = _load('exam_task')


class SmartWatchSceneTest(unittest.TestCase):
    def test_catalog_defaults_to_one_click(self):
        preset = next(item for item in catalog.FUSION_SCENE_PRESETS if item['id'] == 'smart_watch')
        self.assertEqual(preset['name'], '智能手表作弊检测')
        self.assertEqual(preset['type'], 'smart_watch')
        self.assertEqual(preset['requires'], ['object_detection', 'pose_behavior'])
        self.assertEqual(preset['defaults']['min_touches'], 1)
        self.assertEqual(preset['defaults']['alert_type'], 'smart_watch')
        self.assertEqual(catalog.alert_type_labels()['smart_watch'], '智能手表作弊检测')

    def test_pose_catalog_does_not_include_fusion_scenes(self):
        ids = [item['id'] for item in catalog.POSE_SCENE_PRESETS]
        self.assertNotIn('smart_watch', ids)
        self.assertNotIn('smart_glasses', ids)
        self.assertNotIn('chin_rest', ids)
        self.assertNotIn('look_aside', ids)
        self.assertEqual(catalog.alert_type_labels()['smart_watch'], '智能手表作弊检测')

    def test_watch_fusion_needs_both_models_and_class(self):
        params = {'fusions': [{'type': 'smart_watch', 'class_ids': [4], 'enabled': True}]}
        self.assertEqual(
            exam_task.validate_scene_bindings(params, None, 2),
            '智能手表需要同时绑定目标检测算法和姿态算法',
        )
        self.assertEqual(
            exam_task.validate_scene_bindings({'fusions': [{'type': 'smart_watch', 'enabled': True}]}, 1, 2),
            '智能手表场景需要选择手表类别',
        )
        self.assertIsNone(exam_task.validate_scene_bindings(params, 1, 2))

    def test_glasses_class_error_stays_specific(self):
        self.assertEqual(
            exam_task.validate_scene_bindings(
                {'fusions': [{'type': 'smart_glasses', 'enabled': True}]},
                1,
                2,
            ),
            '智能眼镜场景需要选择眼镜类别',
        )

    def test_watch_is_removed_from_pose_behaviors(self):
        params = exam_task.sanitize_exam_params({
            'behaviors': [
                {'type': 'smart_watch', 'name': '手表'},
                {'type': 'gaze_away', 'name': '长时间不看屏幕'},
            ],
            'fusions': [{'type': 'smart_watch', 'class_ids': [4], 'enabled': True}],
        })
        self.assertEqual([item['type'] for item in params['behaviors']], ['gaze_away'])
        needs = exam_task.scene_needs(params)
        self.assertTrue(needs['need_od'])
        self.assertTrue(needs['need_pose'])
        self.assertEqual(needs['fusions'][0]['type'], 'smart_watch')


class DetectionSceneClassTest(unittest.TestCase):
    def test_od_presets_leave_class_empty(self):
        for preset in catalog.OD_SCENE_PRESETS:
            self.assertEqual(preset['defaults'].get('class_ids'), [], preset['id'])

    def test_merge_clears_legacy_class_zero(self):
        merged = catalog.merge_catalog_schema(
            {'scene_presets': [{
                'id': 'phone_detect',
                'type': 'presence',
                'name': '识别手机',
                'defaults': {'class_ids': [0], 'alert_type': 'phone_detect', 'enabled': True},
            }]},
            'object_detection',
        )
        phone = next(item for item in merged['scene_presets'] if item['id'] == 'phone_detect')
        self.assertEqual(phone['defaults']['class_ids'], [])

    def test_merge_keeps_explicit_class(self):
        merged = catalog.merge_catalog_schema(
            {'scene_presets': [{
                'id': 'phone_detect',
                'type': 'presence',
                'name': '识别手机',
                'defaults': {'class_ids': [3], 'alert_type': 'phone_detect', 'enabled': True},
            }]},
            'object_detection',
        )
        phone = next(item for item in merged['scene_presets'] if item['id'] == 'phone_detect')
        self.assertEqual(phone['defaults']['class_ids'], [3])

    def test_merge_drops_scenes_removed_from_catalog(self):
        merged_od = catalog.merge_catalog_schema(
            {'scene_presets': [
                {'id': 'phone_detect', 'name': '识别手机', 'defaults': {'class_ids': []}},
                {'id': 'camera_occlusion', 'name': '摄像头遮挡'},
                {'id': 'generic_presence', 'name': '区域内出现'},
                {'id': 'fire_smoke', 'name': '火情/烟雾'},
                {'id': 'person_absence', 'name': '人员缺席'},
            ]},
            'object_detection',
        )
        od_ids = [item['id'] for item in merged_od['scene_presets']]
        self.assertEqual(od_ids, [item['id'] for item in catalog.OD_SCENE_PRESETS])
        self.assertIn('camera_occlusion', od_ids)
        self.assertIn('glasses_detect', od_ids)
        self.assertIn('watch_detect', od_ids)

        merged_pose = catalog.merge_catalog_schema(
            {'scene_presets': [
                {'id': 'not_looking_screen', 'name': '长时间不看屏幕'},
                {'id': 'look_aside', 'name': '左右张望'},
                {'id': 'chin_rest', 'name': '手托下巴'},
                {'id': 'person_absence', 'name': '人员缺席'},
                {'id': 'smart_watch', 'name': '智能手表'},
            ]},
            'pose_behavior',
        )
        pose_ids = [item['id'] for item in merged_pose['scene_presets']]
        self.assertEqual(pose_ids, [item['id'] for item in catalog.POSE_SCENE_PRESETS])
        self.assertNotIn('look_aside', pose_ids)
        self.assertNotIn('chin_rest', pose_ids)

    def test_camera_health_is_hidden_from_catalog(self):
        self.assertTrue(catalog.is_hidden_algorithm('camera_health', 'camera_health', 'exam'))
        api = catalog.catalog_for_api()
        self.assertNotIn('camera_health', [item['value'] for item in api['engines']])
        self.assertNotIn('camera_health', [item['type'] for item in api['products']])
        self.assertIn('camera_occlusion', [item['id'] for item in api['od_scene_presets']])
        od_ids = [item['id'] for item in api['od_scene_presets']]
        fusion_ids = [item['id'] for item in api['fusion_scene_presets']]
        self.assertIn('glasses_detect', od_ids)
        self.assertIn('watch_detect', od_ids)
        self.assertEqual(fusion_ids, ['smart_glasses', 'smart_watch'])
        self.assertEqual(catalog.alert_type_labels()['glasses_detect'], '识别眼镜')
        self.assertEqual(catalog.alert_type_labels()['watch_detect'], '识别手表')
        self.assertEqual(catalog.alert_type_labels()['smart_glasses'], 'AI智能眼镜拍摄题目')
        self.assertEqual(catalog.alert_type_labels()['smart_watch'], '智能手表作弊检测')

    def test_enabled_detection_scene_requires_class(self):
        self.assertEqual(
            exam_task.validate_scene_bindings(
                {'rules': [{'name': '识别手机', 'enabled': True, 'class_ids': []}]},
                1,
                None,
            ),
            '检测场景「识别手机」需要选择类别',
        )
        self.assertIsNone(exam_task.validate_scene_bindings(
            {'rules': [{'name': '识别手机', 'enabled': True, 'class_ids': [2]}]},
            1,
            None,
        ))
        self.assertIsNone(exam_task.validate_scene_bindings(
            {'rules': [{'name': '识别手机', 'enabled': False, 'class_ids': []}]},
            1,
            None,
        ))
        self.assertIsNone(exam_task.missing_detection_class([
            {'name': '人员缺席', 'class_ids': [0], 'enabled': True},
        ]))
        self.assertIsNone(exam_task.missing_detection_class([
            {'name': '摄像头遮挡', 'type': 'camera_occlusion', 'enabled': True, 'class_ids': []},
        ]))

    def test_person_scenes_moved_to_pose(self):
        od_ids = [item['id'] for item in catalog.OD_SCENE_PRESETS]
        pose_ids = [item['id'] for item in catalog.POSE_SCENE_PRESETS]
        for preset_id in ('person_linger', 'aisle_crowd'):
            self.assertNotIn(preset_id, od_ids)
            self.assertIn(preset_id, pose_ids)
        self.assertNotIn('person_absence', od_ids)
        self.assertNotIn('person_absence', pose_ids)
        self.assertNotIn('generic_presence', od_ids)
        self.assertIn('camera_occlusion', od_ids)
        self.assertIn('glasses_detect', od_ids)
        self.assertIn('watch_detect', od_ids)
        self.assertNotIn('smart_glasses', od_ids)
        self.assertNotIn('smart_watch', od_ids)
        self.assertNotIn('fire_smoke', od_ids)
        self.assertNotIn('look_aside', pose_ids)
        self.assertNotIn('chin_rest', pose_ids)
        labels = catalog.alert_type_labels()
        self.assertNotIn('person_absence', labels)
        self.assertEqual(labels['exam_area_linger'], '人员滞留')
        self.assertEqual(labels['aisle_crowd'], '通道人员聚集')
        self.assertEqual(labels['desk_stand'], '考台旁站人')
        self.assertNotIn('desk_stand', od_ids)

    def test_fire_and_smoke_are_separate_scenes(self):
        od_ids = [item['id'] for item in catalog.OD_SCENE_PRESETS]
        self.assertIn('fire_detect', od_ids)
        self.assertIn('smoke_detect', od_ids)
        self.assertNotIn('fire_smoke', od_ids)
        labels = catalog.alert_type_labels()
        self.assertEqual(labels['fire_detect'], '识别火情')
        self.assertEqual(labels['smoke_detect'], '识别烟雾')

    def test_scene_class_must_stay_inside_algorithm_labels(self):
        params = {'rules': [{'name': '识别手机', 'enabled': True, 'class_ids': [1]}]}
        self.assertEqual(
            exam_task.validate_scene_bindings(params, 1, None, allowed_class_ids=[2, 4]),
            '场景「识别手机」只能选择算法已勾选的类别',
        )
        self.assertIsNone(exam_task.validate_scene_bindings(
            {'rules': [{'name': '识别手机', 'enabled': True, 'class_ids': [4]}]},
            1,
            None,
            allowed_class_ids=[2, 4],
        ))
        self.assertIsNone(exam_task.validate_scene_bindings(
            {'rules': [{'name': '识别手机', 'enabled': True, 'class_ids': [1]}]},
            1,
            None,
            allowed_class_ids=[],
        ))
        self.assertEqual(
            exam_task.classes_outside_allowlist(
                [{'name': '智能手表', 'type': 'smart_watch', 'enabled': True, 'class_ids': [1]}],
                [4],
            ),
            '场景「智能手表」只能选择算法已勾选的类别',
        )


if __name__ == '__main__':
    unittest.main()
