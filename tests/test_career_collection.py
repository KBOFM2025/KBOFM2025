import unittest
from scripts.collect_potential_career import HITTING, parse_table, innings_outs, entry_year


def table(body='', footer=''):
    headings = ''.join('<th>' + c + '</th>' for c in ['연도', '팀명', *HITTING])
    return f'<table><thead><tr>{headings}</tr></thead><tfoot>{footer}</tfoot><tbody>{body}</tbody></table>'


class CareerCollectionTests(unittest.TestCase):
    def test_missing_table_and_footer_are_not_zero_appearances(self):
        for page in ('<html>maintenance</html>', table()):
            with self.assertRaises(ValueError):
                parse_table(page, 'hitting')

    def test_explicit_empty_career_is_accepted(self):
        self.assertEqual(parse_table(table(footer='<tr><td>데이터가 존재하지 않습니다</td></tr>'), 'hitting'), [])

    def test_career_games_must_reconcile(self):
        values = ['0'] * len(HITTING)
        values[1] = '12'
        body = '<tr>' + ''.join(f'<td>{c}</td>' for c in ['2024', 'KIA', *values]) + '</tr>'
        footer = '<tr>' + ''.join(f'<th>{c}</th>' for c in ['통산', *values]) + '</tr>'
        self.assertEqual(parse_table(table(body, footer), 'hitting')[0]['G'], '12')
        with self.assertRaises(ValueError):
            parse_table(table(body, footer.replace('12', '13')), 'hitting')

    def test_fractional_innings(self):
        self.assertEqual(innings_outs('150 2/3'), 452)
        self.assertEqual(innings_outs('⅓'), 1)
        with self.assertRaises(ValueError):
            innings_outs('150.2')

    def test_entry_century_and_missing_values(self):
        self.assertEqual(entry_year('99삼성', 2025), 1999)
        self.assertEqual(entry_year('18 넥센 1차', 2025), 2018)
        self.assertIsNone(entry_year('미지명', 2025))
