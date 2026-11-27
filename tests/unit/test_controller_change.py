import unittest


class ControllerChangeTests(unittest.TestCase):
    def test_select_after_change_group_ratio_with_cell_location(self):
        from knowledge_graph.graph.controller_change import facts

        html = '''<table>
          <tr><td>1. 변경내용</td><td>변경전</td><td>최대주주등</td><td>가 외 1명</td></tr>
          <tr><td>소유비율(%)</td><td>25.00</td></tr>
          <tr><td>변경후</td><td>최대주주등</td><td>나 외 2명</td></tr>
          <tr><td>소유비율(%)</td><td><b>30.50</b></td></tr>
          <tr><td>4. 변경일자</td><td>2026-10-27</td></tr>
        </table>'''
        result = facts(html)
        self.assertEqual(result['after_group_ratio'], ('30.50', 'table/1/row/4/cell/2'))
        self.assertEqual(result['change_date'], ('2026-10-27', 'table/1/row/5/cell/2'))

    def test_reject_extra_after_ratio_in_same_table(self):
        from knowledge_graph.graph.controller_change import facts

        html = '''<table><tr><td>변경후</td><td>최대주주등</td><td>가</td></tr>
          <tr><td>소유비율(%)</td><td>25.10</td></tr>
          <tr><td>소유비율(%)</td><td>30.50</td></tr>
          <tr><td>4. 변경일자</td><td>2026-10-27</td></tr></table>'''
        with self.assertRaisesRegex(ValueError, 'after_group_ratio'):
            facts(html)
