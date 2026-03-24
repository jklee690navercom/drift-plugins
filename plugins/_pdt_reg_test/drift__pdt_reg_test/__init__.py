def register(app):
    from framework.plugin.types import PluginInfo
    from framework.plugin.base import DriftDetector
    class TestDetector(DriftDetector):
        def detect(self, data, data_ids, stream, params): return []
    return PluginInfo(
        key='_pdt_reg_test', name='Test Plugin', version='1.0.0',
        description='Harness test plugin', category='statistical',
        card_template='', page_url='', detector_class=TestDetector)
